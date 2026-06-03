#!/usr/bin/env python3
"""
Competitor Page Decoder — fetch a competitor's web page, strip it to clean
visible text, and have a senior PMM decode their positioning into a strategic
briefing.

Usage: python3 decode.py <url> [-p local|cloud] [-m MODEL]

The processor (-p) and cloud model (-m) are sticky: once set they persist in
.env for every tool in the suite until changed. See the shared signalyser_core.

The briefing is saved two ways:
  - a timestamped report in outputs/        (sc.save_report)
  - a company intel file in inputs/<slug>-004.md, joining the shared corpus the
    rest of the suite reads (sc.save_intel)
"""

import re
import sys
import argparse
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

import signalyser_core as sc

# ── Config ──────────────────────────────────────────────────────────────────

# A browser-like User-Agent — many marketing sites 403 the default requests UA.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# Whole tags whose contents are never page substance — dropped entirely.
NOISE_TAGS = ["nav", "footer", "header", "aside", "script", "style", "noscript", "iframe"]

# Elements whose class/id signals site chrome or a cookie/consent banner.
NOISE_CLASSES = re.compile(
    r"(cookie|consent|banner|modal|popup|overlay|toast|announcement|"
    r"nav|navbar|navigation|footer|sidebar|breadcrumb)",
    re.I,
)

SYSTEM_PROMPT = """\
You are a senior Product Marketing Manager doing competitive intelligence. \
Given the visible text of a competitor's web page, decode their positioning into \
a tight, strategic briefing. Be specific, quote their exact language where it is \
revealing, and avoid generic filler.

Respond using EXACTLY this markdown structure (keep the headers verbatim):

### Their core pitch
One crisp sentence capturing what they claim to do and for whom.

### Who they're targeting
2-3 bullets on the buyer persona, company size, and pain points the page signals.

### Top 3 positioning bets
A numbered list. Each bet = the claim they are leaning on + why it matters competitively.

### What they're NOT saying
2-3 bullets on notable omissions, weaknesses they avoid, or topics conspicuously absent.

### PMM actions
3 concrete next steps for your team (messaging to sharpen, gaps to exploit, content to create)."""


# ── Fetch + extract ───────────────────────────────────────────────────────────

def fetch_page(url: str) -> str:
    """GET the URL with a browser-like UA; exit with a clear error on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        sys.exit(f"Error fetching {url}: {e}")


def extract_text(html: str) -> str:
    """Strip nav/footer/chrome/cookie noise and collapse to clean visible text."""
    soup = BeautifulSoup(html, "lxml")

    # Drop whole noise tags (script/style/nav/footer/...).
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    # Drop elements whose class/id marks them as chrome or a cookie banner.
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag) or not tag.attrs:
            continue
        classes = " ".join(tag.get("class", []))
        tag_id = tag.get("id") or ""
        if NOISE_CLASSES.search(classes) or NOISE_CLASSES.search(tag_id):
            tag.decompose()

    # Collapse whitespace: trim each line, drop blanks.
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def company_slug(url: str) -> str:
    """Derive a company slug from the URL domain.

    https://www.notion.com/product -> 'notion'
    """
    host = urlparse(url).netloc.lower()
    host = re.sub(r"^www\.", "", host)
    host = host.split(":")[0]                 # drop any :port
    label = host.split(".")[0] if host else host
    return sc.slugify(label) or sc.slugify(host)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decode a competitor's web page into a PMM positioning briefing."
    )
    parser.add_argument("url", help="competitor page URL, e.g. https://www.notion.com")
    sc.add_processing_args(parser)
    args = parser.parse_args()

    url = args.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    slug = company_slug(url)

    print(f"\nFetching {url}...")
    html = fetch_page(url)

    print("Extracting visible text...")
    clean_text = extract_text(html)
    if not clean_text:
        sys.exit(f"Error: no readable text extracted from {url}.")
    print(f"Extracted {len(clean_text):,} characters.\n")

    report = sc.analyze_large(
        SYSTEM_PROMPT,
        header=f"Competitor page: {url}",
        body=clean_text,
        processor=processor,
        model_key=model_key,
    )

    print("\n" + "=" * 70 + "\n")

    out = sc.save_report(f"{slug}-page", report)
    intel = sc.save_intel(slug, sc.SOURCE_IDS["page"], report)
    print(f"Report saved:  {out}")
    print(f"Intel saved:   {intel}\n")


if __name__ == "__main__":
    main()
