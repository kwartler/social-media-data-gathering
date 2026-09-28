"""Run a collection: each input -> rows (+ optional OpenRouter extraction) -> export folder and zip."""
from __future__ import annotations

import csv
import io
import json
import random
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Iterator

from . import bluesky, classify, config, errors, llm, reddit, truthsocial, ytdlp_sites
from .records import COLUMNS, SEGMENT_COLUMNS, TRANSLATABLE, now_iso, pseudonymize

__version__ = "0.2.0"

COLLECTORS = {
    "youtube": ytdlp_sites.collect,
    "tiktok": ytdlp_sites.collect,
    "instagram": ytdlp_sites.collect,
    "facebook": ytdlp_sites.collect,
    "bluesky": bluesky.collect,
    "reddit": reddit.collect,
    "truthsocial": truthsocial.collect,
    "other": ytdlp_sites.collect,
}

# Seconds to pause between items, per platform, to stay under rate limits
PAUSE = {"youtube": 1.5, "tiktok": 2.0, "instagram": 4.0, "facebook": 3.0, "bluesky": 0.3, "reddit": 1.0, "truthsocial": 5.0, "other": 2.0}

DEFAULT_OPTS = {
    "comments": 0,
    "caption_lang": "en",
    "llm": True,
    "model": config.DEFAULT_MODEL,
    "max_media_seconds": 300,
    "pseudonymize": "everyone",  # everyone, commenters, or none
    "include_identifiable": True,
    "keep_media": False,
    "youtube_source": "captions",  # captions (timedtext), model, or both
    "translate_to": "",            # e.g. "English"; empty means no translation
}

# Characters of text per translation request; longer posts are split across calls
TRANSLATE_CHUNK = 12000


def list_account(raw: str, limit: int, sort: str = "new") -> Iterator[dict]:
    t = classify.classify(raw)
    if t["kind"] != "account":
        raise ValueError("That is a single post, not an account. Use Collect instead.")
    if t["platform"] in ("youtube", "tiktok"):
        yield from ytdlp_sites.list_account(t, limit)
    elif t["platform"] == "bluesky":
        yield from bluesky.list_account(t, limit)
    elif t["platform"] == "reddit":
        yield from reddit.list_account(t, limit, sort)
    elif t["platform"] == "truthsocial":
        yield from truthsocial.list_account(t, limit)


def search(platform: str, query: str, limit: int, sort: str = "latest", subreddit: str = "") -> Iterator[dict]:
    if platform == "youtube":
        yield from ytdlp_sites.search_youtube(query, limit)
    elif platform == "bluesky":
        yield from bluesky.search(query, limit, "top" if sort == "top" else "latest")
    elif platform == "reddit":
        yield from reddit.search(query, limit, "top" if sort == "top" else "new", subreddit)
    else:
        raise ValueError(f"Search is not available for {platform}.")


def _apply_llm(result: dict, opts: dict) -> dict:
    """Fill model-extracted columns on the post row. Returns usage info for the manifest."""
    post = result["rows"][0]
    fetch = result.get("fetch_media")
    if not opts.get("llm") or not fetch:
        return {}
    model = opts.get("model") or config.DEFAULT_MODEL
    if not config.get("openrouter_api_key"):
        post["llm_error"] = "No OpenRouter API key set, so model extraction was skipped. Add one in Settings."
        return {}
    post["llm_model"] = model
    media_dir = None
    try:
        got = fetch()
        if not got:
            post["llm_error"] = "No downloadable media found in this post."
            return {}
        kind, files = got
        media_dir = files[0].parent if files else None
        if kind == "video":
            files = [ytdlp_sites.shrink_video(f) for f in files]
        out = llm.extract(files, kind, model)
    except Exception as e:
        post["llm_error"] = errors.friendly(e) if not isinstance(e, llm.LLMError) else str(e)
        return {}
    finally:
        if media_dir and not opts.get("keep_media"):
            shutil.rmtree(media_dir, ignore_errors=True)

    segs = [sg for sg in out.get("transcript_segments") or [] if isinstance(sg, dict) and sg.get("text")]
    post["llm_transcript"] = "\n".join(f"{sg.get('speaker') or '?'}: {sg['text']}" for sg in segs)
    post["speakers"] = [
        {"id": str(sp.get("id", "")), "description": str(sp.get("description", "")), "on_screen": bool(sp.get("on_screen"))}
        for sp in out.get("speakers") or [] if isinstance(sp, dict)
    ]
    ost = out.get("on_screen_text") or []
    post["on_screen_text"] = " | ".join(ost) if isinstance(ost, list) else str(ost)
    post["visual_description"] = out.get("visual_description") or ""
    post["audio_description"] = out.get("audio_description") or ""
    if not post["language"] and out.get("language") not in (None, "", "und"):
        post["language"] = out["language"]
    post["ai_generated"] = True
    post["llm_model"] = out.get("_model_used") or model
    for sg in segs:
        result["segments"].append({"doc_id": post["doc_id"], "source": "llm", "speaker": sg.get("speaker") or "?",
                                   "start_seconds": sg.get("start_seconds"), "end_seconds": "", "text": sg["text"]})
    usage = out.get("_usage") or {}
    return {"cached": bool(out.get("_cached")), "cost": usage.get("cost"),
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}


