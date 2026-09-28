"""Turn a pasted URL or handle into {platform, kind, ...}.

kind is "post" (one item) or "account" (a list of recent items to choose from).
Unsupported platforms raise ValueError with a specific explanation.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

UNSUPPORTED = {
    "snapchat.com": "Snapchat is not supported: there is no public download path and content expires.",
    "x.com": "X/Twitter is not supported: its API is paid and logged-out access is blocked.",
    "twitter.com": "X/Twitter is not supported: its API is paid and logged-out access is blocked.",
    "threads.net": "Threads is not supported yet.",
    "threads.com": "Threads is not supported yet.",
    "linkedin.com": "LinkedIn is not supported: its terms prohibit automated collection.",
    "vimeo.com": "Vimeo is not supported: its videos are copy-protected (DRM), so they cannot be sent to the model.",
    "kick.com": "Kick is not supported: its links lead to live streams, which cannot be collected.",
}


def _host(p) -> str:
    h = (p.netloc or "").lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def classify(raw: str) -> dict:
    s = raw.strip()
    if not s:
        raise ValueError("Empty input.")

    # Shorthand handles: tiktok:@name, reddit:r/sub, reddit:u/name, bsky:name.bsky.social
    m = re.match(r"^(tiktok|reddit|bsky|bluesky|youtube|yt|truth|truthsocial):\s*(.+)$", s, re.I)
    if m:
        plat, ref = m.group(1).lower(), m.group(2).strip()
        if plat == "tiktok":
            return {"platform": "tiktok", "kind": "account", "url": f"https://www.tiktok.com/@{ref.lstrip('@')}"}
        if plat == "reddit":
            return _reddit_ref(ref, s)
        if plat in ("truth", "truthsocial"):
            return {"platform": "truthsocial", "kind": "account", "handle": ref.lstrip("@")}
        if plat in ("bsky", "bluesky"):
            return {"platform": "bluesky", "kind": "account", "actor": ref.lstrip("@")}
        return {"platform": "youtube", "kind": "account", "url": f"https://www.youtube.com/@{ref.lstrip('@')}"}

    if YT_ID_RE.match(s):
        return {"platform": "youtube", "kind": "post", "url": f"https://www.youtube.com/watch?v={s}", "id": s}

    if not re.match(r"^https?://", s, re.I):
        s = "https://" + s
    p = urlparse(s)
    host = _host(p)
    path = p.path or "/"
    parts = [x for x in path.split("/") if x]

    for bad, msg in UNSUPPORTED.items():
        if host == bad or host.endswith("." + bad):
            raise ValueError(msg)

    # YouTube
    if host == "youtu.be" and parts and YT_ID_RE.match(parts[0]):
        return {"platform": "youtube", "kind": "post", "url": f"https://www.youtube.com/watch?v={parts[0]}", "id": parts[0]}
    if host.endswith("youtube.com"):
        if path == "/watch":
            vid = (parse_qs(p.query).get("v") or [""])[0]
            if YT_ID_RE.match(vid):
                return {"platform": "youtube", "kind": "post", "url": f"https://www.youtube.com/watch?v={vid}", "id": vid}
        if len(parts) >= 2 and parts[0] in ("shorts", "live", "embed") and YT_ID_RE.match(parts[1]):
            return {"platform": "youtube", "kind": "post", "url": f"https://www.youtube.com/watch?v={parts[1]}", "id": parts[1]}
        if parts and (parts[0].startswith("@") or parts[0] in ("channel", "c", "user")):
            base = "/".join(parts[:1] if parts[0].startswith("@") else parts[:2])
            return {"platform": "youtube", "kind": "account", "url": f"https://www.youtube.com/{base}"}
        raise ValueError("Unrecognized YouTube URL. Paste a video, Shorts, or channel link.")

    # TikTok
    if host.endswith("tiktok.com"):
        if host in ("vm.tiktok.com", "vt.tiktok.com") or (parts and parts[0] == "t"):
            return {"platform": "tiktok", "kind": "post", "url": s}
        if len(parts) >= 3 and parts[1] in ("video", "photo"):
            return {"platform": "tiktok", "kind": "post", "url": f"https://www.tiktok.com/{parts[0]}/{parts[1]}/{parts[2]}", "id": parts[2]}
        if len(parts) == 1 and parts[0].startswith("@"):
            return {"platform": "tiktok", "kind": "account", "url": f"https://www.tiktok.com/{parts[0]}"}
        raise ValueError("Unrecognized TikTok URL. Paste a video link or a profile link (tiktok.com/@name).")

    # Instagram: single posts only
    if host.endswith("instagram.com"):
        if len(parts) >= 2 and parts[0] in ("p", "reel", "reels", "tv"):
            return {"platform": "instagram", "kind": "post", "url": f"https://www.instagram.com/{parts[0]}/{parts[1]}/", "id": parts[1]}
        if len(parts) >= 3 and parts[1] in ("p", "reel") :
            return {"platform": "instagram", "kind": "post", "url": f"https://www.instagram.com/{parts[1]}/{parts[2]}/", "id": parts[2]}
        if parts and parts[0] == "stories":
            raise ValueError("Instagram stories require a login, so they are not supported. Paste a post or reel link.")
        raise ValueError("Instagram profiles are not supported (they require a login). Paste individual post or reel links.")

    # Facebook: single posts only
    if host.endswith("facebook.com") or host == "fb.watch":
        if host == "fb.watch" or any(x in parts for x in ("videos", "reel", "posts", "watch", "share", "photo", "photos", "story.php")) or "story_fbid" in p.query or path.startswith("/watch"):
            return {"platform": "facebook", "kind": "post", "url": s}
        raise ValueError("Facebook profiles and pages are not supported (they require a login). Paste individual public post or video links.")

    # Reddit
    if host.endswith("reddit.com") or host == "redd.it":
        if host == "redd.it" and parts:
            return {"platform": "reddit", "kind": "post", "id": parts[0], "url": s}
        if "comments" in parts:
            i = parts.index("comments")
            if len(parts) > i + 1:
                cid = parts[i + 3] if len(parts) > i + 3 else ""
                return {"platform": "reddit", "kind": "post", "id": parts[i + 1], "comment": cid, "url": s}
        if len(parts) >= 4 and parts[0] == "r" and parts[2] == "s":
            return {"platform": "reddit", "kind": "post", "share": True, "url": s}
        if len(parts) >= 2 and parts[0] in ("r", "u", "user"):
            return _reddit_ref("/".join(parts[:2]), s)
        raise ValueError("Unrecognized Reddit URL. Paste a post link, a subreddit (reddit.com/r/name), or a user (reddit.com/user/name).")

    # Truth Social: /@user/posts/ID or /@user/ID for a post, /@user for an account
    if host == "truthsocial.com":
        if parts and parts[0].startswith("@"):
            post_id = parts[2] if len(parts) >= 3 and parts[1] == "posts" else (parts[1] if len(parts) >= 2 else "")
            if post_id.isdigit():
                return {"platform": "truthsocial", "kind": "post", "id": post_id, "url": s}
            if len(parts) == 1:
                return {"platform": "truthsocial", "kind": "account", "handle": parts[0][1:]}
        raise ValueError("Unrecognized Truth Social URL. Paste a post link or a profile link (truthsocial.com/@name).")

    # Bluesky
    if host == "bsky.app":
        if len(parts) >= 4 and parts[0] == "profile" and parts[2] == "post":
            return {"platform": "bluesky", "kind": "post", "actor": parts[1], "rkey": parts[3], "url": s}
        if len(parts) >= 2 and parts[0] == "profile":
            return {"platform": "bluesky", "kind": "account", "actor": parts[1]}
        raise ValueError("Unrecognized Bluesky URL. Paste a post link or a profile link.")

    # Any other site yt-dlp supports (Rumble, BitChute, Odysee, Dailymotion, Bilibili, ...)
    site = ytdlp_site(s)
    if site:
        return {"platform": "other", "kind": "post", "url": s, "site": site}

    raise ValueError(f"Unrecognized or unsupported site: {host or s}")


_EXTRACTORS = None


def ytdlp_site(url: str) -> str:
    """Name of the yt-dlp extractor that handles url, or "" (the catch-all generic one doesn't count)."""
    global _EXTRACTORS
    if _EXTRACTORS is None:
        from yt_dlp.extractor import gen_extractor_classes
        _EXTRACTORS = [c for c in gen_extractor_classes() if c.ie_key() != "Generic"]
    for c in _EXTRACTORS:
        try:
            if c.suitable(url) and c.working():
                return c.ie_key()
        except Exception:
            continue
    return ""


def _reddit_ref(ref: str, raw: str) -> dict:
    ref = ref.strip().strip("/")
    m = re.match(r"^(r|u|user)/([A-Za-z0-9_-]+)$", ref)
    if not m:
        raise ValueError(f"Unrecognized Reddit reference: {raw}. Use r/subreddit or u/username.")
    kind = "subreddit" if m.group(1) == "r" else "user"
    return {"platform": "reddit", "kind": "account", "target": kind, "name": m.group(2)}
