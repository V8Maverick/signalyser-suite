#!/usr/bin/env python3
"""
Offline test for sessions (signalyser_core.io + the web Sessions manager).

Covers: creating/switching/listing/deleting sessions, that INPUTS_DIR/OUTPUTS_DIR
and read/write helpers track the active session, that two sessions are isolated,
and the web routes (GET /sessions, POST new/switch/delete). No network/LLM.

Snapshots and restores the sticky SESSION + .env so the user's config is untouched.

Run: <venv-python> tests/test_sessions.py   (exit 0 = PASS)
"""

import os
import sys
import shutil
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))

import signalyser_core as sc
from signalyser_core.env import ENV_FILE

A = "zz-test-session-a"
B = "zz-test-session-b"


def main() -> None:
    failures = []

    # Snapshot what we will mutate so we can restore it.
    env_backup = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else None
    session_backup = os.environ.get("SESSION")

    def cleanup():
        for name in (A, B):
            shutil.rmtree(sc.SESSIONS_ROOT / name, ignore_errors=True)
        if env_backup is not None:
            ENV_FILE.write_text(env_backup, encoding="utf-8")
        if session_backup is not None:
            os.environ["SESSION"] = session_backup
        else:
            os.environ.pop("SESSION", None)

    try:
        # ── Core ────────────────────────────────────────────────────────────────
        sc.create_session(A)
        sc.set_active_session(A)
        if sc.active_session() != A:
            failures.append(f"active_session != {A} after switch")
        if sc.INPUTS_DIR != sc.SESSIONS_ROOT / A / "inputs":
            failures.append("INPUTS_DIR did not track the active session")
        if A not in sc.list_sessions():
            failures.append(f"{A} missing from list_sessions")

        # Write intel into A, then prove B can't see it (isolation).
        sc.save_intel("acme", "004", "intel for A")
        sc.set_active_session(B)            # auto-creates on first dir access
        sc.create_session(B)
        if sc.read_company_intel("acme"):
            failures.append("session B sees session A's intel (not isolated)")
        # Back to A — the intel is there.
        sc.set_active_session(A)
        if "acme-004.md" not in sc.read_company_intel("acme"):
            failures.append("session A lost its own intel after round-trip")

        # Per-session "our company" (active is A here).
        sc.set_own_company("AcmeCo")
        if sc.get_own_company() != "AcmeCo":
            failures.append("own company not set for session A")
        sc.set_active_session(B)
        if sc.get_own_company():
            failures.append("session B leaked session A's own company")
        sc.set_active_session(A)

        # Delete A.
        sc.set_active_session(B)
        sc.delete_session(A)
        if (sc.SESSIONS_ROOT / A).exists():
            failures.append("delete_session did not remove the folder")

        # ── Web ─────────────────────────────────────────────────────────────────
        from fastapi.testclient import TestClient
        from signalyser_web.app import app
        c = TestClient(app)

        r = c.get("/sessions")
        if r.status_code != 200 or "Sessions" not in r.text:
            failures.append("GET /sessions did not render")

        # Create + switch via the web.
        c.post("/sessions/new", data={"name": A}, follow_redirects=False)
        if sc.active_session() != A:
            failures.append("POST /sessions/new did not create+switch")

        # Switch back to B via the web.
        c.post("/sessions/switch", data={"name": B}, follow_redirects=False)
        if sc.active_session() != B:
            failures.append("POST /sessions/switch did not switch")

        # Deleting the ACTIVE session falls back to 'default'.
        c.post("/sessions/delete", data={"name": B}, follow_redirects=False)
        if sc.active_session() != sc.DEFAULT_SESSION:
            failures.append("deleting the active session did not fall back to default")

        # Per-session "our company" via the web route.
        c.post("/sessions/new", data={"name": A}, follow_redirects=False)
        c.post("/session/own", data={"own_company": "WebCo"}, follow_redirects=False)
        if sc.get_own_company() != "WebCo":
            failures.append("POST /session/own did not set the session's own company")

    finally:
        cleanup()

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS  sessions: create/switch/list/delete, isolation, web routes")


if __name__ == "__main__":
    main()
