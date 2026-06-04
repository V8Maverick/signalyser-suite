#!/usr/bin/env python3
"""
Offline test for the Signalyser web front end (signalyser_web).

Drives the FastAPI app via fastapi.testclient.TestClient — no real uvicorn
server, no network, and NEVER a real LLM. The one end-to-end run uses a company
with no intel files, so the persona tool exits 1 fast (before any model call).

Settings are persisted to the shared .env; this test snapshots and restores the
PROCESSOR it touches and never writes a real API key.

Run: <venv-python> tests/test_web.py   (exit 0 = PASS)
"""

import os
import sys
from pathlib import Path

# Make the suite root importable (signalyser_web + signalyser_core).
SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))

from fastapi.testclient import TestClient

from signalyser_core.env import ENV_FILE
import signalyser_web.settings as s
from signalyser_web.app import app


def main() -> None:
    failures = []
    c = TestClient(app)

    # Snapshot the raw .env up front so we can restore the user's config exactly
    # (byte-for-byte). update_settings can only create/update keys, never remove
    # one we add, so rewriting the file is the only fully non-destructive option.
    env_existed = ENV_FILE.exists()
    env_snapshot = ENV_FILE.read_text(encoding="utf-8") if env_existed else None
    # Also snapshot the live env vars we mutate, to restore the running process.
    proc_snapshot = os.environ.get("PROCESSOR")
    model_snapshot = os.environ.get("CLOUD_MODEL")

    try:
        # 1. The four pages render with their expected content.
        page_checks = {
            "/tools": "Collect",
            "/corpus": "corpus",
            "/reports": "reports",
            "/settings": "Settings",
        }
        for path, expected in page_checks.items():
            r = c.get(path)
            if r.status_code != 200:
                failures.append(f"GET {path} returned {r.status_code}, expected 200")
            elif expected.lower() not in r.text.lower():
                failures.append(f"GET {path} body missing expected text {expected!r}")

        # 2. POST /run with an unknown tool -> 400 JSON {ok: false}.
        r = c.post("/run", data={"tool": "definitely_not_a_tool"})
        if r.status_code != 400:
            failures.append(f"unknown tool: status {r.status_code}, expected 400")
        else:
            body = r.json()
            if body.get("ok") is not False:
                failures.append(f"unknown tool: ok is {body.get('ok')!r}, expected False")
            if "definitely_not_a_tool" not in body.get("error", ""):
                failures.append("unknown tool: error does not name the bad tool")

        # 3. POST /run missing a required field (page with no url) -> 400 naming it.
        # Force local so the cloud gate does not fire first.
        s.update_settings(processor="local")
        r = c.post("/run", data={"tool": "page"})
        if r.status_code != 400:
            failures.append(f"missing field: status {r.status_code}, expected 400")
        else:
            body = r.json()
            if body.get("ok") is not False:
                failures.append(f"missing field: ok is {body.get('ok')!r}, expected False")
            err = body.get("error", "").lower()
            if "url" not in err or "required" not in err:
                failures.append("missing field: error does not mention the required URL field")

        # 4. Run-validation gating: cloud processor + no API key -> 400 about the key.
        # We force cloud WITHOUT writing a real key; restore happens in finally.
        # A model must be set, else the gate stops at "needs a model" first.
        s.update_settings(processor="cloud", model="sonnet-4.6")
        if s.get_settings()["has_api_key"]:
            # The user genuinely has a key set — can't exercise the no-key gate
            # without destroying their config, so skip this single assertion.
            print("NOTE: ANTHROPIC_API_KEY present; skipping no-key cloud gate check")
        else:
            r = c.post("/run", data={"tool": "personas", "company": "anything"})
            if r.status_code != 400:
                failures.append(f"cloud gate: status {r.status_code}, expected 400")
            else:
                body = r.json()
                if body.get("ok") is not False:
                    failures.append(f"cloud gate: ok is {body.get('ok')!r}, expected False")
                err = body.get("error", "")
                if "API_KEY" not in err.upper() or "Settings" not in err:
                    failures.append("cloud gate: error does not mention API key / Settings")

        # 5. End-to-end streaming with no network/LLM. Force local, run personas on a
        # company with no intel: the tool exits 1 fast (before any model call).
        s.update_settings(processor="local")
        r = c.post("/run", data={"tool": "personas",
                                 "company": "zzweb_smoke_nonexistent"})
        if r.status_code != 200:
            failures.append(f"local run: status {r.status_code}, expected 200")
        else:
            body = r.json()
            if body.get("ok") is not True:
                failures.append(f"local run: ok is {body.get('ok')!r}, expected True")
            job_id = body.get("job_id")
            if not job_id:
                failures.append("local run: no job_id returned")
            else:
                with c.stream("GET", f"/stream/{job_id}") as resp:
                    stream_body = "".join(resp.iter_text())
                # NOTE: never print the raw body — it may contain non-cp1252 chars
                # that crash the Windows console.
                has_data = "data:" in stream_body
                has_done = "event: done" in stream_body
                # personas exits with: "No intel for ... run collectors first"
                has_no_intel = ("no intel" in stream_body.lower()
                                or "collector" in stream_body.lower())
                if not has_data:
                    failures.append("stream: no `data:` lines found")
                if not has_done:
                    failures.append("stream: no `event: done` line found")
                if not has_no_intel:
                    failures.append("stream: missing the tool's no-intel/collector message")
    finally:
        # 6. Restore the user's .env and process env exactly as we found them.
        if env_snapshot is not None:
            ENV_FILE.write_text(env_snapshot, encoding="utf-8")
        elif ENV_FILE.exists():
            ENV_FILE.unlink()
        for key, val in (("PROCESSOR", proc_snapshot), ("CLOUD_MODEL", model_snapshot)):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
