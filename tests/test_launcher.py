#!/usr/bin/env python3
"""
Offline test for the top-level launcher (signalyser.py).

Verifies the command table points at scripts that actually exist, the help /
unknown-command exit codes, and that a valid command forwards its remaining args
to the tool via subprocess (subprocess.run is monkeypatched — no tool is run).

Run: <venv-python> tests/test_launcher.py   (exit 0 = PASS)
"""

import sys
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))

import signalyser


def main() -> None:
    failures = []

    # 1. Every command maps to a tool script that exists on disk.
    for name, (rel, _desc) in signalyser.COMMANDS.items():
        if not (SUITE_ROOT / rel).exists():
            failures.append(f"command {name!r} points at missing script: {rel}")

    # 2. All 8 adapted tools + reddit are wired up.
    for expected in ("reddit", "page", "jobs", "tenk", "youtube",
                     "personas", "arc", "quadrant", "assets"):
        if expected not in signalyser.COMMANDS:
            failures.append(f"launcher missing command: {expected}")

    # 3. help / no args -> 0; unknown -> 2.
    if signalyser.main([]) != 0:
        failures.append("no-args did not return 0")
    if signalyser.main(["help"]) != 0:
        failures.append("help did not return 0")
    if signalyser.main(["bogus-cmd"]) != 2:
        failures.append("unknown command did not return 2")

    # 4. A valid command forwards args to the tool via subprocess.
    captured = {}

    class FakeProc:
        returncode = 7

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    real_run = signalyser.subprocess.run
    signalyser.subprocess.run = fake_run
    try:
        rc = signalyser.main(["jobs", "notion", "-p", "cloud"])
    finally:
        signalyser.subprocess.run = real_run

    if rc != 7:
        failures.append(f"launcher did not propagate tool returncode (got {rc})")
    cmd = captured.get("cmd", [])
    if not cmd or cmd[0] != sys.executable:
        failures.append("launcher did not run the tool with the current interpreter")
    if "analyse.py" not in "".join(str(c) for c in cmd):
        failures.append("launcher did not target the jobs tool script")
    if cmd[-3:] != ["notion", "-p", "cloud"]:
        failures.append(f"launcher did not forward tool args unchanged: {cmd[-3:]}")

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS  launcher: dispatch table + help/unknown codes + arg forwarding")


if __name__ == "__main__":
    main()
