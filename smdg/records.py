"""The corpus schema: one row per document (a post or a comment).

Every collector returns rows built with `new_row`, so all platforms export the
same columns in the same order. See codebook.md in each export for meanings.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from . import config

COLUMNS = [
    "doc_id",
    "platform",
    "doc_type",
    "post_id",
    "parent_id",
    "url",
    "author",
    "author_id",
    "community",
    "created_at",
    "title",
    "text",
    "caption_transcript",
    "caption_source",
    "llm_transcript",
    "on_screen_text",
    "visual_description",
    "audio_description",
    "speakers",
    "alt_text",
    "media_type",
    "language",
    "hashtags",
    "like_count",
    "reply_count",
    "share_count",
    "view_count",
    "ai_generated",
    "llm_model",
    "llm_error",
    "translation_language",
    "translated_title",
    "translated_text",
    "translated_caption_transcript",
    "translated_llm_transcript",
    "translated_on_screen_text",
    "source_input",
    "collected_at",
]

SEGMENT_COLUMNS = ["doc_id", "source", "speaker", "start_seconds", "end_seconds", "text"]

# Columns that identify people; moved to the linking key when pseudonymizing
IDENTIFYING = ("url", "author", "author_id")
TEXT_FIELDS = ("title", "text", "caption_transcript", "llm_transcript", "on_screen_text", "alt_text",
               "translated_title", "translated_text", "translated_caption_transcript",
               "translated_llm_transcript", "translated_on_screen_text")

# Source field -> translated field
TRANSLATABLE = {
    "title": "translated_title",
    "text": "translated_text",
    "caption_transcript": "translated_caption_transcript",
    "llm_transcript": "translated_llm_transcript",
    "on_screen_text": "translated_on_screen_text",
}

HASHTAG_RE = re.compile(r"(?<![\w#])#(\w+)", re.UNICODE)
MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?)")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_from_epoch(ts) -> str:
    if ts in (None, ""):
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError):
        return ""


def norm_iso(s: str) -> str:
    """Normalize any ISO 8601 timestamp to second precision UTC (2024-01-31T12:00:00Z)."""
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_row(platform: str, doc_type: str, post_id: str, **fields) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update(
        platform=platform,
        doc_type=doc_type,
        post_id=str(post_id),
        doc_id=f"{platform}_{doc_type}_{fields.get('comment_id') or post_id}",
        collected_at=now_iso(),
        ai_generated=False,
    )
    fields.pop("comment_id", None)
    for k, v in fields.items():
        if k in row and v is not None:
            row[k] = v
    row["created_at"] = norm_iso(row["created_at"])
    if not row["hashtags"]:
        row["hashtags"] = " ".join(sorted(set(HASHTAG_RE.findall(row["text"] or ""))))
    return row


def pseudonym(platform: str, ident: str) -> str:
    if not ident:
        return ""
    h = hashlib.sha256(f"{config.salt()}|{platform}|{ident.lower()}".encode()).hexdigest()
    return f"u_{h[:10]}"


def pseudonymize(rows: list[dict]) -> list[dict]:
    """Return (rows with people replaced by stable pseudonyms, linking key rows).

    The same account always gets the same pseudonym on this computer, so reply
    networks and author-level analysis still work.
    """
    key = []
    out = []
    for r in rows:
        r = dict(r)
        plat = r["platform"]
        key.append({
            "doc_id": r["doc_id"],
            "url": r["url"],
            "author": r["author"],
            "author_id": r["author_id"],
            "pseudonym": pseudonym(plat, r["author_id"] or r["author"]),
        })
        r["author"] = pseudonym(plat, r["author_id"] or r["author"])
        r["author_id"] = r["author"]
        r["url"] = ""
        for f in TEXT_FIELDS:
            if r.get(f):
                r[f] = MENTION_RE.sub(lambda m: "@" + pseudonym(plat, m.group(1)), r[f])
        out.append(r)
    return out, key