def _apply_translation(result: dict, opts: dict) -> dict:
    """Translate the post and its comments into opts["translate_to"], filling translated_* fields."""
    language = (opts.get("translate_to") or "").strip()
    if not language:
        return {}
    rows = result["rows"]
    if not config.get("openrouter_api_key"):
        rows[0]["llm_error"] = (rows[0]["llm_error"] + " " if rows[0]["llm_error"] else "") + \
            "No OpenRouter API key set, so translation was skipped."
        return {}
    model = opts.get("model") or config.DEFAULT_MODEL
    # One request per chunk of {row index|field: text}
    pending, chunks, size = {}, [], 0
    for i, r in enumerate(rows):
        for src in TRANSLATABLE:
            text = r.get(src) or ""
            if text.strip():
                if size + len(text) > TRANSLATE_CHUNK and pending:
                    chunks.append(pending)
                    pending, size = {}, 0
                pending[f"{i}|{src}"] = text
                size += len(text)
    if pending:
        chunks.append(pending)
    cost = 0.0
    try:
        for chunk in chunks:
            out, usage = llm.translate(chunk, language, model)
            cost += usage.get("cost") or 0
            for key, val in out.items():
                i, src = key.split("|", 1)
                rows[int(i)][TRANSLATABLE[src]] = val
    except Exception as e:
        msg = str(e) if isinstance(e, llm.LLMError) else errors.friendly(e)
        rows[0]["llm_error"] = (rows[0]["llm_error"] + " " if rows[0]["llm_error"] else "") + f"Translation failed: {msg}"
        return {"cost": cost}
    for r in rows:
        r["translation_language"] = language
        if any(r.get(t) for t in TRANSLATABLE.values()):
            r["ai_generated"] = True
            r["llm_model"] = r["llm_model"] or model
    return {"cost": cost, "requests": len(chunks)}


