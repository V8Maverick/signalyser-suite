#!/usr/bin/env python3
"""
Job Posting Analyzer — PMM Signal Report.

Fetches a company's current open roles from Ashby's public posting API (falling
back to Greenhouse), builds a compact digest, and sends it to the shared
Signalyser analysis backend — local Ollama/Qwen or cloud Anthropic/Claude — to
surface hiring signals: where they're hiring, repeated keywords, technology
signals, inferred strategic priorities, and concrete PMM actions.

Usage:
    python analyse.py <slug> [-p local|cloud] [-m MODEL]
    python analyse.py notion
    python analyse.py vercel -p cloud -m opus-4.8

The processor (-p) and cloud model (-m) are sticky — once set they persist in
.env for every run until changed (handled by the shared core).
"""

# Self-heal: re-exec under the suite .venv so signalyser_core and third-party deps
# resolve no matter which Python / working dir launched this tool. See _bootstrap.py.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if __name__ == "__main__":
    import _bootstrap
    _bootstrap.ensure_venv(__file__)

import sys
import re
import html
import argparse
from pathlib import Path

import requests

# Make the suite root importable when run directly from tools/job_postings/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import signalyser_core as sc

# ── Config ──────────────────────────────────────────────────────────────────

ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

DESCRIPTION_CAP = 1500  # max chars of each job description kept in the digest
REQUEST_TIMEOUT = 12     # seconds per HTTP request


# ── HTML → plain text ─────────────────────────────────────────────────────────

def strip_html(raw: str) -> str:
    """Strip HTML tags and decode entities, preserving rough block structure."""
    if not raw:
        return ""
    # Preserve newlines from common block elements before stripping tags.
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|li|h[1-6]|div|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)          # remaining tags
    text = html.unescape(text)                    # entities
    text = re.sub(r"\n{3,}", "\n\n", text)        # collapse blank lines
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ── Job fetchers ──────────────────────────────────────────────────────────────

def fetch_ashby(slug: str) -> list[dict]:
    """Fetch open roles from Ashby's public posting API (no auth).

    Returns a normalised list of {title, department, location, description}.
    Returns [] if the board is missing or has no postings.
    """
    url = ASHBY_URL.format(slug=slug)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        raw_jobs = resp.json().get("jobs", [])
    except Exception:
        return []
    if not raw_jobs:
        return []

    jobs = []
    for j in raw_jobs:
        dept = j.get("department")
        dept_name = dept.get("name", "Unknown") if isinstance(dept, dict) else (dept or "Unknown")
        loc = j.get("location")
        loc_name = loc.get("name", "") if isinstance(loc, dict) else (loc or "")
        desc_html = j.get("descriptionHtml") or j.get("description") or ""
        jobs.append({
            "title": j.get("title", "Untitled"),
            "department": dept_name,
            "location": loc_name,
            "description": strip_html(desc_html)[:DESCRIPTION_CAP],
        })
    return jobs


def fetch_greenhouse(slug: str) -> list[dict]:
    """Fallback: fetch open roles from the Greenhouse boards JSON API (no auth).

    Returns the same normalised shape as fetch_ashby.
    """
    url = GREENHOUSE_URL.format(slug=slug)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        raw_jobs = resp.json().get("jobs", [])
    except Exception:
        return []
    if not raw_jobs:
        return []

    jobs = []
    for j in raw_jobs:
        dept_list = j.get("departments") or []
        dept_name = dept_list[0].get("name", "Unknown") if dept_list else "Unknown"
        loc_list = j.get("offices") or []
        loc_name = loc_list[0].get("name", "") if loc_list else ""
        # Greenhouse single-location field as a fallback.
        if not loc_name and isinstance(j.get("location"), dict):
            loc_name = j["location"].get("name", "")
        content_html = j.get("content", "")
        jobs.append({
            "title": j.get("title", "Untitled"),
            "department": dept_name,
            "location": loc_name,
            "description": strip_html(content_html)[:DESCRIPTION_CAP],
        })
    return jobs


def fetch_jobs(slug: str) -> tuple[list[dict], str]:
    """Try Ashby first, then Greenhouse. Returns (jobs, source_name)."""
    print("  Fetching from Ashby...", flush=True)
    jobs = fetch_ashby(slug)
    if jobs:
        return jobs, "Ashby"

    print("  Ashby returned no roles. Trying Greenhouse...", flush=True)
    jobs = fetch_greenhouse(slug)
    if jobs:
        return jobs, "Greenhouse"

    return [], "none"


