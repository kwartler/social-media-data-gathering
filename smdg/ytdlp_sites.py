"""YouTube, TikTok, Instagram, and Facebook through yt-dlp.

YouTube works as in yt-timed-text by default: text comes from the timedtext
caption track (json3), and the raw json3 is exported. The YouTube tab can also
send the video to the model instead of, or alongside, the captions.
TikTok, Instagram, and Facebook add a media download step that feeds the
OpenRouter extraction.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterator

import httpx
import yt_dlp

from . import captions, config
from .records import iso_from_epoch, new_row


YT_CLIENTS = ["web", "android"]  # same as yt-timed-text


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _opts(**extra) -> dict:
    o = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "socket_timeout": 30,
        "ignore_no_formats_error": True,  # image-only posts still return metadata
        "extractor_args": {"youtube": {"player_client": YT_CLIENTS}},
    }
    ff = _ffmpeg()
    if ff:
        o["ffmpeg_location"] = ff
    o.update(extra)
    return o


# ---------------------------------------------------------------------------
# Single posts
# ---------------------------------------------------------------------------

def collect(target: dict, opts: dict) -> dict:
    platform = target["platform"]
    n_comments = int(opts.get("comments") or 0)
    extra = {}
    if n_comments:
        extra["getcomments"] = True
        extra["extractor_args"] = {
            "youtube": {"player_client": YT_CLIENTS, "max_comments": [str(n_comments), "all", "all", "all"]},
        }
    with yt_dlp.YoutubeDL(_opts(**extra)) as ydl:
        info = ydl.extract_info(target["url"], download=False)
        info = ydl.sanitize_info(info)

        entries = info.get("entries") if info.get("_type") == "playlist" else None
        main = info
        if entries:
            # Carousel: metadata lives on the first entry
            main = {**entries[0], **{k: v for k, v in info.items() if v and k != "entries"}}

        yt_source = opts.get("youtube_source") or "captions"
        if platform == "youtube" and yt_source == "model":
            cap_segs, cap_source, cap_raw = [], "none", None
        else:
            cap_segs, cap_source, cap_raw = _platform_captions(ydl, main, opts.get("caption_lang") or "en")

    post_id = str(main.get("id") or target.get("id") or "")
    url = main.get("webpage_url") or target["url"]
    media_type = _media_type(main, entries)
    row = new_row(
        platform, "post", post_id,
        url=url,
        author=main.get("uploader") or main.get("channel") or "",
        author_id=str(main.get("uploader_id") or main.get("channel_id") or ""),
        created_at=iso_from_epoch(main.get("timestamp")) or _upload_date(main.get("upload_date")),
        title=(main.get("title") or "") if platform == "youtube" else "",
        text=main.get("description") or "",
        caption_transcript=captions.join(cap_segs),
        caption_source=cap_source,
        media_type=media_type,
        language=main.get("language") or "",
        like_count=main.get("like_count"),
        reply_count=main.get("comment_count"),
        share_count=main.get("repost_count"),
        view_count=main.get("view_count"),
        source_input=target.get("input", target["url"]),
    )
    if main.get("tags"):
        row["hashtags"] = " ".join(sorted(set(row["hashtags"].split()) | {t.lstrip("#") for t in main["tags"] if t}))

    rows = [row]
    comments = info.get("comments") or main.get("comments") or []
    for c in comments[: n_comments or 0]:
        if not c.get("text"):
            continue
        parent = c.get("parent")
        rows.append(new_row(
            platform, "comment", post_id,
            comment_id=str(c.get("id")),
            parent_id=f"{platform}_comment_{parent}" if parent and parent != "root" else row["doc_id"],
            url=url,
            author=c.get("author") or "",
            author_id=str(c.get("author_id") or ""),
            created_at=iso_from_epoch(c.get("timestamp")),
            text=c["text"],
            like_count=c.get("like_count"),
            media_type="text",
            source_input=row["source_input"],
        ))

    segments = [{"doc_id": row["doc_id"], "source": f"caption_{cap_source}", **s} for s in cap_segs]
    raw = {k: v for k, v in info.items() if k not in ("formats", "requested_formats", "thumbnails", "automatic_captions", "heatmap")}
    if cap_raw is not None:
        raw["_caption_track"] = cap_raw

    timedtext = {}
    if platform == "youtube" and cap_raw is not None:
        ext = "json" if cap_raw["ext"] == "json3" else cap_raw["ext"]  # json3 keeps yt-timed-text's .json name
        timedtext[f"{post_id}_{cap_raw['lang']}.{ext}"] = cap_raw["data"]

    # YouTube: timedtext captions by default (as in yt-timed-text); the model only if chosen
    if platform == "youtube" and yt_source == "captions":
        return {"rows": rows, "segments": segments, "raw": raw, "timedtext": timedtext, "fetch_media": None}

    duration = main.get("duration")
    max_secs = int(opts.get("max_media_seconds") or 300)

    def fetch_media() -> tuple[str, list[Path]] | None:
        if duration and duration > max_secs:
            raise RuntimeError(f"Video is {int(duration)}s, longer than the {max_secs}s limit set for model extraction.")
        return download_media(target["url"], info, entries, post_id, platform)

    return {"rows": rows, "segments": segments, "raw": raw, "timedtext": timedtext, "fetch_media": fetch_media}


def _upload_date(d) -> str:
    if d and len(str(d)) == 8:
        d = str(d)
        return f"{d[:4]}-{d[4:6]}-{d[6:]}T00:00:00Z"
    return ""


def _has_video(e: dict) -> bool:
    # Facebook leaves vcodec unset, so "unknown" counts as video unless marked absent
    return any(f.get("vcodec") != "none" and f.get("video_ext") != "none" for f in e.get("formats") or [])


def _media_type(main: dict, entries) -> str:
    kinds = {"video" if _has_video(e) else "image" for e in (entries or [main])}
    return "video" if kinds == {"video"} else ("image" if kinds == {"image"} else "mixed")


def _platform_captions(ydl, info: dict, lang: str):
    """Prefer creator-uploaded captions, then auto captions. Returns (segments, source, raw)."""
    for source, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
        code, tracks = captions.pick_track(info.get(key) or {}, lang)
        if not tracks:
            continue
        track = next((t for t in tracks if t.get("ext") == "json3"), None) \
            or next((t for t in tracks if t.get("ext") in ("vtt", "srt")), None)
        if not track or not track.get("url"):
            continue
        try:
            raw = ydl.urlopen(track["url"]).read().decode("utf-8", errors="replace")
            segs = captions.parse_any(raw, track.get("ext"))
        except Exception:
            continue
        if segs:
            return segs, source, {"lang": code, "ext": track.get("ext"), "data": raw if track.get("ext") != "json3" else json.loads(raw)}
    return [], "none", None


def download_media(url: str, info: dict, entries, post_id: str, platform: str) -> tuple[str, list[Path]] | None:
    """Download a low-resolution copy for the model. Videos win over images."""
    out_dir = config.MEDIA_DIR / f"{platform}_{post_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    items = entries or [info]
    videos = [e for e in items if _has_video(e)]

    if videos:
        opts = _opts(
            skip_download=False,
            format="b[height<=?480][vcodec!=?none][acodec!=?none]/bv*[height<=?480]+ba/b[height<=?720]/bv*+ba/b",
            merge_output_format="mp4",
            outtmpl=str(out_dir / "%(id)s.%(ext)s"),
            noplaylist=False,
            playlist_items="1",
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = sorted(p for p in out_dir.iterdir() if p.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"))
        return ("video", files[:1]) if files else None

    # Image post: take the full-size image for each item (max 10)
    files = []
    for i, e in enumerate(items[:10]):
        thumbs = e.get("thumbnails") or []
        img = (thumbs[-1].get("url") if thumbs else None) or e.get("thumbnail")
        if not img:
            continue
        r = httpx.get(img, timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        ext = ".png" if "png" in r.headers.get("content-type", "") else ".jpg"
        p = out_dir / f"image_{i + 1:02d}{ext}"
        p.write_bytes(r.content)
        files.append(p)
    return ("images", files) if files else None


# ---------------------------------------------------------------------------
# Accounts and search
# ---------------------------------------------------------------------------

def list_account(target: dict, limit: int) -> Iterator[dict]:
    url = target["url"]
    if target["platform"] == "youtube" and not url.rstrip("/").endswith(("/videos", "/shorts")):
        url = url.rstrip("/") + "/videos"
    opts = _opts(extract_flat="in_playlist", playlistend=limit)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    for e in (info.get("entries") or [])[:limit]:
        if e:
            yield _list_item(target["platform"], e)


def youtube_languages(url: str) -> dict:
    """Caption languages for one video: {title, manual: [{code, name}], auto: [...]}. From yt-timed-text."""
    with yt_dlp.YoutubeDL(_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    def fmt(d):
        out = []
        for code, tracks in (d or {}).items():
            name = code
            if tracks and isinstance(tracks, list):
                name = tracks[0].get("name") or code
            out.append({"code": code, "name": name})
        return out

    return {"title": info.get("title"), "manual": fmt(info.get("subtitles")), "auto": fmt(info.get("automatic_captions"))}


def search_youtube(query: str, limit: int) -> Iterator[dict]:
    with yt_dlp.YoutubeDL(_opts(extract_flat="in_playlist")) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    for e in info.get("entries") or []:
        if e:
            yield _list_item("youtube", e)


def _list_item(platform: str, e: dict) -> dict:
    vid = e.get("id")
    url = e.get("url") if (e.get("url") or "").startswith("http") else None
    if platform == "youtube":
        url = f"https://www.youtube.com/watch?v={vid}"
        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    else:
        thumb = (e.get("thumbnails") or [{}])[-1].get("url") or e.get("thumbnail")
    return {
        "platform": platform,
        "url": url or e.get("webpage_url") or "",
        "id": vid,
        "title": e.get("title") or e.get("description") or vid,
        "author": e.get("uploader") or e.get("channel") or "",
        "created_at": iso_from_epoch(e.get("timestamp")),
        "duration": e.get("duration"),
        "thumbnail": thumb,
    }
