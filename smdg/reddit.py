"""Reddit through its official Data API (application-only OAuth).

Reddit blocks anonymous access, so each user needs a free "script" app from
https://www.reddit.com/prefs/apps and Reddit's approval under its Responsible
Builder Policy. The app only reads public content and never logs in as a user.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import httpx

from . import config
from .records import iso_from_epoch, new_row

API = "https://oauth.reddit.com"
UA = "python:social-media-data-gathering:v0.1 (academic research tool)"

_token: dict = {}


def _auth() -> str:
    if _token.get("value") and _token.get("exp", 0) > time.time():
        return _token["value"]
    cid, secret = config.get("reddit_client_id"), config.get("reddit_client_secret")
    if not cid or not secret:
        raise PermissionError("Reddit needs an API client ID and secret (Reddit blocks anonymous access). "
                              "Add them in Settings; the README explains how to get them.")
    r = httpx.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret),
                   data={"grant_type": "client_credentials"}, headers={"User-Agent": UA}, timeout=30)
    if r.status_code == 401:
        raise PermissionError("Reddit rejected the client ID or secret. Check them in Settings.")
    r.raise_for_status()
    d = r.json()
    if "access_token" not in d:
        raise PermissionError(f"Reddit did not issue a token: {d}")
    _token.update(value=d["access_token"], exp=time.time() + int(d.get("expires_in", 3600)) - 60)
    return _token["value"]


def _get(path: str, params: dict | None = None):
    r = httpx.get(f"{API}{path}", params={"raw_json": 1, **(params or {})},
                  headers={"User-Agent": UA, "Authorization": f"bearer {_auth()}"}, timeout=30)
    if r.status_code == 404:
        raise LookupError("Reddit returned 404: the post, subreddit, or user does not exist or was removed.")
    if r.status_code == 403:
        raise PermissionError("Reddit returned 403: the subreddit is private or quarantined, or the API app lacks access.")
    if r.status_code == 429:
        raise RuntimeError("Reddit rate limit hit (429). Wait a minute and re-run.")
    r.raise_for_status()
    return r.json()


def _resolve_share(url: str) -> str:
    r = httpx.get(url, headers={"User-Agent": UA}, follow_redirects=False, timeout=30)
    loc = r.headers.get("location") or ""
    if "/comments/" not in loc:
        raise ValueError("Could not resolve this Reddit share link. Open it in a browser and paste the full post URL.")
    return loc


def _post_row(d: dict, source_input: str) -> dict:
    return new_row(
        "reddit", "post", d["id"],
        url="https://www.reddit.com" + d.get("permalink", ""),
        author=d.get("author") or "",
        author_id=d.get("author_fullname") or "",
        community="r/" + (d.get("subreddit") or ""),
        created_at=iso_from_epoch(d.get("created_utc")),
        title=d.get("title") or "",
        text=d.get("selftext") or "",
        media_type=_media(d)[0],
        like_count=d.get("score"),
        reply_count=d.get("num_comments"),
        share_count=d.get("num_crossposts"),
        source_input=source_input,
    )


def _media(d: dict) -> tuple[str, list[str]]:
    if d.get("is_video"):
        rv = ((d.get("media") or d.get("secure_media") or {}).get("reddit_video")) or {}
        return "video", [rv.get("hls_url") or rv.get("fallback_url")] if rv else []
    if d.get("is_gallery"):
        meta = d.get("media_metadata") or {}
        items = (d.get("gallery_data") or {}).get("items") or []
        return "image", [meta[i["media_id"]]["s"]["u"] for i in items if meta.get(i["media_id"], {}).get("s", {}).get("u")][:10]
    if d.get("post_hint") == "image" and d.get("url"):
        return "image", [d["url"]]
    return "text", []


def collect(target: dict, opts: dict) -> dict:
    if target.get("share"):
        from .classify import classify
        target = {**classify(_resolve_share(target["url"])), "input": target.get("input", target["url"])}
    n_comments = int(opts.get("comments") or 0)
    data = _get(f"/comments/{target['id']}", {"limit": max(n_comments, 1), "depth": 10, "sort": "top"})
    d = data[0]["data"]["children"][0]["data"]
    src = target.get("input", target.get("url", ""))
    main = _post_row(d, src)
    rows = [main]

    def walk(children: list):
        for c in children:
            if len(rows) - 1 >= n_comments:
                return
            if c.get("kind") != "t1":
                continue
            cd = c["data"]
            pid = cd.get("parent_id") or ""
            rows.append(new_row(
                "reddit", "comment", d["id"],
                comment_id=cd["id"],
                parent_id=f"reddit_comment_{pid[3:]}" if pid.startswith("t1_") else main["doc_id"],
                url="https://www.reddit.com" + cd.get("permalink", ""),
                author=cd.get("author") or "",
                author_id=cd.get("author_fullname") or "",
                community=main["community"],
                created_at=iso_from_epoch(cd.get("created_utc")),
                text=cd.get("body") or "",
                media_type="text",
                like_count=cd.get("score"),
                source_input=src,
            ))
            replies = cd.get("replies")
            if isinstance(replies, dict):
                walk(replies["data"]["children"])

    if n_comments:
        walk(data[1]["data"]["children"])

    media_type, urls = _media(d)

    def fetch_media():
        if not urls:
            return None
        out = config.MEDIA_DIR / f"reddit_{d['id']}"
        out.mkdir(parents=True, exist_ok=True)
        if media_type == "video":
            import yt_dlp
            from .ytdlp_sites import _opts
            with yt_dlp.YoutubeDL(_opts(skip_download=False, outtmpl=str(out / "video.%(ext)s"), merge_output_format="mp4")) as ydl:
                ydl.download([urls[0]])
            files = sorted(out.glob("video.*"))
            return ("video", files[:1]) if files else None
        files = []
        for i, u in enumerate(urls):
            r = httpx.get(u, timeout=60, headers={"User-Agent": UA}, follow_redirects=True)
            r.raise_for_status()
            p = out / f"image_{i + 1:02d}.jpg"
            p.write_bytes(r.content)
            files.append(p)
        return "images", files

    return {"rows": rows, "segments": [], "raw": data, "fetch_media": fetch_media if media_type != "text" else None}


def _item(d: dict) -> dict:
    thumb = d.get("thumbnail") if (d.get("thumbnail") or "").startswith("http") else ""
    return {
        "platform": "reddit",
        "url": "https://www.reddit.com" + d.get("permalink", ""),
        "id": d["id"],
        "title": d.get("title") or "",
        "author": d.get("author") or "",
        "created_at": iso_from_epoch(d.get("created_utc")),
        "duration": None,
        "thumbnail": thumb,
    }


def _paged(path: str, params: dict, limit: int) -> Iterator[dict]:
    after, n = None, 0
    while n < limit:
        p = {**params, "limit": min(100, limit - n)}
        if after:
            p["after"] = after
        data = _get(path, p)["data"]
        for c in data.get("children") or []:
            if c.get("kind") == "t3":
                yield _item(c["data"])
                n += 1
        after = data.get("after")
        if not after:
            return


def list_account(target: dict, limit: int, sort: str = "new") -> Iterator[dict]:
    if target["target"] == "subreddit":
        yield from _paged(f"/r/{target['name']}/{sort}", {"t": "all"} if sort == "top" else {}, limit)
    else:
        yield from _paged(f"/user/{target['name']}/submitted", {"sort": sort}, limit)


def search(query: str, limit: int, sort: str = "new", subreddit: str = "") -> Iterator[dict]:
    path = f"/r/{subreddit}/search" if subreddit else "/search"
    params = {"q": query, "sort": sort, "type": "link"}
    if subreddit:
        params["restrict_sr"] = 1
    yield from _paged(path, params, limit)
