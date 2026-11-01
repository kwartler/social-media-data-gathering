"""FastAPI server: serves the SPA and exposes collection endpoints.

Run with:  python app.py
Or via the packaged binary, which auto-opens the browser.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from smdg import classify, config, errors, llm, pipeline, ytdlp_sites


# ---------------------------------------------------------------------------
# Paths (work in both dev and PyInstaller-frozen mode)
# ---------------------------------------------------------------------------

def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / rel


STATIC_DIR = resource_path("static")
PORT = int(os.environ.get("SMDG_PORT", "8010"))  # override only to run a second copy for testing

app = FastAPI(title="Social Media Data Gathering")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CollectBody(BaseModel):
    inputs: list[str]
    options: dict = {}


class ListBody(BaseModel):
    input: str
    limit: int = 25
    sort: str = "new"


class SearchBody(BaseModel):
    platform: str
    query: str
    limit: int = 25
    sort: str = "latest"
    subreddit: str = ""


class SettingsBody(BaseModel):
    openrouter_api_key: Optional[str] = None
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None
    bluesky_handle: Optional[str] = None
    bluesky_app_password: Optional[str] = None
    model: Optional[str] = None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _ndjson(gen):
    def wrapped():
        try:
            for obj in gen:
                yield json.dumps(obj, ensure_ascii=False, default=str) + "\n"
        except Exception as e:
            msg = str(e) if isinstance(e, (ValueError, PermissionError, LookupError, RuntimeError)) else errors.friendly(e)
            yield json.dumps({"event": "error", "error": msg}) + "\n"
    return StreamingResponse(wrapped(), media_type="application/x-ndjson")


@app.post("/api/classify")
def classify_inputs(body: CollectBody):
    out = []
    for raw in body.inputs:
        try:
            t = classify.classify(raw)
            out.append({"input": raw, "ok": True, "platform": t["platform"], "kind": t["kind"]})
        except ValueError as e:
            out.append({"input": raw, "ok": False, "error": str(e)})
    return out


@app.post("/api/list")
def list_account(body: ListBody):
    try:
        classify.classify(body.input)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _ndjson(pipeline.list_account(body.input, max(1, min(body.limit, 1000)), body.sort))


@app.post("/api/search")
def search(body: SearchBody):
    return _ndjson(pipeline.search(body.platform, body.query, max(1, min(body.limit, 1000)), body.sort, body.subreddit))


@app.post("/api/collect")
def collect(body: CollectBody):
    inputs = [s.strip() for s in body.inputs if s.strip()]
    if not inputs:
        raise HTTPException(400, "Nothing to collect.")
    return _ndjson(pipeline.run(inputs, body.options))


@app.get("/api/exports/{name}")
def download_export(name: str):
    path = (config.EXPORT_DIR / name).resolve()
    if path.parent != config.EXPORT_DIR.resolve() or not path.exists():
        raise HTTPException(404, "Export not found.")
    return FileResponse(str(path), media_type="application/zip", filename=name)


@app.get("/api/youtube/languages")
def youtube_languages(url: str):
    try:
        t = classify.classify(url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if t["platform"] != "youtube" or t["kind"] != "post":
        raise HTTPException(400, "Not a YouTube video link.")
    try:
        return ytdlp_sites.youtube_languages(t["url"])
    except Exception as e:
        raise HTTPException(500, f"Failed to list languages: {e}")


class FolderBody(BaseModel):
    path: str = ""


@app.post("/api/check-folder")
def check_folder(body: FolderBody):
    try:
        return {"ok": True, "path": str(config.check_folder(body.path))}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/choose-folder")
def choose_folder():
    """Open the operating system's folder picker (the app runs on the student's own computer)."""
    import subprocess
    prompt = "Choose where to save copies of videos and images"
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["osascript", "-e", "tell me to activate",
                                "-e", f'POSIX path of (choose folder with prompt "{prompt}")'],
                               capture_output=True, text=True, timeout=900)
            if r.returncode != 0:
                return {"cancelled": True}
            return {"path": r.stdout.strip().rstrip("/") or "/"}
        if sys.platform == "win32":
            ps = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
                  f"$f.Description = '{prompt}'; $f.ShowNewFolderButton = $true;"
                  "$owner = New-Object System.Windows.Forms.Form -Property @{TopMost = $true};"
                  "if ($f.ShowDialog($owner) -eq 'OK') { $f.SelectedPath }")
            r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps],
                               capture_output=True, text=True, timeout=900,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            path = r.stdout.strip()
            return {"path": path} if path else {"cancelled": True}
    except Exception as e:
        return {"error": f"Could not open the folder picker: {e}. Type the folder path instead."}
    return {"error": "No folder picker on this system. Type the folder path instead."}


@app.post("/api/open-folder")
def open_folder(body: FolderBody):
    """Show a kept-copies folder in Finder or File Explorer (only folders this app created)."""
    import subprocess
    p = Path(body.path).expanduser()
    if not (p.is_dir() and p.name.startswith("social_media_corpus_") and p.name.endswith("_media")):
        raise HTTPException(400, "Not a folder of kept copies.")
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    elif sys.platform == "win32":
        os.startfile(str(p))  # noqa: S606 (a folder this app created)
    else:
        subprocess.Popen(["xdg-open", str(p)])
    return {"ok": True}


@app.get("/api/models")
def models():
    try:
        return {"default": config.DEFAULT_MODEL, "models": llm.list_models()}
    except Exception as e:
        raise HTTPException(502, f"Could not load the OpenRouter model list: {e}")


@app.get("/api/settings")
def get_settings():
    return config.public_view()


@app.post("/api/settings")
def save_settings(body: SettingsBody):
    config.update(body.model_dump())
    return config.public_view()


@app.get("/api/log")
def collection_log(limit: int = 200):
    if not config.LOG_PATH.exists():
        return []
    lines = config.LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(l) for l in reversed(lines) if l.strip()]


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

@app.post("/api/shutdown")
def shutdown():
    """Gracefully stop the server. Called by the in-browser Quit button."""
    def _kill():
        time.sleep(0.3)  # let the response reach the browser first
        os.kill(os.getpid(), signal.SIGTERM)
        # Worker threads from a finished collection can keep the interpreter
        # alive after uvicorn stops; force the exit if that happens.
        time.sleep(2.0)
        os._exit(0)
    threading.Thread(target=_kill, daemon=True).start()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Static SPA
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"error": "static/index.html missing"}, 500)


# ---------------------------------------------------------------------------
# Auto-update yt-dlp on startup (best-effort)
# ---------------------------------------------------------------------------

def _try_self_update_ytdlp():
    """Try to upgrade yt-dlp in the background. Safe to fail."""
    def run():
        try:
            import subprocess
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "yt-dlp"],
                timeout=60,
                check=False,
            )
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    import uvicorn

    url = f"http://127.0.0.1:{PORT}"

    # If a server is already running, just (re-)open the browser and wait.
    # We intentionally keep this Terminal window open rather than exiting
    # immediately: macOS treats an app that quits in under ~5 s as a crash
    # and will block future launches with "not open anymore".
    if _port_in_use(PORT):
        print(f"\nSocial Media Data Gathering is already running at {url}")
        print("Opening browser... close this window whenever you like.\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            input()  # keep the Terminal alive until the user closes it
        except (EOFError, KeyboardInterrupt):
            pass
        return

    config.clear_temp_exports()

    # Auto-update yt-dlp in the background (no-op when running as a frozen binary)
    if not getattr(sys, "frozen", False):
        _try_self_update_ytdlp()

    # Open browser shortly after the server starts
    def open_browser():
        time.sleep(1.0)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    if not os.environ.get("SMDG_NO_BROWSER"):
        threading.Thread(target=open_browser, daemon=True).start()

    print(f"\nSocial Media Data Gathering running at {url}\nPress Ctrl+C to stop.\n")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
