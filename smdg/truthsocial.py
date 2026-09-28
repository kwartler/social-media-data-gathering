"""Truth Social through its public (Mastodon-style) API, logged out.

TERMS OF SERVICE WARNING: Truth Social's API rejects ordinary requests; this
module only gets through by presenting itself as a Chrome browser (the same
curl_cffi impersonation yt-dlp uses for TikTok). Truth Social's terms likely
prohibit automated collection. Get IRB guidance before using this for research
you plan to publish.

Works: single posts, an account's recent posts. Needs a login (not supported):
replies and search. Truth Social rate-limits hard, so requests are paced.
"""
from __future__ import annotations

import html
import re
import time
from typing import Iterator

from curl_cffi import requests as cffi

from . import config
from .records import new_row

API = "https://truthsocial.com/api/v1"
MIN_GAP = 3.0  # seconds between requests; Truth Social returns 429 quickly

_session = None
_last = 0.0


def _get(path: str, params: dict | None = None, raw: bool = False):
    global _session, _last
    if _session is None:
        _session = cffi.Session(impersonate="chrome")
    wait = MIN_GAP - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    url = path if path.startswith("http") else f"{API}{path}"
    try:
        r = _session.get(url, params=params, timeout=60)
    except Exception as e:
        raise RuntimeError(f"Could not reach Truth Social: {e}") from e
    finally:
        _last = time.time()
    if r.status_code == 429:
        raise RuntimeError("Truth Social is rate-limiting requests (429). Wait 15 to 30 minutes, then re-run "
                           "the failed links. Collect in smaller batches.")
    if r.status_code == 404:
        raise LookupError("Truth Social post or account not found (deleted, or the link is wrong).")
    if r.status_code in (401, 403):
        raise PermissionError("Truth Social refused the request. It may require a login for this content, "
                              "or it blocked automated access. The app never logs in.")
    r.raise_for_status()
    return r if raw else r.json()


def html_to_text(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"</p>\s*<p[^>]*>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def _media_type(st: dict) -> str:
    kinds = {m.get("type") for m in st.get("media_attachments") or []}
    if not kinds:
        return "text"
    if kinds <= {"video", "gifv"}:
        return "video"
    if kinds <= {"image"}:
        return "image"
    return "mixed"


def _row(st: dict, source_input: str) -> dict:
    acct = st.get("account") or {}
    row = new_row(
        "truthsocial", "post", st["id"],
        url=st.get("url") or f"https://truthsocial.com/@{acct.get('acct', '')}/{st['id']}",
        author=acct.get("acct") or acct.get("username") or "",
        author_id=str(acct.get("id") or ""),
        created_at=st.get("created_at") or "",
        text=html_to_text(st.get("content") or ""),
        alt_text=" | ".join(m["description"] for m in st.get("media_attachments") or [] if m.get("description")),
        media_type=_media_type(st),
        language=st.get("language") or "",
        like_count=st.get("favourites_count"),
        reply_count=st.get("replies_count"),
        share_count=st.get("reblogs_count"),
        source_input=source_input,
    )
    tags = {t.get("name") for t in st.get("tags") or [] if t.get("name")}
    if tags:
        row["hashtags"] = " ".join(sorted(set(row["hashtags"].split()) | tags))
    return row


def collect(target: dict, opts: dict) -> dict:
    st = _get(f"/statuses/{target['id']}")
    if st.get("reblog"):  # a repost: collect the original post
        st = st["reblog"]
    row = _row(st, target.get("input", target.get("url", "")))
    media = st.get("media_attachments") or []

    def fetch_media():
        videos = [m for m in media if m.get("type") in ("video", "gifv") and m.get("url")]
        images = [m for m in media if m.get("type") == "image" and m.get("url")]
        if not videos and not images:
            return None
        out = config.MEDIA_DIR / f"truthsocial_{st['id']}"
        out.mkdir(parents=True, exist_ok=True)
        max_secs = int(opts.get("max_media_seconds") or 300)
        if videos:
            dur = ((videos[0].get("meta") or {}).get("original") or {}).get("duration")
            if dur and dur > max_secs:
                raise RuntimeError(f"Video is {int(dur)}s, longer than the {max_secs}s limit set for model extraction.")
            p = out / "video.mp4"
            p.write_bytes(_get(videos[0]["url"], raw=True).content)
            return "video", [p]
        files = []
        for i, m in enumerate(images[:10]):
            p = out / f"image_{i + 1:02d}.jpg"
            p.write_bytes(_get(m["url"], raw=True).content)
            files.append(p)
        return "images", files

    return {"rows": [row], "segments": [], "raw": st, "fetch_media": fetch_media if media else None}


def _item(st: dict) -> dict:
    acct = st.get("account") or {}
    media = st.get("media_attachments") or []
    text = html_to_text(st.get("content") or "")
    return {
        "platform": "truthsocial",
        "url": st.get("url") or f"https://truthsocial.com/@{acct.get('acct', '')}/{st['id']}",
        "id": st["id"],
        "title": text[:200] or f"[{_media_type(st)} post, no text]",
        "author": acct.get("acct") or "",
        "created_at": st.get("created_at") or "",
        "duration": None,
        "thumbnail": media[0].get("preview_url") if media else acct.get("avatar"),
    }


def list_account(target: dict, limit: int) -> Iterator[dict]:
    acct = _get("/accounts/lookup", {"acct": target["handle"]})
    max_id, n = None, 0
    while n < limit:
        params = {"exclude_replies": "true", "exclude_reblogs": "true"}
        if max_id:
            params["max_id"] = max_id
        page = _get(f"/accounts/{acct['id']}/statuses", params)
        if not page:
            return
        for st in page:
            yield _item(st)
            n += 1
            if n >= limit:
                return
        max_id = page[-1]["id"]