# ── Digest builder ────────────────────────────────────────────────────────────

def build_digest(slug: str, jobs: list[dict], source: str) -> str:
    """Serialise the job list into a compact text block for analysis."""
    lines = [
        f"Company: {slug}",
        f"Source: {source}",
        f"Total open roles: {len(jobs)}",
        "",
    ]
    for i, j in enumerate(jobs, 1):
        lines.append(f"--- Job {i} ---")
        lines.append(f"Title: {j['title']}")
        lines.append(f"Department: {j['department']}")
        if j.get("location"):
            lines.append(f"Location: {j['location']}")
        if j.get("description"):
            lines.append(f"Description snippet:\n{j['description'][:DESCRIPTION_CAP]}")
        lines.append("")
    return "\n".join(lines)


# ── Analysis prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior Product Marketing Manager (PMM) and competitive intelligence \
analyst. Your job is to read a company's current open job postings and extract \
strategic go-to-market signals.

Your analysis must be grounded in the actual text of the job postings. Cite \
specific patterns, phrases, and department concentrations as evidence. Do not \
speculate beyond what the postings show. Be specific, opinionated, and \
actionable. Write for a senior PMM audience.

Produce a signal report in **exactly** this markdown format (keep the headers \
verbatim):

## Job Signal Report: {company}

### Where they're hiring (by department)
List departments and their role counts. Call out which are growing fastest by \
volume, and note any unusual concentrations or absences.

### Repeated keywords across postings
Pull the 10–15 most-repeated meaningful phrases, terms, or requirements across \
postings. Explain what each cluster signals about company direction.

### Technology and tool signals
List specific technologies, platforms, frameworks, and tools mentioned, grouped \
by category (infrastructure, data, product, GTM, etc.). Note what's absent but \
expected.

### Inferred strategic priorities
Infer 3–5 strategic bets the company is making, each supported by 2–3 specific \
signals from the postings.

### PMM action items
Give 4–6 concrete, specific, numbered actions a PMM at a competing or adjacent \
company should take in response to these signals. Be tactical — not "monitor \
their website" but "reposition your [X] messaging to counter their push into [Y]."
"""


def build_user_prompt(slug: str, digest: str) -> str:
    return (
        f"Here are the current open job postings for **{slug}**. "
        "Analyze them for PMM-relevant signals and produce the report as "
        "instructed in the system prompt.\n\n"
        f"{digest}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def extract_slug(arg: str) -> str:
    """Accept a bare slug or a full Ashby/Greenhouse job-board URL."""
    arg = arg.strip()
    m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", arg)
    if m:
        return m.group(1).lower()
    m = re.search(r"boards\.greenhouse\.io/([^/?#]+)", arg)
    if m:
        return m.group(1).lower()
    return arg.lower().lstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze a company's open job postings for PMM signals "
                    "(Ashby with Greenhouse fallback)."
    )
    parser.add_argument(
        "slug",
        help="company job-board slug or URL, e.g. notion or "
             "https://jobs.ashbyhq.com/dash0",
    )
    sc.add_processing_args(parser)
    args = parser.parse_args()

    slug = extract_slug(args.slug)

    # Load .env and resolve the backend (sticky via .env).
    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    print(f"\nAnalyzing job postings for '{slug}'...\n")

    jobs, source = fetch_jobs(slug)
    if not jobs:
        print(f"\nNo job board found on Ashby or Greenhouse for '{slug}'.")
        print("Check the slug spelling and try again.")
        sys.exit(1)

    print(f"  Found {len(jobs)} open roles via {source}.\n")

    digest = build_digest(slug, jobs, source)
    report = sc.analyze(
        SYSTEM_PROMPT,
        build_user_prompt(slug, digest),
        processor=processor,
        model_key=model_key,
    )
    print("\n" + "=" * 70 + "\n")

    if not report.strip():
        print("Error: analysis returned an empty response.")
        sys.exit(1)

    report_path = sc.save_report(f"{slug}-jobs", report)
    intel_path = sc.save_intel(slug, sc.SOURCE_IDS["jobs"], report)
    print(f"Report saved: {report_path}")
    print(f"Intel saved:  {intel_path}\n")


if __name__ == "__main__":
    main()
