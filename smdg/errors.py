"""Translate raw extractor and HTTP errors into specific, actionable messages."""
from __future__ import annotations

import re

RULES = [
    (r"login|log in|cookies|registered users|sign in to view|private", "This post needs a login (private, followers-only, age-restricted, or a logged-out rate limit). The app never logs in. Wait a while and retry, or pick a public post."),
    (r"rate.?limit|429|too many requests|exceeded", "The platform is rate-limiting requests. Wait 10 to 15 minutes, then re-run."),
    (r"confirm you.?re not a bot", "YouTube is asking for a bot check. Wait a few minutes, or update the app (newer yt-dlp versions usually fix this)."),
    (r"404|not found|removed|deleted|no longer available|unavailable|does not exist", "The post was not found. It may have been removed, made private, or the link is wrong."),
    (r"unsupported url", "This link format is not supported. Paste the post's own URL (not a search or feed page)."),
    (r"unable to extract|could not find|json|parse", "The platform's page changed and the extractor could not read it. Update the app; if it persists, report it."),
    (r"timed? ?out|connection|network|resolve host", "Network problem reaching the platform. Check your connection and retry."),
]


def friendly(err: Exception | str) -> str:
    raw = re.sub(r"\x1b\[[0-9;]*m", "", str(err)).replace("ERROR: ", "").strip()
    low = raw.lower()
    for pat, msg in RULES:
        if re.search(pat, low):
            return f"{msg} [detail: {raw[:200]}]"
    return raw[:300] or "Unknown error."
