#!/usr/bin/env python3
"""Offline tests for the Company Positioning Arc (tool 008).

No network and no model calls: sc.read_company_intel returns fake intel and
sc.analyze is stubbed to capture its arguments instead of hitting a backend.
Run:  <suite venv python> tests/test_positioning_arc.py   (exit 0 on success)
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Make the suite root importable (signalyser_core + tools.positioning_arc).
SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))
sys.path.insert(0, str(SUITE_ROOT / "tools" / "positioning_arc"))

import signalyser_core as sc  # noqa: E402
import arc  # noqa: E402

FAKE_INTEL = {
    "acme-002.md": "G2 reviews: customers love that Acme is 'dead simple to set up'.",
    "acme-004.md": "Website: Acme claims to be 'the all-in-one platform for growth teams'.",
}

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}" + (f" — {detail}" if detail else ""))
        failures.append(name)


def test_build_body_includes_intel_and_quadrant() -> None:
    body = arc.build_body(FAKE_INTEL, quadrant="Quadrant: Acme sits top-right.")
    check("build_body includes intel filenames", "acme-002.md" in body and "acme-004.md" in body)
    check("build_body includes intel contents", "dead simple to set up" in body)
    check("build_body folds in quadrant when present", "top-right" in body)

    body_no_q = arc.build_body(FAKE_INTEL, quadrant=None)
    check("build_body omits quadrant header when absent", "quadrant" not in body_no_q.lower())


def test_main_passes_intel_to_analyze_and_writes() -> None:
    captured: dict = {}
    written: dict = {}

    def fake_analyze(system_prompt, user_prompt, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return "## Current state\n- stub arc\n"

    # Capture the inputs/<slug>-positioning-arc.md write without touching disk.
    real_write_text = Path.write_text

    def fake_write_text(self, data, *a, **k):
        if self.name.endswith("positioning-arc.md"):
            written["path"] = self
            written["data"] = data
            return None
        return real_write_text(self, data, *a, **k)

    args = SimpleNamespace(company="Acme", processor="local", model="qwen")

    with mock.patch.object(sc, "read_company_intel", return_value=FAKE_INTEL), \
         mock.patch.object(sc, "resolve_processing", return_value=("local", None)), \
         mock.patch.object(sc, "analyze", side_effect=fake_analyze), \
         mock.patch.object(sc, "load_env", return_value=None), \
         mock.patch.object(sc, "print_backend", return_value=None), \
         mock.patch.object(sc, "save_report", return_value=Path("outputs/stub.md")), \
         mock.patch.object(arc, "read_quadrant_rationale", return_value=None), \
         mock.patch.object(Path, "write_text", new=fake_write_text), \
         mock.patch.object(arc.argparse.ArgumentParser, "parse_args", return_value=args):
        arc.main()

    check("prompt includes intel filenames", "acme-002.md" in captured.get("user_prompt", ""),
          repr(captured.get("user_prompt", "")[:80]))
    check("prompt includes intel contents",
          "dead simple to set up" in captured.get("user_prompt", ""))
    check("prompt includes the company name", "Acme" in captured.get("user_prompt", ""))
    check("system prompt is the PMM advisor prompt",
          captured.get("system_prompt") == arc.SYSTEM_PROMPT)
    check("intel file written to inputs/<slug>-positioning-arc.md",
          written.get("path") is not None
          and written["path"].name == "acme-positioning-arc.md",
          repr(written.get("path")))
    check("written intel is the analysis output", written.get("data") == "## Current state\n- stub arc\n")


def test_main_exits_when_no_intel() -> None:
    args = SimpleNamespace(company="ghost", processor="local", model="qwen")
    raised = {}

    with mock.patch.object(sc, "read_company_intel", return_value={}), \
         mock.patch.object(sc, "resolve_processing", return_value=("local", None)), \
         mock.patch.object(sc, "load_env", return_value=None), \
         mock.patch.object(sc, "print_backend", return_value=None), \
         mock.patch.object(sc, "analyze", side_effect=AssertionError("analyze must NOT be called")), \
         mock.patch.object(arc.argparse.ArgumentParser, "parse_args", return_value=args):
        try:
            arc.main()
        except SystemExit as e:
            raised["code"] = e.code

    check("empty intel exits non-zero", raised.get("code") not in (None, 0), repr(raised))


def main() -> None:
    test_build_body_includes_intel_and_quadrant()
    test_main_passes_intel_to_analyze_and_writes()
    test_main_exits_when_no_intel()
    print()
    if failures:
        print(f"{len(failures)} test(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("All positioning arc tests passed.")


if __name__ == "__main__":
    main()
