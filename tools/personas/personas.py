#!/usr/bin/env python3
"""
Persona Generator — read every intel file a company has accumulated in the
shared corpus and have a senior PMM synthesise 2-3 evidence-based buyer personas,
where every attribute traces back to a specific source file/signal.

Usage: python3 personas.py --company <name> [-p local|cloud] [-m MODEL]

The processor (-p) and cloud model (-m) are sticky: once set they persist in
.env for every tool in the suite until changed. See the shared signalyser_core.

The personas document is saved two ways:
  - a timestamped report in outputs/        (sc.save_report)
  - inputs/<slug>-personas.md, so the downstream asset generator can read it.
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

import signalyser_core as sc

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior Product Marketing Manager building evidence-based buyer personas.

Do not invent personas from general knowledge. Derive every attribute from the
source materials provided:
- Review / community data reveals who is buying and why
- Job postings reveal who they are selling to and how they describe the buyer
- 10-K / 20-F reveals how they describe buyers and markets
- Competitor page reveals who they target

For each persona generate, using EXACTLY these headers (keep them verbatim):

PERSONA NAME: (a real job title, not a cute name)

EVIDENCE BASE:
Which source files informed this persona and what specific signals revealed them.

WHO THEY ARE:
- Job title and seniority
- Company size and type
- Day to day reality in 2-3 sentences
- What they read, follow, care about

WHAT THEY ARE TRYING TO DO:
- Primary job to be done
- Secondary jobs to be done
- What success looks like to them

WHY THEY BUY:
- Trigger event that starts the search
- What they are moving away from
- What they are moving toward
- How they justify it internally

WHY THEY DON'T BUY:
- Top objection
- What makes them stall
- Who else is in the room blocking the deal

EXACT LANGUAGE THEY USE:
- 3-5 direct quotes or phrases drawn from the source data
- How they describe the problem in their own words
- How they describe the ideal solution

WHERE TO REACH THEM:
- Channels they trust
- Content formats that work
- Communities they participate in

Generate 2-3 personas. Only include a persona if there is sufficient evidence in
the source materials to populate at least 70% of the fields. Do not pad with
assumptions.

Trace every attribute to a specific source file/signal. Flag any field populated
from inference rather than direct evidence with (inferred).

After all personas, add:

SEGMENT PRIORITY RECOMMENDATION:
Which persona represents the highest-value segment to prioritise right now and why.
Base this only on evidence in the source materials — growth signals, strategic
investment, GTM motion, competitive window. Do not use general market knowledge."""


def build_user_prompt(company: str, intel: dict[str, str]) -> str:
    """Concatenate the company's intel files, each labelled by filename."""
    blocks = [f"### FILE: {name}\n\n{contents}" for name, contents in intel.items()]
    source_materials = "\n\n".join(blocks)
    return (
        f"Build evidence-based buyer personas for {company} from the source "
        f"materials below.\n\n---\n\nSOURCE MATERIALS:\n\n{source_materials}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate evidence-based buyer personas from a company's intel corpus."
    )
    parser.add_argument("--company", required=True, help="company name, e.g. notion")
    sc.add_processing_args(parser)
    args = parser.parse_args()

    company = args.company.strip()

    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    intel = sc.read_company_intel(company)
    if not intel:
        sys.exit(
            f"No intel for {company} in inputs/ — run collectors first "
            "(page/jobs/10-K)."
        )

    print(f"\nGenerating personas for {company} from {len(intel)} intel file(s): "
          f"{', '.join(intel)}\n")

    user_prompt = build_user_prompt(company, intel)
    report = sc.analyze(
        SYSTEM_PROMPT,
        user_prompt,
        processor=processor,
        model_key=model_key,
    )

    print("\n" + "=" * 70 + "\n")

    out = sc.save_report(f"{company}-personas", report)
    # Also write to inputs/ so the downstream asset generator can read it.
    intel_file = sc.INPUTS_DIR / f"{sc.slugify(company)}-personas.md"
    intel_file.write_text(report, encoding="utf-8")
    print(f"Report saved:  {out}")
    print(f"Intel saved:   {intel_file}\n")


if __name__ == "__main__":
    main()
