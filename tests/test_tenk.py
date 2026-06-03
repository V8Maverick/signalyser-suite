#!/usr/bin/env python3
"""Offline unit tests for the 10-K / Earnings Analyzer (tool 006).

No network: SEC HTTP calls are stubbed with an in-process fake. We verify the
two helpers that have non-trivial logic — CIK zero-padding to 10 digits, and
HTML stripping — without ever calling the real analysis backend.

Run:  .venv/Scripts/python tests/test_tenk.py   (exit 0 = all pass)
"""

import sys
from pathlib import Path

# Make both the suite root (for `import signalyser_core`) and the tool dir
# importable, regardless of the cwd the test is launched from.
SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))
sys.path.insert(0, str(SUITE_ROOT / "tools" / "tenk"))

import analyse  # noqa: E402  (the tool module under test)


# ── A tiny fake for requests.get so get_cik() never touches the network ─────────

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# A minimal company_tickers.json-shaped payload. cik_str is intentionally a small
# integer so we can assert it gets zero-padded to a 10-digit string.
_FAKE_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1108524, "ticker": "CRM", "title": "Salesforce, Inc."},
}


def _install_fake_tickers():
    """Patch analyse.requests.get to return the fake tickers payload."""
    analyse.requests.get = lambda *a, **k: _FakeResponse(_FAKE_TICKERS)


# ── Tests ───────────────────────────────────────────────────────────────────────

def test_cik_zero_pads_to_10_digits():
    _install_fake_tickers()
    cik, name = analyse.get_cik("aapl")  # lowercase to also exercise case handling
    assert cik == "0000320193", f"expected 10-digit padded CIK, got {cik!r}"
    assert len(cik) == 10, f"CIK must be exactly 10 chars, got {len(cik)}"
    assert name == "Apple Inc.", f"expected company title, got {name!r}"


def test_cik_unknown_ticker_raises():
    _install_fake_tickers()
    try:
        analyse.get_cik("NOPE")
    except ValueError:
        return
    raise AssertionError("get_cik should raise ValueError for an unknown ticker")


def test_strip_html_removes_tags():
    snippet = (
        "<html><head><style>.x{color:red}</style>"
        "<script>var a=1;</script></head><body>"
        "<h1>Item&nbsp;1A. Risk Factors</h1>"
        "<p>Our&nbsp;business faces <b>intense</b> competition &amp; risk.</p>"
        "</body></html>"
    )
    out = analyse.strip_html(snippet)
    # No tags survive.
    assert "<" not in out and ">" not in out, f"tags not fully stripped: {out!r}"
    # Script/style contents are gone entirely.
    assert "color:red" not in out, f"style block leaked: {out!r}"
    assert "var a=1" not in out, f"script block leaked: {out!r}"
    # Real text and decoded entities survive.
    assert "Risk Factors" in out, f"heading text lost: {out!r}"
    assert "intense" in out, f"bold text lost: {out!r}"
    assert "competition & risk" in out, f"entities not decoded: {out!r}"
    # Whitespace is collapsed (no double spaces, no leading/trailing).
    assert "  " not in out, f"whitespace not collapsed: {out!r}"
    assert out == out.strip(), "output should be stripped of edge whitespace"


# ── Runner ──────────────────────────────────────────────────────────────────────

def main() -> None:
    tests = [
        test_cik_zero_pads_to_10_digits,
        test_cik_unknown_ticker_raises,
        test_strip_html_removes_tags,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # unexpected error — also a failure
            failures += 1
            print(f"FAIL  {t.__name__}: unexpected {type(e).__name__}: {e}")

    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
