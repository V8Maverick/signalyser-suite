"""Offline tests for the Competitive Quadrant tool.

No network, no LLM: we feed a canned JSON string to the parse function and call
the plotting function on sample data (Agg backend). The real sc.analyze is never
called.

Run:  .venv/bin/python tests/test_quadrant.py   (exit 0 = all pass)
"""
import sys
import tempfile
from pathlib import Path

# Make the suite root and the quadrant tool importable when run directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "quadrant"))

import quadrant as q

failures = []

def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


# ── (a) parse_response: plain JSON ───────────────────────────────────────────────

CANNED_JSON = """\
{
  "x_axis": {"label": "Self-serve vs Sales-led", "low": "Pure self-serve", "high": "Enterprise sales-led"},
  "y_axis": {"label": "Breadth of platform", "low": "Single point tool", "high": "End-to-end suite"},
  "companies": [
    {"name": "Acme", "x": -6.0, "y": 3.5, "rationale": "PLG motion, narrow tool."},
    {"name": "Globex", "x": 7.5, "y": 8.0, "rationale": "Field sales, full suite."}
  ]
}"""

data = q.parse_response(CANNED_JSON)
check("parse extracts x_axis label", data["x_axis"]["label"] == "Self-serve vs Sales-led")
check("parse extracts y_axis label", data["y_axis"]["label"] == "Breadth of platform")
check("parse extracts both companies", len(data["companies"]) == 2)
check("parse keeps company coords", data["companies"][0]["x"] == -6.0 and data["companies"][1]["y"] == 8.0)
check("parse keeps company name", data["companies"][1]["name"] == "Globex")


# ── (a') parse_response: strips ```json fences ───────────────────────────────────

FENCED = "```json\n" + CANNED_JSON + "\n```"
data_fenced = q.parse_response(FENCED)
check("parse strips ```json fences", data_fenced["x_axis"]["label"] == "Self-serve vs Sales-led")
check("parse strips fences keeps companies", len(data_fenced["companies"]) == 2)

# bare ``` fence (no language tag)
BARE = "```\n" + CANNED_JSON + "\n```"
check("parse strips bare ``` fence", q.parse_response(BARE)["y_axis"]["label"] == "Breadth of platform")


# ── (a'') parse_response: failures raise (so main can exit 1) ─────────────────────

try:
    q.parse_response("not json at all {")
    check("malformed JSON raises", False)
except Exception:
    check("malformed JSON raises", True)

try:
    q.parse_response('{"x_axis": {}, "y_axis": {}}')  # missing companies
    check("missing key raises", False)
except ValueError:
    check("missing key raises", True)


# ── (b) plot_quadrant: writes a PNG to a temp dir (Agg, no LLM) ───────────────────

SAMPLE = {
    "x_axis": {"label": "X", "low": "lo", "high": "hi"},
    "y_axis": {"label": "Y", "low": "lo", "high": "hi"},
    "companies": [
        {"name": "Acme", "x": -6.0, "y": 3.5, "rationale": "r1"},
        {"name": "Globex", "x": 7.5, "y": 8.0, "rationale": "r2"},
        {"name": "Initech", "x": 1.0, "y": -4.0, "rationale": "r3"},
    ],
}

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "quadrant-1.png"
    returned = q.plot_quadrant(SAMPLE, out)
    check("plot returns the output path", returned == out)
    check("plot writes a PNG file", out.exists())
    check("plot PNG is non-empty", out.exists() and out.stat().st_size > 0)
    # PNG magic number
    check("plot output is a real PNG", out.exists() and out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n")

    # plot creates a missing parent dir
    nested = Path(tmp) / "sub" / "deep" / "quadrant-1.png"
    q.plot_quadrant(SAMPLE, nested)
    check("plot creates missing parent dirs", nested.exists())


# ── build_rationale_md sanity (offline, pure string) ─────────────────────────────

md = q.build_rationale_md(SAMPLE)
check("rationale md has axes section", "## X-axis: X" in md and "## Y-axis: Y" in md)
check("rationale md lists each company", "### Acme" in md and "### Globex" in md and "### Initech" in md)


print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
