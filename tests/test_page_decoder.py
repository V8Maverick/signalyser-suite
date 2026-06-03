#!/usr/bin/env python3
"""Offline tests for the Competitor Page Decoder (tool 004).

No network and no model calls: requests.get is mocked to return sample HTML, and
sc.analyze_large is stubbed to capture its arguments instead of hitting a backend.
Run:  <suite venv python> tests/test_page_decoder.py   (exit 0 on success)
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Make the suite root importable (signalyser_core + tools.page_decoder).
SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))
sys.path.insert(0, str(SUITE_ROOT / "tools" / "page_decoder"))

import signalyser_core as sc  # noqa: E402
import decode  # noqa: E402

SAMPLE_HTML = """
<!doctype html>
<html>
  <head>
    <title>Acme — Ship faster</title>
    <style>.x { color: red; }</style>
    <script>console.log("tracking");</script>
  </head>
  <body>
    <header><nav>Home Pricing Login</nav></header>
    <div id="cookie-banner">We use cookies. Accept all?</div>
    <main>
      <h1>Acme ships your roadmap</h1>
      <p>The fastest way for product teams to plan and launch.</p>
      <ul><li>Built for startups</li><li>Loved by PMs</li></ul>
    </main>
    <footer>Copyright Acme. Privacy Terms.</footer>
  </body>
</html>
"""

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}" + (f" — {detail}" if detail else ""))
        failures.append(name)


def test_extract_strips_html() -> None:
    text = decode.extract_text(SAMPLE_HTML)
    check("extract_text returns tag-free text", "<" not in text and ">" not in text,
          repr(text[:80]))
    check("extract_text keeps body copy", "Acme ships your roadmap" in text)
    check("extract_text keeps list items", "Built for startups" in text)
    # Noise removed: scripts, styles, nav, footer chrome, cookie banner.
    check("extract_text drops <script>", "tracking" not in text and "console.log" not in text)
    check("extract_text drops <style>", "color: red" not in text)
    check("extract_text drops nav chrome", "Pricing Login" not in text)
    check("extract_text drops cookie banner", "We use cookies" not in text)
    check("extract_text drops footer", "Privacy Terms" not in text)


def test_company_slug() -> None:
    check("slug strips www + tld", decode.company_slug("https://www.notion.com") == "notion")
    check("slug from bare-ish host", decode.company_slug("https://linear.app/features") == "linear")


def test_header_contains_url_and_clean_body() -> None:
    url = "https://www.acme.com/product"
    captured: dict = {}

    def fake_get(u, *a, **k):
        return SimpleNamespace(text=SAMPLE_HTML, raise_for_status=lambda: None)

    def fake_analyze_large(system_prompt, header, body, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["header"] = header
        captured["body"] = body
        return "### Their core pitch\nstub briefing\n"

    args = SimpleNamespace(url=url, processor="local", model="qwen")

    with mock.patch.object(decode.requests, "get", side_effect=fake_get), \
         mock.patch.object(sc, "resolve_processing", return_value=("local", None)), \
         mock.patch.object(sc, "analyze_large", side_effect=fake_analyze_large), \
         mock.patch.object(sc, "load_env", return_value=None), \
         mock.patch.object(sc, "print_backend", return_value=None), \
         mock.patch.object(sc, "save_report", return_value=Path("outputs/stub.md")), \
         mock.patch.object(sc, "save_intel", return_value=Path("inputs/acme-004.md")), \
         mock.patch.object(decode.argparse.ArgumentParser, "parse_args", return_value=args):
        decode.main()

    check("prompt header contains the URL", url in captured.get("header", ""),
          repr(captured.get("header")))
    check("analyzed body is tag-free",
          "<" not in captured.get("body", "x<") and ">" not in captured.get("body", "x>"))
    check("analyzed body has page copy", "Acme ships your roadmap" in captured.get("body", ""))
    check("system prompt is the PMM briefing prompt",
          captured.get("system_prompt") == decode.SYSTEM_PROMPT)


def main() -> None:
    test_extract_strips_html()
    test_company_slug()
    test_header_contains_url_and_clean_body()
    print()
    if failures:
        print(f"{len(failures)} test(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("All page decoder tests passed.")


if __name__ == "__main__":
    main()
