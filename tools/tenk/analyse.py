#!/usr/bin/env python3
"""
10-K / 20-F SEC filing analyser — PMM competitive intelligence.

Pulls a company's most recent annual filing from SEC EDGAR, strips it to plain
text, and runs it through the shared Signalyser analysis backend (local Ollama
with map-reduce, or cloud Anthropic in a single pass) to produce a structured
PMM signal report.

Usage:
    python analyse.py CRM
    python analyse.py MSFT -p cloud -m opus-4.8
    python analyse.py MNDY -p local
"""

# Self-heal: re-exec under the suite .venv so signalyser_core and third-party deps
# resolve no matter which Python / working dir launched this tool. See _bootstrap.py.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if __name__ == "__main__":
    import _bootstrap
    _bootstrap.ensure_venv(__file__)

import re
import sys
import argparse
from datetime import datetime

import requests

import signalyser_core as sc

# ── SEC EDGAR config ───────────────────────────────────────────────────────────

# SEC requires a descriptive User-Agent that identifies the requester.
HEADERS = {"User-Agent": "signalyser-suite (contact@example.com)"}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"

# Cap input — enough to cover the narrative sections the analysis needs.
MAX_CHARS = 200_000


# ── SEC fetch helpers ──────────────────────────────────────────────────────────


def get_cik(ticker: str) -> tuple[str, str]:
    """Return (zero-padded 10-digit CIK, company name) for a ticker symbol."""
    resp = requests.get(TICKERS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    ticker_upper = ticker.upper()
    for entry in resp.json().values():
        if entry["ticker"].upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10), entry["title"]
    raise ValueError(f"Ticker '{ticker}' not found in EDGAR company list")


def get_latest_annual_filing(cik: str) -> dict:
    """Fetch the submissions JSON and return metadata for the most recent 10-K or 20-F."""
    url = SUBMISSIONS_URL.format(cik=cik)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    filings = data["filings"]["recent"]
    for i, form in enumerate(filings["form"]):
        if form in ("10-K", "20-F"):
            return {
                "form_type": form,
                "accession": filings["accessionNumber"][i],
                "primary_doc": filings["primaryDocument"][i],
                "filing_date": filings["filingDate"][i],
            }

    raise ValueError(
        f"No 10-K or 20-F found in recent filings for CIK {cik}. "
        "The company may have too many historical filings; check EDGAR directly."
    )


def strip_html(html: str) -> str:
    """Strip HTML tags and decode common entities, returning plain text."""
    # Remove script / style blocks entirely.
    html = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Drop all remaining tags.
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode the handful of entities that show up in filings.
    replacements = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&apos;": "'",
    }
    for ent, char in replacements.items():
        html = html.replace(ent, char)
    # Collapse whitespace.
    return re.sub(r"\s+", " ", html).strip()


def fetch_filing_text(cik: str, filing: dict) -> tuple[str, str]:
    """Download the primary annual filing document; return (plain_text, source_url)."""
    cik_int = str(int(cik))  # archive URL path uses the integer CIK (no leading zeros)
    accession_no_dashes = filing["accession"].replace("-", "")
    primary_doc = filing["primary_doc"]

    url = ARCHIVES_URL.format(
        cik=cik_int,
        accession=accession_no_dashes,
        doc=primary_doc,
    )
    print(f"  URL: {url}")

    resp = requests.get(url, headers=HEADERS, timeout=90)
    resp.raise_for_status()

    text = resp.text
    if primary_doc.lower().endswith((".htm", ".html")):
        text = strip_html(text)

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[Document truncated at 200,000 characters for analysis]"

    return text, url


# ── Analysis ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior Product Marketing Manager (PMM) specialising in competitive intelligence. \
You read SEC annual filings (10-K and 20-F) to surface strategic signals that matter to \
competing or partnering PMMs.

Your analysis is precise, opinionated, and actionable. You quote directly from filings. \
You highlight what changed, not just what exists. You skip boilerplate and go straight to signal.

