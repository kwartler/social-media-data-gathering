"""Live smoke test: feed real example links (tests/smoke_urls.json) to the app,
the same way the input boxes do, and report what works.

It talks to the app over its local web API, so it can test the source code or a
packaged download. Each run uses a throwaway settings folder, so it never
touches your real one.

    python scripts/smoke_test.py                      # test the source code
    python scripts/smoke_test.py --app path/to/social-media-data-gathering.app
    python scripts/smoke_test.py --model              # also run a few videos through the model
    python scripts/smoke_test.py --only tiktok

Reddit and Bluesky search are skipped unless their credentials are set as
environment variables (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, BLUESKY_HANDLE,
BLUESKY_APP_PASSWORD). --model needs OPENROUTER_API_KEY and costs a few cents.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tests" / "smoke_urls.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "smdg" / "document.schema.json").read_text(encoding="utf-8"))
PORT = 8019
BASE_OPTS = {"llm": False, "pseudonymize": "none", "include_identifiable": False, "comments": 0}
REQUIRES = {
    "reddit": ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"),
    "bluesky": ("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"),
    "model": ("OPENROUTER_API_KEY",),
}


def start_app(app_path: str | None) -> tuple[subprocess.Popen, str]:
    home = tempfile.mkdtemp(prefix="smdg-smoke-home-")
    env = {**os.environ, "HOME": home, "USERPROFILE": home, "SMDG_PORT": str(PORT), "SMDG_NO_BROWSER": "1"}
    if app_path:
        p = Path(app_path)
        if p.suffix == ".app":
            p = p / "Contents" / "MacOS" / p.stem
        cmd = [str(p)]
    else:
        cmd = [sys.executable, str(ROOT / "app.py")]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{PORT}"
    for _ in range(60):
        try:
            httpx.get(base, timeout=2)
            return proc, base
        except httpx.HTTPError:
            time.sleep(1)
    proc.kill()
    raise SystemExit(f"The app did not start on port {PORT}. Is something else using that port?")


def ndjson(client: httpx.Client, path: str, body: dict) -> list[dict]:
    with client.stream("POST", path, json=body, timeout=900) as r:
        if r.status_code >= 400:
            r.read()
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        return [json.loads(line) for line in r.iter_lines() if line.strip()]


def check_docs(client: httpx.Client, zip_name: str, expect: dict) -> str | None:
    """Download the export and check it; returns a problem description or None."""
    try:
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(SCHEMA)
    except ImportError:
        validator = None
    data = client.get(f"/api/exports/{zip_name}", timeout=120).content
    docs = [json.loads(l) for l in zipfile.ZipFile(io.BytesIO(data)).read("corpus.jsonl").decode().splitlines()]
    if validator:
        errs = [e.message for d in docs for e in validator.iter_errors(d)]
        if errs:
            return f"schema: {errs[0][:120]}"
    post = docs[0]
    if len(docs) < expect.get("min_docs", 1):
        return f"expected at least {expect['min_docs']} documents, got {len(docs)}"
    if "caption_source" in expect and post["caption_source"] != expect["caption_source"]:
        return f"caption_source was {post['caption_source']!r}"
    for field in ("visual_description", "llm_transcript"):
        if expect.get(field) and not post[field]:
            return f"{field} is empty ({post['llm_error'] or 'no error given'})"
    if expect.get("visual_description") and not post["ai_generated"]:
        return "ai_generated is false"
    return None


def missing(requires: str | None) -> str | None:
    if requires and not all(os.environ.get(v) for v in REQUIRES[requires]):
        return "skipped: set " + " and ".join(REQUIRES[requires])
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", help="Packaged app to test (.app on Mac, .exe on Windows). Default: source code.")
    ap.add_argument("--model", action="store_true", help="Also run a few videos through the model (costs a few cents).")
    ap.add_argument("--only", help="Only test one tab, e.g. tiktok")
    args = ap.parse_args()

    proc, base = start_app(args.app)
    client = httpx.Client(base_url=base)
    results = []

    def record(section, case, status, detail="", secs=0.0):
        results.append((section, case.get("tab", "-"), case["name"], status, detail, secs))
        if status == "FAIL" and case.get("best_effort"):
            status = "WARN"  # known to be intermittent on the platform's side; doesn't fail the run
        results[-1] = results[-1][:3] + (status,) + results[-1][4:]
        mark = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "skip", "WARN": "warn"}[status]
        print(f"  {mark:<4}  {case['name']:<45} {detail}", flush=True)

    def wanted(case):
        return not args.only or case.get("tab") == args.only

    try:
        sections = [("collect", CASES["collect"])]
        if args.model:
            sections.append(("model", CASES["model"]))
        for section, cases in sections:
            print(f"\n{section.upper()}")
            for case in filter(wanted, cases):
                skip = missing("model" if section == "model" else case.get("requires"))
                if skip:
                    record(section, case, "SKIP", skip)
                    continue
                opts = {**BASE_OPTS, **({"llm": True} if section == "model" else {}), **case.get("options", {})}
                t0 = time.time()
                try:
                    events = ndjson(client, "/api/collect", {"inputs": [case["input"]], "options": opts})
                    item = next(e for e in events if e.get("event") == "item")
                    done = next(e for e in events if e.get("event") == "done")
                    if not item["ok"]:
                        record(section, case, "FAIL", item["error"][:150], time.time() - t0)
                        continue
                    problem = check_docs(client, done["zip"], case.get("expect", {}))
                    record(section, case, "FAIL" if problem else "PASS",
                           problem or f"{item['n_docs']} doc(s)", time.time() - t0)
                except Exception as e:
                    record(section, case, "FAIL", str(e)[:150], time.time() - t0)
                time.sleep(2)

        print("\nLIST ACCOUNTS")
        for case in filter(wanted, CASES["list"]):
            skip = missing(case.get("requires"))
            if skip:
                record("list", case, "SKIP", skip)
                continue
            t0 = time.time()
            try:
                events = ndjson(client, "/api/list", {"input": case["input"], "limit": case["limit"]})
                errs = [e["error"] for e in events if e.get("event") == "error"]
                n = sum(1 for e in events if "url" in e)
                if errs or not n:
                    record("list", case, "FAIL", (errs[0] if errs else "no posts returned")[:150], time.time() - t0)
                else:
                    record("list", case, "PASS", f"{n} post(s)", time.time() - t0)
            except Exception as e:
                record("list", case, "FAIL", str(e)[:150], time.time() - t0)
            time.sleep(2)

        print("\nSEARCH")
        for case in filter(wanted, CASES["search"]):
            skip = missing(case.get("requires"))
            if skip:
                record("search", case, "SKIP", skip)
                continue
            t0 = time.time()
            try:
                events = ndjson(client, "/api/search", {"platform": case["platform"], "query": case["query"],
                                                        "limit": case["limit"]})
                errs = [e["error"] for e in events if e.get("event") == "error"]
                n = sum(1 for e in events if "url" in e)
                record("search", case, "FAIL" if errs or not n else "PASS",
                       (errs[0][:150] if errs else f"{n} result(s)") if (errs or n) else "no results", time.time() - t0)
            except Exception as e:
                record("search", case, "FAIL", str(e)[:150], time.time() - t0)

        if not args.only:
            print("\nREJECTED ON PURPOSE")
            res = client.post("/api/classify", json={"inputs": [c["input"] for c in CASES["rejected"]]}).json()
            for case, r in zip(CASES["rejected"], res):
                record("rejected", case, "FAIL" if r["ok"] else "PASS",
                       "was accepted" if r["ok"] else r["error"][:90])
    finally:
        try:
            client.post("/api/shutdown", timeout=5)
        except httpx.HTTPError:
            pass
        time.sleep(3)
        if proc.poll() is None:
            proc.kill()

    passed = sum(r[3] == "PASS" for r in results)
    failed = sum(r[3] == "FAIL" for r in results)
    skipped = sum(r[3] == "SKIP" for r in results)
    warned = sum(r[3] == "WARN" for r in results)
    print(f"\n{passed} passed, {failed} failed, {warned} best-effort warnings, {skipped} skipped")
    if warned:
        print("Warnings are best-effort features (TikTok profile listing) that the platform refused this time; retry later.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
