#!/usr/bin/env python3
"""
Offline test for the CTA Tracker (012).

Mocks the model (sc.analyze) but runs the real matplotlib heatmap. Feeds a small
on-disk corpus via --inputs, designates our company, and asserts: the prompt flags
our company, a PNG heatmap + a markdown report are written, the report marks "us",
and is_own is enforced from our setting (not trusted from the model).

Run: <venv-python> tests/test_cta_tracker.py   (exit 0 = PASS)
"""

import sys
import tempfile
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))
sys.path.insert(0, str(SUITE_ROOT / "tools" / "cta_tracker"))

import signalyser_core as sc
import cta

CANNED = """```json
{
  "themes": ["Free delivery", "Guarantee"],
  "companies": [
    {"name": "ourco", "is_own": false, "scores": {"Free delivery": 8, "Guarantee": 3},
     "primary_ctas": ["Free next-day delivery"], "usps": ["fastest dispatch"]},
    {"name": "rival", "is_own": true, "scores": {"Free delivery": 2, "Guarantee": 9},
     "primary_ctas": ["Lifetime guarantee"], "usps": ["lifetime guarantee"]}
  ],
  "our_position": {"gaining": ["delivery speed"], "losing": ["guarantee length"],
                   "our_usps": ["next-day"], "their_usps": ["lifetime guarantee"]}
}
```"""


def main() -> None:
    failures = []
    captured = {}

    def fake_analyze(system_prompt, user_prompt, *, processor, model_key, **kw):
        captured["user"] = user_prompt
        return CANNED

    cta.sc.analyze = fake_analyze
    cta.sc.load_env = lambda: None
    cta.sc.resolve_processing = lambda args: ("local", None)
    cta.sc.print_backend = lambda p, m: None

    out_before = set(sc.outputs_dir().glob("cta-tracker_*.png"))
    md_before = set(sc.outputs_dir().glob("cta-tracker_*.md"))
    new_png = set()
    new_md = set()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "ourco-004.md").write_text("OurCo: free next-day delivery.", encoding="utf-8")
        (tmpdir / "rival-005.md").write_text("Rival: lifetime guarantee.", encoding="utf-8")

        sys.argv = ["cta.py", "--inputs", str(tmpdir), "--own", "ourco"]
        try:
            cta.main()

            if "OUR COMPANY is OURCO" not in captured.get("user", ""):
                failures.append("prompt did not flag our company")

            new_png = set(sc.outputs_dir().glob("cta-tracker_*.png")) - out_before
            new_md = set(sc.outputs_dir().glob("cta-tracker_*.md")) - md_before
            if not new_png:
                failures.append("no heatmap PNG written")
            else:
                png = next(iter(new_png))
                if png.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                    failures.append("heatmap is not a valid PNG")
            if not new_md:
                failures.append("no report markdown written")
            else:
                report = next(iter(new_md)).read_text(encoding="utf-8")
                if "**Our company:** ourco" not in report:
                    failures.append("report missing our-company header")
                # is_own enforced from our setting: ourco is us, despite the model
                # marking 'rival' as is_own=true.
                if "### ourco *(us)*" not in report:
                    failures.append("report did not mark ourco as us (is_own not enforced)")
                if "### rival *(us)*" in report:
                    failures.append("rival wrongly marked as us")
                if "## Us vs them" not in report:
                    failures.append("report missing the us-vs-them section")
        finally:
            for p in new_png | new_md:
                p.unlink(missing_ok=True)

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS  cta tracker: heatmap + report, our-company enforced")


if __name__ == "__main__":
    main()
