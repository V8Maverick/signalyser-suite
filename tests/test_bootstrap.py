#!/usr/bin/env python3
"""
Offline test for the venv self-heal bootstrap (_bootstrap.py + the per-tool shim).

Regression guard for: running a tool with the *wrong* Python (e.g. the system
interpreter, which lacks the editable install + deps) used to fail with
`ModuleNotFoundError: signalyser_core`. Each tool now re-execs itself under the
suite .venv. This test proves that by launching a tool with a non-venv Python and
asserting it still succeeds.

Run: <venv-python> tests/test_bootstrap.py   (exit 0 = PASS)
"""

import os
import sys
import subprocess
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))

import _bootstrap


def _non_venv_python() -> str | None:
    """A real Python interpreter that is NOT the suite venv (the base/system one)."""
    candidates = [
        os.path.join(sys.base_prefix, "python.exe"),          # Windows base
        os.path.join(sys.base_prefix, "bin", "python3"),       # POSIX base
        os.path.join(sys.base_prefix, "bin", "python"),
    ]
    venv_py = os.path.realpath(sys.executable)
    for c in candidates:
        if os.path.exists(c) and os.path.realpath(c) != venv_py:
            return c
    return None


def main() -> None:
    failures = []

    # 1. ensure_venv is a no-op when already under the venv (we are, in tests):
    #    it must return without re-execing / exiting.
    tool = SUITE_ROOT / "tools" / "page_decoder" / "decode.py"
    try:
        _bootstrap.ensure_venv(str(tool))  # should simply return
    except SystemExit:
        failures.append("ensure_venv re-execed even though we're under the venv")

    # 2. _find_root locates the suite root (the dir with .venv / pyproject.toml)
    #    from a tool two directories deep.
    found = _bootstrap._find_root(str(tool))
    if Path(found).resolve() != SUITE_ROOT:
        failures.append(f"_find_root returned {found!r}, expected {SUITE_ROOT}")

    # 3. The real fix: launch a tool with a NON-venv Python and confirm it
    #    self-heals (re-execs under .venv) and runs to a clean --help.
    other = _non_venv_python()
    if other is None:
        print("NOTE: no non-venv Python found — skipping the live self-heal check.")
    else:
        for rel in ("tools/page_decoder/decode.py", "tools/personas/personas.py"):
            proc = subprocess.run(
                [other, str(SUITE_ROOT / rel), "--help"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if proc.returncode != 0:
                failures.append(f"{rel} under non-venv Python exited {proc.returncode} "
                                f"(stderr: {proc.stderr.strip()[:120]})")
            elif "usage:" not in proc.stdout.lower():
                failures.append(f"{rel} under non-venv Python printed no usage text")

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS  bootstrap: tools self-heal under a non-venv Python")


if __name__ == "__main__":
    main()