def _log(entry: dict) -> None:
    with open(config.LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(inputs: list[str], opts: dict) -> Iterator[dict]:
    """Collect every input, yielding progress events; the last event names the zip."""
    opts = {**DEFAULT_OPTS, **{k: v for k, v in (opts or {}).items() if v is not None}}
    job_id = time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    started = now_iso()
    all_rows, all_segments, raws, timedtext, items = [], [], {}, {}, []
    yield {"event": "start", "job_id": job_id, "total": len(inputs)}

    last_platform = None
    for i, raw_input in enumerate(inputs):
        entry = {"input": raw_input, "job_id": job_id, "requested_at": now_iso()}
        try:
            target = classify.classify(raw_input)
            entry["platform"] = target["platform"]
            if target["kind"] != "post":
                raise ValueError("This is an account, not a post. Use List posts to choose posts from it.")
            if last_platform == target["platform"]:
                time.sleep(PAUSE.get(target["platform"], 1.0) * (0.75 + random.random() / 2))
            last_platform = target["platform"]
            target["input"] = raw_input
            result = COLLECTORS[target["platform"]](target, opts)
            usage = _apply_llm(result, opts)
            tr_usage = _apply_translation(result, opts)
            if tr_usage:
                usage = {**usage, "translation_cost": tr_usage.get("cost"),
                         "cost": (usage.get("cost") or 0) + (tr_usage.get("cost") or 0)}
            post = result["rows"][0]
            all_rows.extend(result["rows"])
            all_segments.extend(result["segments"])
            raws[post["doc_id"]] = result["raw"]
            timedtext.update(result.get("timedtext") or {})
            entry.update(ok=True, doc_id=post["doc_id"], n_docs=len(result["rows"]),
                         llm_error=post["llm_error"] or None, llm_usage=usage or None)
            preview = post["title"] or post["text"] or post["caption_transcript"] or post["llm_transcript"] or post["visual_description"]
            yield {"event": "item", "i": i, "input": raw_input, "ok": True, "platform": target["platform"],
                   "n_docs": len(result["rows"]), "llm_error": post["llm_error"],
                   "preview": preview[:240], "cost": (usage or {}).get("cost")}
        except Exception as e:
            msg = str(e) if isinstance(e, (ValueError, PermissionError, LookupError)) else errors.friendly(e)
            entry.update(ok=False, error=msg)
            yield {"event": "item", "i": i, "input": raw_input, "ok": False, "error": msg,
                   "platform": entry.get("platform")}
        items.append(entry)
        _log(entry)

    manifest = {
        "job_id": job_id,
        "app": "social-media-data-gathering",
        "app_version": __version__,
        "started_at": started,
        "finished_at": now_iso(),
        "options": {k: v for k, v in opts.items()},
        "llm_prompt": llm.prompt_record() if opts.get("llm") else None,
        "items": items,
        "n_documents": len(all_rows),
        "total_llm_cost_usd": round(sum((it.get("llm_usage") or {}).get("cost") or 0 for it in items), 6),
    }
    zip_path = export(job_id, all_rows, all_segments, raws, timedtext, manifest, opts)
    yield {"event": "done", "job_id": job_id, "n_docs": len(all_rows),
           "ok": sum(1 for it in items if it.get("ok")), "failed": sum(1 for it in items if not it.get("ok")),
           "cost": manifest["total_llm_cost_usd"], "zip": zip_path.name}


INT_COLUMNS = {"like_count", "reply_count", "share_count", "view_count"}


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def to_document(row: dict, segments: list[dict]) -> dict:
    """One corpus row in the common JSON schema (smdg/document.schema.json)."""
    doc = {}
    for c in COLUMNS:
        v = row.get(c)
        if c in INT_COLUMNS:
            doc[c] = _as_int(v)
        elif c == "ai_generated":
            doc[c] = bool(v)
        elif c == "speakers":
            doc[c] = v if isinstance(v, list) else []
        else:
            doc[c] = "" if v is None else str(v)
    doc["segments"] = [
        {"source": s["source"],
         "speaker": s.get("speaker") or "",
         "start_seconds": s.get("start_seconds") if s.get("start_seconds") != "" else None,
         "end_seconds": s.get("end_seconds") if s.get("end_seconds") != "" else None,
         "text": s["text"]}
        for s in segments
    ]
    return doc


def _cell(v):
    if v is True or v is False:
        return "TRUE" if v else "FALSE"
    if isinstance(v, list):  # speakers
        return " | ".join(f"{sp['id']}: {sp['description']}" + (" (on screen)" if sp.get("on_screen") else "")
                          for sp in v if isinstance(sp, dict))
    return "" if v is None else v


def _csv(rows: list[dict], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: _cell(v) for k, v in r.items()})
    return buf.getvalue()


def export(job_id: str, rows, segments, raws, timedtext, manifest, opts) -> Path:
    mode = opts.get("pseudonymize")
    mode = {True: "everyone", False: "none", None: "none"}.get(mode, mode)
    rows, key, names = pseudonymize(rows, mode)
    by_doc: dict[str, list] = {}
    for sg in segments:
        by_doc.setdefault(sg["doc_id"], []).append(sg)
    here = Path(__file__).parent
    zip_path = config.EXPORT_DIR / f"social_media_corpus_{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("corpus.jsonl", "".join(
            json.dumps(to_document(r, by_doc.get(r["doc_id"], [])), ensure_ascii=False) + "\n" for r in rows))
        z.writestr("corpus.csv", _csv(rows, COLUMNS))
        z.writestr("segments.csv", _csv(segments, SEGMENT_COLUMNS))
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
        z.writestr("document.schema.json", (here / "document.schema.json").read_text(encoding="utf-8"))
        z.writestr("codebook.md", (here / "codebook.md").read_text(encoding="utf-8"))
        for name, data in timedtext.items():
            z.writestr(f"timedtext/{name}", data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))
        if opts.get("include_identifiable"):
            if key:
                z.writestr("identifiable/linking_key.csv", _csv(key, ["doc_id", "pseudonym", "author", "author_id", "url"]))
                z.writestr("identifiable/pseudonym_key.csv", _csv(names, ["pseudonym", "platform", "kind", "original"]))
            for doc_id, raw in raws.items():
                z.writestr(f"identifiable/raw/{doc_id}.json", json.dumps(raw, ensure_ascii=False, default=str))
    return zip_path