Produce the report using EXACTLY the section headers below. Do not add extra sections. \
Quote the filing directly wherever it strengthens a point.

## 10-K Signal Report: {TICKER}

### How they describe their market and customers
Analyse the specific language, terminology, and framing used to describe their TAM, \
customer segments, use cases, and ICP. Quote key phrases verbatim. Note any evolution \
in who they say they serve.

### Where they're investing vs pulling back
Identify R&D priorities, new product bets, headcount signals, capex trends, geographic \
moves, and any areas of divestment or reduced emphasis. Use specific numbers where available.

### Risk factors a competitor PMM should know
Surface the most strategically revealing admissions — vulnerabilities they acknowledge, \
market threats they name, competitive pressures they flag, and regulatory exposure. \
Quote from the risk factors section.

### Competitors they name and how they frame them
List every named competitor or competitive category. Analyse the framing: minimising, \
acknowledging, or repositioning? Note any significant competitors conspicuously absent.

### Narrative shifts from prior year
Identify what is new, what is de-emphasised, and what language has changed. What themes \
are rising? What was prominent before that is now buried or gone?

### PMM actions
5–7 specific, tactical actions a competing or partnering PMM should take based on these \
signals. Be direct and concrete.\
"""


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse a company's latest SEC 10-K/20-F for PMM competitive signals."
    )
    parser.add_argument("ticker", help="stock ticker symbol, e.g. CRM")
    sc.add_processing_args(parser)
    args = parser.parse_args()

    ticker = args.ticker.upper()

    print(f"\n{'=' * 58}")
    print(f"  10-K / 20-F Analyser  ·  {ticker}")
    print(f"{'=' * 58}\n")

    # Load .env and resolve the processing backend (sticky -p/-m via .env).
    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    print(f"\n[1/4] Looking up CIK for {ticker}...")
    try:
        cik, company_name = get_cik(ticker)
    except (requests.HTTPError, ValueError) as e:
        print(f"  Error: {e}")
        sys.exit(1)
    print(f"  {company_name}  (CIK: {cik})\n")

    print("[2/4] Finding most recent annual filing (10-K or 20-F)...")
    try:
        filing = get_latest_annual_filing(cik)
    except (requests.HTTPError, ValueError) as e:
        print(f"  Error: {e}")
        sys.exit(1)
    form_type = filing["form_type"]
    print(f"  {form_type}  ·  Filed {filing['filing_date']}  ·  {filing['primary_doc']}\n")

    print("[3/4] Fetching document...")
    try:
        doc_text, doc_url = fetch_filing_text(cik, filing)
    except requests.HTTPError as e:
        print(f"  Error fetching filing: {e}")
        sys.exit(1)
    print(f"  {len(doc_text):,} characters\n")

    print("[4/4] Analysing...\n")
    analysis_date = datetime.now().strftime("%Y-%m-%d")
    header = (
        f"{form_type} for {ticker}\n"
        f"Company: {company_name}\n"
        f"Filing date: {filing['filing_date']}\n"
        f"Analysis date: {analysis_date}\n"
        f"Source: {doc_url}"
    )
    system_prompt = SYSTEM_PROMPT.replace("{TICKER}", ticker)

    report = sc.analyze_large(
        system_prompt,
        header=header,
        body=doc_text[:MAX_CHARS],
        processor=processor,
        model_key=model_key,
    )

    # Save the report and feed it into the shared cross-tool intel corpus.
    report_path = sc.save_report(f"{ticker}-10k", report)
    intel_path = sc.save_intel(ticker, sc.SOURCE_IDS["tenk"], report)

    print(f"\n{'=' * 58}")
    print("  Done!")
    print(f"  Report : {report_path}")
    print(f"  Intel  : {intel_path}")
    print(f"  Source : {doc_url}")
    print(f"{'=' * 58}\n")


if __name__ == "__main__":
    main()
