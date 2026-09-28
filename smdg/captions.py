"""Platform-provided captions (YouTube json3, TikTok WebVTT) as segments + text."""
from __future__ import annotations

import json
import re


def pick_track(tracks_by_lang: dict, lang: str) -> tuple[str, list] | tuple[None, None]:
    """Exact language match first, then any code starting with it (en -> en-US, eng-US)."""
    if not tracks_by_lang:
        return None, None
    if lang in tracks_by_lang:
        return lang, tracks_by_lang[lang]
    base = lang.split("-")[0].lower()
    for code, tracks in tracks_by_lang.items():
        c = code.lower()
        if c.startswith(base) or (base == "en" and c.startswith("eng")):
            return code, tracks
    return None, None


def parse_json3(data: dict) -> list[dict]:
    segs = []
    for ev in data.get("events") or []:
        text = "".join(s.get("utf8", "") for s in ev.get("segs") or []).replace("\n", " ").strip()
        if not text:
            continue
        start = (ev.get("tStartMs") or 0) / 1000
        segs.append({"start_seconds": round(start, 3),
                     "end_seconds": round(start + (ev.get("dDurationMs") or 0) / 1000, 3),
                     "text": text})
    return segs


TS_RE = re.compile(r"(\d{1,2}:)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{1,2}:)?(\d{1,2}):(\d{2})[.,](\d{3})")


def _secs(h, m, s, ms) -> float:
    return int((h or "0:")[:-1] or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_vtt(text: str) -> list[dict]:
    """Parse WebVTT or SRT into segments, dropping cue settings and markup."""
    segs = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    for b in blocks:
        lines = [l for l in b.strip().split("\n") if l.strip()]
        for i, line in enumerate(lines):
            m = TS_RE.search(line)
            if m:
                g = m.groups()
                body = " ".join(re.sub(r"<[^>]+>", "", l).strip() for l in lines[i + 1:]).strip()
                if body:
                    segs.append({"start_seconds": round(_secs(*g[:4]), 3),
                                 "end_seconds": round(_secs(*g[4:]), 3),
                                 "text": body})
                break
    # Rolling auto-captions repeat the previous line; drop exact consecutive duplicates
    out = []
    for s in segs:
        if not out or out[-1]["text"] != s["text"]:
            out.append(s)
    return out


def parse_any(raw: str, ext: str) -> list[dict]:
    if ext == "json3":
        return parse_json3(json.loads(raw))
    return parse_vtt(raw)


def join(segs: list[dict]) -> str:
    return " ".join(s["text"] for s in segs).strip()
