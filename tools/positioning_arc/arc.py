#!/usr/bin/env python3
"""
Company Positioning Arc — read everything the suite knows about a company and
have a senior PMM advise its CMO with a three-horizon positioning arc:
Current state -> Horizon 1 (defend) -> Horizon 2 (move) -> Horizon 3 (own).

Usage: python3 arc.py --company <name> [-p local|cloud] [-m MODEL]

The processor (-p) and cloud model (-m) are sticky: once set they persist in
.env for every tool in the suite until changed. See the shared signalyser_core.

Intelligence is read from the shared inputs/ corpus (sc.read_company_intel) —
the G2/reddit/page/jobs/10-K files the rest of the suite collects. If a
competitive-quadrant axes rationale exists (outputs/axes-rationale.md or
tools/quadrant/axes-rationale.md) it is folded in too; if not, it's skipped.

The arc is saved two ways:
  - a timestamped report in outputs/                  (sc.save_report)
  - a company intel file in inputs/<slug>-positioning-arc.md, joining the shared
    corpus so the asset generator can read it downstream.
"""

# Self-heal: re-exec under the suite .venv so signalyser_core and third-party deps
# resolve no matter which Python / working dir launched this tool. See _bootstrap.py.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if __name__ == "__main__":
    import _bootstrap
    _bootstrap.ensure_venv(__file__)

import sys
import argparse
from pathlib import Path

import signalyser_core as sc

# ── Config ──────────────────────────────────────────────────────────────────

# Optional competitive-quadrant rationale. Read if present, ignored if not — the
# quadrant tool is built by another agent, so we never hard-depend on it.
QUADRANT_CANDIDATES = [
    sc.OUTPUTS_DIR / "axes-rationale.md",
    sc.SUITE_ROOT / "tools" / "quadrant" / "axes-rationale.md",
]

SYSTEM_PROMPT = """\
You are a senior Product Marketing Manager acting as strategic advisor to the \
company's CMO. From the source intelligence provided (customer voice, website \
positioning, job-posting signals, financials, competitive context), produce a \
three-horizon positioning arc. Use the EXACT language from the sources wherever \
it is revealing — quote real phrases customers and the company use. Be specific \
to this company; reject any advice that could apply to any B2B SaaS company.

Respond using EXACTLY this markdown structure (keep the headers verbatim):

## Current state
- **Inferred positioning:** What the company currently claims to be and for whom.
- **Claimed vs perceived gap:** What they say vs what customers actually say — quote both sides.
- **Biggest vulnerability:** The single competitive weakness most exposed right now.

## Horizon 1 (0-6 months): Defend and sharpen
- **Core positioning claim:** The claim to lead with now.
- **Proof points available today:** Evidence from the sources that backs it.
- **Stop saying:** Specific phrasing to drop immediately.
- **Start saying:** Specific phrasing to adopt immediately.

## Horizon 2 (6-12 months): Anticipate and move
- **Core positioning claim:** The evolved claim.
- **What must ship to support it:** The capability or proof needed.
- **Competitor move to anticipate:** The likeliest threat and the counter.
- **Whitespace to start claiming now:** The unowned ground to seed early.

## Horizon 3 (12-18 months): Own the category
- **Core positioning claim:** The category-defining claim.
- **The single bet that must be true:** The one assumption everything rests on.
- **Risk if this positioning fails:** What breaks if the bet is wrong.
- **Fallback position:** Where to retreat to if it does."""


# ── Source assembly ─────────────────────────────────────────────────────────

def read_quadrant_rationale() -> str | None:
    """Return the competitive-quadrant rationale if any candidate file exists."""
    for path in QUADRANT_CANDIDATES:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def build_body(intel: dict[str, str], quadrant: str | None) -> str:
    """Stitch the intel files (and optional quadrant) into one source block."""
    parts = [f"### Source: {name}\n\n{content}" for name, content in intel.items()]
    if quadrant:
        parts.append(f"### Competitive quadrant rationale\n\n{quadrant}")
    return "\n\n---\n\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a three-horizon company positioning arc for the CMO."
    )
    parser.add_argument(
        "--company", required=True, metavar="NAME",
        help="company to analyze, e.g. notion (matches inputs/<company>-*.md)",
    )
    sc.add_processing_args(parser)
    args = parser.parse_args()

    company = args.company.strip()

    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    intel = sc.read_company_intel(company)
    if not intel:
        print(
            f"\nError: no intelligence found for '{company}' in {sc.INPUTS_DIR}.\n"
            f"Run the collector tools first so files matching "
            f"{sc.slugify(company)}-*.md exist (e.g. the page decoder, job analyzer)."
        )
        sys.exit(1)

    quadrant = read_quadrant_rationale()

    print(f"\nBuilding positioning arc for {company} from {len(intel)} intel file(s)"
          + (" + quadrant rationale" if quadrant else "") + "...\n")

    body = build_body(intel, quadrant)
    user_prompt = f"Company: {company}\n\nSource materials:\n\n{body}"

    report = sc.analyze(
        SYSTEM_PROMPT,
        user_prompt,
        processor=processor,
        model_key=model_key,
    )

    print("\n" + "=" * 70 + "\n")

    out = sc.save_report(f"{company}-positioning-arc", report)
    intel_file = sc.INPUTS_DIR / f"{sc.slugify(company)}-positioning-arc.md"
    intel_file.write_text(report, encoding="utf-8")
    print(f"Report saved:  {out}")
    print(f"Intel saved:   {intel_file}\n")


if __name__ == "__main__":
    main()
