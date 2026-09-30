"""OpenRouter extraction: turn a video or images into transcript + visual text.

The prompt is versioned and saved in every export's manifest so a corpus can be
reproduced or audited later. Results are cached by (media hash, model, prompt
version), so re-running a collection does not pay for the same file twice.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
from pathlib import Path

import httpx

from . import config

API = "https://openrouter.ai/api/v1"
PROMPT_VERSION = "v2"

SYSTEM_PROMPT = (
    "You extract data from social media media files for an academic text-analysis "
    "corpus. Report only what is actually visible or audible. Do not guess at "
    "anyone's identity, intent, age, or other attributes that are not stated. "
    "Transcribe speech verbatim in its original language; do not translate or "
    "clean it up. If something is absent (no speech, no on-screen text), return "
    "an empty value rather than inventing content."
)

USER_PROMPT = (
    "Extract the following from the attached {kind} and reply with JSON only.\n"
    "- language: BCP-47 code of the main spoken or written language, or \"und\".\n"
    "- speakers: one entry per distinct voice, labeled \"A\", \"B\", \"C\" in order of "
    "first speech. Tell voices apart using both the audio (voice quality, pitch, "
    "accent) and the video (whose lips move, who faces the camera, cuts between "
    "people). For each give a short neutral visual or vocal description "
    "(\"person in red jacket facing camera\", \"off-screen narrator\") and whether they "
    "are visible on screen while speaking. Do not name anyone unless the name is "
    "shown or spoken. Empty list if there is no speech.\n"
    "- transcript_segments: one entry per speaker turn, in order, each with the "
    "speaker label, approximate start_seconds, and the verbatim text. Start a new "
    "segment whenever the speaker changes. Use \"?\" as the speaker when you cannot "
    "tell who is talking. Empty list for images or no speech.\n"
    "- on_screen_text: list of distinct text overlays, captions, signs, or "
    "stickers shown, verbatim, in order of appearance.\n"
    "- visual_description: 2 to 5 plain sentences objectively describing the "
    "setting, people's visible actions and gestures, objects, symbols, and imagery.\n"
    "- audio_description: one sentence on music, sound effects, or other "
    "non-speech audio. Empty string for images."
)

SCHEMA = {
    "name": "media_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["language", "speakers", "transcript_segments", "on_screen_text",
                     "visual_description", "audio_description"],
        "properties": {
            "language": {"type": "string"},
            "speakers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "description", "on_screen"],
                    "properties": {"id": {"type": "string"}, "description": {"type": "string"},
                                   "on_screen": {"type": "boolean"}},
                },
            },
            "transcript_segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "start_seconds", "text"],
                    "properties": {"speaker": {"type": "string"}, "start_seconds": {"type": "number"},
                                   "text": {"type": "string"}},
                },
            },
            "on_screen_text": {"type": "array", "items": {"type": "string"}},
            "visual_description": {"type": "string"},
            "audio_description": {"type": "string"},
        },
    },
}

TRANSLATE_VERSION = "t1"
TRANSLATE_PROMPT = (
    "Translate each value in the JSON object below into {language}. Keep the keys "
    "unchanged. Preserve meaning, tone, slang, profanity, emoji, hashtags, @mentions, "
    "URLs, and speaker labels (such as \"A:\") exactly; do not summarize, soften, or "
    "explain. If a value is already in {language}, return it unchanged. Reply with the "
    "JSON object only."
)

MAX_BYTES = 45 * 1024 * 1024


class LLMError(Exception):
    pass


def prompt_record() -> dict:
    return {"version": PROMPT_VERSION, "system": SYSTEM_PROMPT, "user": USER_PROMPT, "schema": SCHEMA,
            "translation": {"version": TRANSLATE_VERSION, "system": TRANSLATE_PROMPT}}


def list_models() -> list[dict]:
    """The curated model choices, with current prices from OpenRouter when reachable."""
    prices = {}
    try:
        r = httpx.get(f"{API}/models", timeout=30)
        r.raise_for_status()
        for m in r.json().get("data", []):
            p = (m.get("pricing") or {})
            try:
                prices[m["id"]] = (float(p.get("prompt")) * 1_000_000, float(p.get("completion")) * 1_000_000)
            except (TypeError, ValueError):
                pass
    except httpx.HTTPError:
        pass  # offline: still offer the choices, just without prices
    return [{**c, "prompt_per_million": prices.get(c["id"], (None, None))[0],
             "completion_per_million": prices.get(c["id"], (None, None))[1]}
            for c in config.MODEL_CHOICES]


def _data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMError("The model did not return usable JSON (it may have refused). "
                   f"Reply began: {text[:160]!r}")


def _chat(body: dict, cache_key: str) -> dict:
    """POST to OpenRouter with caching; returns {"content": str, "usage": {}, "model": str}."""
    api_key = config.get("openrouter_api_key")
    if not api_key:
        raise LLMError("No OpenRouter API key set. Add one in Settings.")
    cache = config.CACHE_DIR / f"{cache_key}.json"
    if cache.exists():
        try:
            out = json.loads(cache.read_text(encoding="utf-8"))
            out["cached"] = True
            return out
        except Exception:
            cache.unlink(missing_ok=True)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/kwartler/social-media-data-gathering",
        "X-Title": "Social Media Data Gathering",
    }
    body = {**body, "usage": {"include": True}}
    try:
        r = httpx.post(f"{API}/chat/completions", json=body, headers=headers, timeout=300)
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach OpenRouter: {e}") from e
    if r.status_code == 401:
        raise LLMError("OpenRouter rejected the API key (401). Check it in Settings.")
    if r.status_code == 402:
        raise LLMError("OpenRouter account is out of credit (402).")
    if r.status_code == 429:
        raise LLMError("OpenRouter rate limit hit (429). Wait a minute and re-run.")
    try:
        data = r.json()
    except ValueError:
        raise LLMError(f"OpenRouter returned HTTP {r.status_code} with a non-JSON body.")
    if r.status_code >= 400 or data.get("error"):
        msg = (data.get("error") or {}).get("message") or f"HTTP {r.status_code}"
        raise LLMError(f"OpenRouter error: {msg}")
    choice = (data.get("choices") or [{}])[0]
    out = {"content": (choice.get("message") or {}).get("content") or "",
           "usage": data.get("usage") or {}, "model": data.get("model") or body["model"]}
    _parse_json(out["content"])  # only cache replies that parse
    config.ensure_dirs()
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", model)


def extract(files: list[Path], kind: str, model: str) -> dict:
    """kind is "video" or "images". Returns the parsed JSON plus _usage, _model_used, _cached."""
    total = sum(f.stat().st_size for f in files)
    if total > MAX_BYTES:
        raise LLMError(f"Media is {total // (1024 * 1024)} MB, over the {MAX_BYTES // (1024 * 1024)} MB limit "
                       "for sending to the model. Lower the max media length in Settings.")
    h = hashlib.sha256()
    for f in files:
        h.update(f.read_bytes())

    content = [{"type": "text", "text": USER_PROMPT.format(kind="video" if kind == "video" else "image(s)")}]
    for f in files:
        if kind == "video":
            content.append({"type": "video_url", "video_url": {"url": _data_url(f)}})
        else:
            content.append({"type": "image_url", "image_url": {"url": _data_url(f)}})
    body = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
    }
    res = _chat(body, f"llm_{h.hexdigest()[:24]}_{_slug(model)}_{PROMPT_VERSION}")
    out = _parse_json(res["content"])
    out["_usage"], out["_model_used"], out["_cached"] = res["usage"], res["model"], bool(res.get("cached"))
    return out


def translate(values: dict[str, str], language: str, model: str) -> tuple[dict[str, str], dict]:
    """Translate a {key: text} mapping in one call. Returns (translations, usage)."""
    values = {k: v for k, v in values.items() if v and v.strip()}
    if not values:
        return {}, {}
    payload = json.dumps(values, ensure_ascii=False)
    h = hashlib.sha256(f"{language}|{payload}".encode()).hexdigest()[:24]
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": TRANSLATE_PROMPT.format(language=language)},
            {"role": "user", "content": payload},
        ],
        "response_format": {"type": "json_object"},
    }
    res = _chat(body, f"tr_{h}_{_slug(model)}_{TRANSLATE_VERSION}")
    out = _parse_json(res["content"])
    return {k: str(out.get(k, "")) for k in values}, {**res["usage"], "cached": bool(res.get("cached"))}
