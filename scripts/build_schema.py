"""Regenerate smdg/document.schema.json from the field list in smdg/records.py.

Run after adding or renaming a field:  python scripts/build_schema.py
The tests fail if the schema and COLUMNS drift apart.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from smdg.records import COLUMNS  # noqa: E402

INT = {"like_count", "reply_count", "share_count", "view_count"}

DESCRIPTIONS = {
    "doc_id": "Unique id: platform_doctype_id.",
    "platform": "Source platform.",
    "doc_type": "post or comment.",
    "post_id": "Platform id of the post this document belongs to.",
    "parent_id": "For comments, the doc_id being replied to. Empty for posts.",
    "url": "Link to the document. Empty when pseudonymized.",
    "author": "Account name, or a pseudonym such as u_3f9a1c02de.",
    "author_id": "Platform account id, or the pseudonym.",
    "community": "Subreddit for Reddit; empty elsewhere.",
    "created_at": "Posting time, ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ). Empty if unknown.",
    "title": "Title (YouTube and Reddit posts).",
    "text": "What the author typed. Never AI-generated.",
    "caption_transcript": "Speech transcript from platform captions (YouTube timedtext, TikTok captions).",
    "caption_source": "manual, auto, none, or empty for comments.",
    "llm_transcript": "Speech transcript from the model, one line per speaker turn, prefixed with the speaker label (A:, B:, ?:).",
    "on_screen_text": "Text shown in the video or images, from the model, separated by ' | '.",
    "visual_description": "Description of the visuals, from the model.",
    "audio_description": "Music and non-speech audio, from the model.",
    "speakers": "Distinct voices the model heard, labeled A, B, C in order of first speech.",
    "alt_text": "Author-written image descriptions (Bluesky).",
    "media_type": "video, image, mixed, or text.",
    "language": "Language code from the platform, or from the model if the platform gave none.",
    "hashtags": "Space-separated hashtags without #.",
    "like_count": "Likes (Reddit: net score) at collection time.",
    "reply_count": "Replies or comments at collection time.",
    "share_count": "Shares, reposts, or quotes at collection time.",
    "view_count": "Views at collection time.",
    "ai_generated": "True when any model-produced field (extraction or translation) has content.",
    "llm_model": "OpenRouter model that produced the model fields.",
    "llm_error": "Why model extraction or translation was skipped or failed.",
    "translation_language": "Target language of the translated_* fields. Empty when translation was off.",
    "translated_title": "Model translation of title.",
    "translated_text": "Model translation of text.",
    "translated_caption_transcript": "Model translation of caption_transcript.",
    "translated_llm_transcript": "Model translation of llm_transcript, keeping speaker labels.",
    "translated_on_screen_text": "Model translation of on_screen_text.",
    "source_input": "Exactly what was pasted to collect this document.",
    "collected_at": "Collection time, ISO 8601 UTC.",
}

ENUMS = {
    "platform": ["youtube", "tiktok", "instagram", "facebook", "reddit", "bluesky"],
    "doc_type": ["post", "comment"],
    "caption_source": ["manual", "auto", "none", ""],
    "media_type": ["video", "image", "mixed", "text", ""],
}


def build() -> dict:
    missing = set(COLUMNS) - set(DESCRIPTIONS)
    if missing:
        raise SystemExit(f"Add descriptions for: {sorted(missing)}")
    props = {}
    for c in COLUMNS:
        if c in INT:
            props[c] = {"type": ["integer", "null"]}
        elif c == "ai_generated":
            props[c] = {"type": "boolean"}
        elif c == "speakers":
            props[c] = {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["id", "description", "on_screen"],
                "properties": {"id": {"type": "string"}, "description": {"type": "string"},
                               "on_screen": {"type": "boolean"}}}}
        else:
            props[c] = {"type": "string"}
        props[c]["description"] = DESCRIPTIONS[c]
        if c in ENUMS:
            props[c]["enum"] = ENUMS[c]
    props["segments"] = {
        "type": "array",
        "description": "Time-stamped transcript pieces for this document (posts only).",
        "items": {
            "type": "object", "additionalProperties": False,
            "required": ["source", "speaker", "start_seconds", "end_seconds", "text"],
            "properties": {
                "source": {"type": "string", "enum": ["caption_manual", "caption_auto", "llm"]},
                "speaker": {"type": "string", "description": "Speaker label for model segments (A, B, ?); empty for captions."},
                "start_seconds": {"type": ["number", "null"]},
                "end_seconds": {"type": ["number", "null"]},
                "text": {"type": "string"},
            },
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/kwartler/social-media-data-gathering/blob/main/smdg/document.schema.json",
        "title": "Social media corpus document",
        "description": "One line of corpus.jsonl. Every platform uses these same fields; "
                       "fields a platform lacks are empty strings, empty lists, or null.",
        "type": "object",
        "additionalProperties": False,
        "required": list(props),
        "properties": props,
    }


if __name__ == "__main__":
    out = ROOT / "smdg" / "document.schema.json"
    out.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
