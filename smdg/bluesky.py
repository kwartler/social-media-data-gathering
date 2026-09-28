"""Bluesky through its open AT Protocol API.

Posts, reply threads, and profiles need no account. Keyword search needs the
student's own handle plus an app password (Settings > Privacy and security >
App passwords in Bluesky), which is Bluesky's official way to grant API access.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import httpx

from . import config
from .records import new_row

PUBLIC = "https://public.api.bsky.app/xrpc"
PDS = "https://bsky.social/xrpc"
UA = {"User-Agent": "social-media-data-gathering (academic research tool)"}

_session: dict = {}


def _get(method: str, params: dict, auth: bool = False) -> dict:
    base, headers = PUBLIC, dict(UA)
    if auth:
        base = PDS
        headers["Authorization"] = f"Bearer {_token()}"
    r = httpx.get(f"{base}/{method}", params=params, headers=headers, timeout=30)
    if r.status_code == 400 and "not found" in r.text.lower():
        raise LookupError("Bluesky post or account not found (deleted, or the link is wrong).")
    if r.status_code in (401, 403) and not auth:
        raise PermissionError("Bluesky requires sign-in for this request. Add your handle and app password in Settings.")
    r.raise_for_status()
    return r.json()


def _token() -> str:
    if _session.get("jwt") and _session.get("exp", 0) > time.time():
        return _session["jwt"]
    handle, pw = config.get("bluesky_handle"), config.get("bluesky_app_password")
    if not handle or not pw:
        raise PermissionError("Bluesky search needs your handle and an app password. Add them in Settings.")
    r = httpx.post(f"{PDS}/com.atproto.server.createSession",
                   json={"identifier": handle.lstrip("@"), "password": pw}, headers=UA, timeout=30)
    if r.status_code == 401:
        raise PermissionError("Bluesky rejected the handle or app password. Check them in Settings.")
    r.raise_for_status()
    _session.update(jwt=r.json()["accessJwt"], exp=time.time() + 60 * 60)
    return _session["jwt"]


def _did(actor: str) -> str:
    if actor.startswith("did:"):
        return actor
    return _get("com.atproto.identity.resolveHandle", {"handle": actor})["did"]


def _web_url(post: dict) -> str:
    rkey = post["uri"].rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{post['author'].get('handle') or post['author']['did']}/post/{rkey}"


def _media(post: dict) -> tuple[str, list[str], str]:
    """Return (media_type, image or playlist urls, alt text) from a post's embed view."""
    emb = post.get("embed") or {}
    if emb.get("$type", "").startswith("app.bsky.embed.recordWithMedia"):
        emb = emb.get("media") or {}
    t = emb.get("$type", "")
    if t.startswith("app.bsky.embed.images"):
        imgs = emb.get("images") or []
        return "image", [i["fullsize"] for i in imgs if i.get("fullsize")], " | ".join(i.get("alt", "") for i in imgs if i.get("alt"))
    if t.startswith("app.bsky.embed.video"):
        return "video", [emb["playlist"]] if emb.get("playlist") else [], emb.get("alt") or ""
    return "text", [], ""


def _row(post: dict, doc_type: str, root_id: str, parent_doc: str, source_input: str) -> dict:
    rec = post.get("record") or {}
    media_type, _, alt = _media(post)
    rkey = post["uri"].rsplit("/", 1)[-1]
    tags = {f["tag"] for fc in rec.get("facets") or [] for f in fc.get("features") or [] if f.get("tag")}
    row = new_row(
        "bluesky", doc_type, root_id,
        comment_id=rkey if doc_type == "comment" else None,
        parent_id=parent_doc,
        url=_web_url(post),
        author=post["author"].get("handle") or "",
        author_id=post["author"].get("did") or "",
        created_at=rec.get("createdAt") or post.get("indexedAt") or "",
        text=rec.get("text") or "",
        alt_text=alt,
        media_type=media_type,
        language=",".join(rec.get("langs") or []),
        like_count=post.get("likeCount"),
        reply_count=post.get("replyCount"),
        share_count=(post.get("repostCount") or 0) + (post.get("quoteCount") or 0),
        source_input=source_input,
    )
    if tags:
        row["hashtags"] = " ".join(sorted(set(row["hashtags"].split()) | tags))
    return row


def collect(target: dict, opts: dict) -> dict:
    uri = f"at://{_did(target['actor'])}/app.bsky.feed.post/{target['rkey']}"
    n_comments = int(opts.get("comments") or 0)
    thread = _get("app.bsky.feed.getPostThread", {"uri": uri, "depth": 6 if n_comments else 0, "parentHeight": 0})["thread"]
    if thread.get("$type", "").endswith("notFoundPost") or "post" not in thread:
        raise LookupError("Bluesky post not found (deleted, or the link is wrong).")
    post = thread["post"]
    root_id = target["rkey"]
    src = target.get("input", target.get("url", ""))
    main = _row(post, "post", root_id, "", src)
    rows = [main]

    def walk(node: dict, parent_doc: str):
        for rep in node.get("replies") or []:
            if len(rows) - 1 >= n_comments or "post" not in rep:
                continue
            r = _row(rep["post"], "comment", root_id, parent_doc, src)
            rows.append(r)
            walk(rep, r["doc_id"])

    if n_comments:
        walk(thread, main["doc_id"])

    media_type, urls, _ = _media(post)

    def fetch_media():
        if not urls:
            return None
        out = config.MEDIA_DIR / f"bluesky_{root_id}"
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
            r = httpx.get(u, timeout=60, headers=UA, follow_redirects=True)
            r.raise_for_status()
            p = out / f"image_{i + 1:02d}.jpg"
            p.write_bytes(r.content)
            files.append(p)
        return "images", files

    return {"rows": rows, "segments": [], "raw": thread, "fetch_media": fetch_media if media_type != "text" else None}


def _item(post: dict) -> dict:
    rec = post.get("record") or {}
    return {
        "platform": "bluesky",
        "url": _web_url(post),
        "id": post["uri"].rsplit("/", 1)[-1],
        "title": (rec.get("text") or "")[:200],
        "author": post["author"].get("handle") or "",
        "created_at": rec.get("createdAt") or "",
        "duration": None,
        "thumbnail": ((post.get("embed") or {}).get("images") or [{}])[0].get("thumb") or post["author"].get("avatar"),
    }


def list_account(target: dict, limit: int) -> Iterator[dict]:
    cursor, n = None, 0
    while n < limit:
        params = {"actor": target["actor"], "limit": min(100, limit - n), "filter": "posts_no_replies"}
        if cursor:
            params["cursor"] = cursor
        data = _get("app.bsky.feed.getAuthorFeed", params)
        for f in data.get("feed") or []:
            if f.get("reason"):  # skip reposts of other people's posts
                continue
            yield _item(f["post"])
            n += 1
            if n >= limit:
                return
        cursor = data.get("cursor")
        if not cursor:
            return


def search(query: str, limit: int, sort: str = "latest") -> Iterator[dict]:
    cursor, n = None, 0
    while n < limit:
        params = {"q": query, "limit": min(100, limit - n), "sort": sort}
        if cursor:
            params["cursor"] = cursor
        data = _get("app.bsky.feed.searchPosts", params, auth=True)
        posts = data.get("posts") or []
        for p in posts:
            yield _item(p)
            n += 1
            if n >= limit:
                return
        cursor = data.get("cursor")
        if not cursor or not posts:
            return
