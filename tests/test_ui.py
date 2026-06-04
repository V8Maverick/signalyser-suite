#!/usr/bin/env python3
"""
Offline test for the v1/v2 UI switch.

Asserts that the sticky UI_VERSION selects the dashboard (v2) vs the original
tool-cards (v1) on /tools, that the v2 theme assets load only under v2, and that
the /ui/<version> toggle persists. Snapshots and restores .env + UI_VERSION.

Run: <venv-python> tests/test_ui.py   (exit 0 = PASS)
"""

import os
import sys
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))

from signalyser_core.env import ENV_FILE
import signalyser_web.settings as settings_mod
from fastapi.testclient import TestClient
from signalyser_web.app import app


def main() -> None:
    failures = []
    env_backup = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else None
    ui_backup = os.environ.get("UI_VERSION")

    c = TestClient(app)
    try:
        # v2 → dashboard
        settings_mod.set_ui_version("v2")
        r = c.get("/tools")
        if "intake-urls" not in r.text or "Signal" not in r.text:
            failures.append("v2 /tools did not render the dashboard")
        if "app_v2.css" not in r.text:
            failures.append("v2 did not load the v2 theme stylesheet")

        # v1 → original tool cards, no v2 assets
        settings_mod.set_ui_version("v1")
        r = c.get("/tools")
        if "tool-card" not in r.text:
            failures.append("v1 /tools did not render the original tool cards")
        if "app_v2.css" in r.text:
            failures.append("v1 leaked the v2 theme stylesheet")

        # the toggle persists
        c.get("/ui/v2", follow_redirects=False)
        if settings_mod.ui_version() != "v2":
            failures.append("/ui/v2 did not switch the sticky UI version")
        c.get("/ui/bogus", follow_redirects=False)
        if settings_mod.ui_version() != "v2":
            failures.append("an invalid UI version was not coerced to v2")
    finally:
        if env_backup is not None:
            ENV_FILE.write_text(env_backup, encoding="utf-8")
        if ui_backup is not None:
            os.environ["UI_VERSION"] = ui_backup
        else:
            os.environ.pop("UI_VERSION", None)

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS  ui: v1/v2 switch selects dashboard vs cards, assets scoped, toggle sticky")


if __name__ == "__main__":
    main()
