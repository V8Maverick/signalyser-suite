#!/usr/bin/env python3
"""
Written Asset Generator (010) — the capstone of the Signalyser suite.

Claude reads everything the suite knows about a company's positioning and its
buyers, then autonomously decides which written assets to create for each
persona, generates them, and runs a reflection loop that scores every asset and
revises any that fall short.

Usage: python3 assets.py --company <name> [-p local|cloud] [-m MODEL]

The processor (-p) and cloud model (-m) are sticky: once set they persist in
.env for every tool in the suite until changed. See the shared signalyser_core.

Inputs (read from the shared inputs/ corpus):
  inputs/<slug>-personas.md          (from tool 009 — the persona source)
  inputs/<slug>-positioning-arc.md   (from tool 008 — the positioning source)
Both are required. There is no separate content brief in this suite — content
angles are derived from the positioning arc by the model itself. If either file
is missing, the tool prints a clear error and exits 1.

The reflection loop scores each asset 0-10 on three criteria and revises any
asset with a score below 7 (max 2 revisions):
  1. PLAN     — which assets to create per persona (STRICT JSON)
  2. GENERATE — the full asset text, streamed
  3. REFLECT  — traceable / objection / cta scores (STRICT JSON)
  4. REVISE   — if any score < 7

Outputs (output to outputs/<slug>/):
  <slug>-content-plan.md                       (summary + scores table)
  <slug>-<persona-slug>-<asset-type-slug>.md   (one file per asset, with frontmatter)
"""

# Self-heal: re-exec under the suite .venv so signalyser_core and third-party deps
# resolve no matter which Python / working dir launched this tool. See _bootstrap.py.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if __name__ == "__main__":
    import _bootstrap
    _bootstrap.ensure_venv(__file__)

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

import signalyser_core as sc

# ── Config ──────────────────────────────────────────────────────────────────

MAX_REVISIONS = 2          # revise an asset at most this many times
SCORE_THRESHOLD = 7        # any criterion below this triggers a revision

# Token budgets per step. Plan/reflect are small JSON; generate/revise are prose.
PLAN_MAX_TOKENS = 4096
ASSET_MAX_TOKENS = 4096
REFLECT_MAX_TOKENS = 1024


# ── Source loading ──────────────────────────────────────────────────────────

def load_sources(company: str) -> tuple[str, str]:
    """Return (personas, positioning_arc) text from the shared inputs/ corpus.

    Both files are required. The persona and positioning-arc tools each write a
    <slug>-personas.md / <slug>-positioning-arc.md into inputs/ when they run, so
    we read those specific files out of read_company_intel's {filename: contents}.
    """
    slug = sc.slugify(company)
    intel = sc.read_company_intel(company)

    personas = intel.get(f"{slug}-personas.md")
    positioning = intel.get(f"{slug}-positioning-arc.md")

    missing = []
    if not personas:
        missing.append(f"  - inputs/{slug}-personas.md  (run tools/personas first)")
    if not positioning:
        missing.append(f"  - inputs/{slug}-positioning-arc.md  (run tools/positioning_arc first)")
    if missing:
        print(
            f"\nError: the asset generator needs both a personas file and a "
            f"positioning-arc file for '{company}', but these are missing:\n"
            + "\n".join(missing)
            + "\n\nRun the upstream tools first:\n"
            f"  python tools/personas/personas.py --company {company}\n"
            f"  python tools/positioning_arc/arc.py --company {company}\n"
        )
        sys.exit(1)

    return personas, positioning


# ── JSON parsing (robust to ```json fences) ───────────────────────────────────

def _strip_json_fence(text: str) -> str:
    """Strip a leading ```json / ``` fence (and trailing ```) if present."""
    s = text.strip()
    if s.startswith("```"):
        # Drop the opening fence line (``` or ```json) and the closing fence.
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[: -3]
    return s.strip()


def parse_json(label: str, raw: str):
    """Parse model output as JSON, tolerating code fences. Exit 1 on failure."""
    try:
        return json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as e:
        print(
            f"\nError: could not parse {label} step output as JSON ({e}).\n"
            "--- raw model output ---\n"
            f"{raw}\n"
            "------------------------"
        )
        sys.exit(1)


# ── Prompts ───────────────────────────────────────────────────────────────────

PLAN_SYSTEM = """\
You are a senior B2B content strategist. Working from a company's positioning arc \
and its evidence-based buyer personas, decide which written assets to create for \
each persona. Match each asset format to where the persona is reachable and \
ground every choice in that persona's buying trigger, top objection, and exact \
language. Derive the content angle from the positioning arc — there is no \
separate content brief. Vary formats across personas so the mix is diverse.

Asset type examples (not exhaustive): one-pager, executive brief, cold email, \
email sequence, battle card, blog post, LinkedIn post, case study outline, FAQ \
sheet, ROI narrative, comparison guide.

Choose 2-3 assets per persona. Respond with STRICT JSON only — no prose, no code \
fences, no commentary. The JSON MUST be an array of objects with EXACTLY these \
keys:
[
  {"persona": "<persona name/title>", "asset_type": "<asset type>", "why": "<why this asset for this persona, grounded in trigger/objection/language>"}
]"""

GENERATE_SYSTEM = """\
You are a senior B2B copywriter. Write one complete, ready-to-publish written \
asset for the target persona using the company's positioning arc and persona \
profile as your only source of truth.

Rules:
- Every claim must trace back to the source materials (positioning arc / persona).
- Use the persona's own documented language wherever possible.
- Address the persona's top objection directly and specifically.
- End with a call-to-action tied to the persona's documented buying trigger, not
  a generic one.
- Output the finished asset in markdown. No placeholders, no meta-commentary."""

REFLECT_SYSTEM = """\
You are a rigorous content quality reviewer. Score the asset against the source \
materials on three criteria, each 0-10:

- traceable: Is every claim grounded in the positioning arc / persona profile?
  Deduct heavily for invented stats or proof points not in the materials.
- objection: Does it directly and specifically address the persona's documented
  top objection? Vague acknowledgement scores low.
- cta: Is the call-to-action tied to this persona's documented buying trigger,
  or is it generic? Generic CTAs score low unless the trigger matches.

Respond with STRICT JSON only — no prose, no code fences. EXACTLY these keys:
{"traceable": <int 0-10>, "objection": <int 0-10>, "cta": <int 0-10>}"""

REVISE_SYSTEM = """\
You are a senior B2B copywriter revising an asset to fix specific quality gaps. \
Return ONLY the revised asset in markdown — no commentary. Keep what works; fix \
what the reviewer flagged. Every claim must trace to the source materials, the \
persona's top objection must be addressed specifically, and the CTA must be tied \
to the persona's documented buying trigger."""


def _sources_block(personas: str, positioning: str) -> str:
    return (
        f"### POSITIONING ARC\n\n{positioning}\n\n"
        f"---\n\n"
        f"### BUYER PERSONAS\n\n{personas}"
    )


def plan_prompt(company: str, personas: str, positioning: str) -> str:
    return (
        f"Company: {company}\n\n"
        f"Decide which written assets to create for each persona below.\n\n"
        f"{_sources_block(personas, positioning)}"
    )


def generate_prompt(company: str, item: dict, personas: str, positioning: str) -> str:
    return (
        f"Company: {company}\n\n"
        f"TARGET PERSONA: {item['persona']}\n"
        f"ASSET TYPE: {item['asset_type']}\n"
        f"WHY THIS ASSET: {item['why']}\n\n"
        f"Write the complete asset now.\n\n"
        f"---\n\n{_sources_block(personas, positioning)}"
    )


def reflect_prompt(company: str, item: dict, content: str,
                   personas: str, positioning: str) -> str:
    return (
        f"Company: {company}\n\n"
        f"PERSONA: {item['persona']}\n"
        f"ASSET TYPE: {item['asset_type']}\n\n"
        f"ASSET TO SCORE:\n{content}\n\n"
        f"---\n\nSOURCE MATERIALS:\n\n{_sources_block(personas, positioning)}"
    )


def revise_prompt(company: str, item: dict, content: str, scores: dict,
                  personas: str, positioning: str) -> str:
    low = [k for k, v in scores.items() if v < SCORE_THRESHOLD]
    score_line = ", ".join(f"{k}={scores[k]}/10" for k in ("traceable", "objection", "cta"))
    return (
        f"Company: {company}\n\n"
        f"PERSONA: {item['persona']}\n"
        f"ASSET TYPE: {item['asset_type']}\n\n"
        f"REVIEW SCORES: {score_line}\n"
        f"FIX THESE CRITERIA (scored below {SCORE_THRESHOLD}): {', '.join(low)}\n\n"
        f"ORIGINAL ASSET:\n{content}\n\n"
        f"---\n\nSOURCE MATERIALS:\n\n{_sources_block(personas, positioning)}\n\n"
        f"Return the revised asset only."
    )


# ── Reflection loop ─────────────────────────────────────────────────────────

def _coerce_scores(raw_scores: dict) -> dict:
    """Pull the three integer scores out of the reflect JSON, defaulting to 0."""
    scores = {}
    for key in ("traceable", "objection", "cta"):
        val = raw_scores.get(key, 0)
        try:
            scores[key] = int(val)
        except (TypeError, ValueError):
            scores[key] = 0
    return scores


def generate_with_reflection(company, item, personas, positioning,
                             processor, model_key) -> tuple[str, dict, int]:
    """Generate one asset, then reflect/revise until it passes or revisions run out.

    Returns (final_content, final_scores, revisions_made).
    """
    content = sc.analyze(
        GENERATE_SYSTEM,
        generate_prompt(company, item, personas, positioning),
        processor=processor, model_key=model_key, max_tokens=ASSET_MAX_TOKENS,
    )

    revisions = 0
    scores: dict = {}
    while True:
        print(f"\n  Reflecting (pass {revisions + 1})...")
        raw = sc.analyze(
            REFLECT_SYSTEM,
            reflect_prompt(company, item, content, personas, positioning),
            processor=processor, model_key=model_key, max_tokens=REFLECT_MAX_TOKENS,
        )
        scores = _coerce_scores(parse_json("reflect", raw))
        low = [k for k, v in scores.items() if v < SCORE_THRESHOLD]
        print("  Scores: " + " | ".join(f"{k} {scores[k]}/10"
                                        for k in ("traceable", "objection", "cta")))

        if not low or revisions >= MAX_REVISIONS:
            if low:
                print(f"  Kept after {revisions} revision(s) — still below "
                      f"threshold on: {', '.join(low)}")
            else:
                print("  All criteria passed.")
            break

        print(f"  Below {SCORE_THRESHOLD} on {', '.join(low)} — revising...\n")
        content = sc.analyze(
            REVISE_SYSTEM,
            revise_prompt(company, item, content, scores, personas, positioning),
            processor=processor, model_key=model_key, max_tokens=ASSET_MAX_TOKENS,
        )
        revisions += 1

    return content, scores, revisions


# ── Output writing ──────────────────────────────────────────────────────────

def _yaml_escape(value: str) -> str:
    """Quote a YAML scalar so colons/special chars in titles stay valid."""
    return '"' + str(value).replace('"', '\\"') + '"'


def write_asset_file(out_dir: Path, slug: str, company: str, item: dict,
                     content: str, scores: dict, title: str) -> str:
    """Write one asset markdown file with YAML frontmatter. Returns the filename."""
    persona_slug = sc.slugify(item["persona"])
    type_slug = sc.slugify(item["asset_type"])
    fname = f"{slug}-{persona_slug}-{type_slug}.md"

    frontmatter = [
        "---",
        f"company: {_yaml_escape(company)}",
        f"persona: {_yaml_escape(item['persona'])}",
        f"asset_type: {_yaml_escape(item['asset_type'])}",
        f"title: {_yaml_escape(title)}",
        "scores:",
        f"  traceable: {scores.get('traceable', 0)}",
        f"  objection: {scores.get('objection', 0)}",
        f"  cta: {scores.get('cta', 0)}",
        "---",
    ]
    (out_dir / fname).write_text("\n".join(frontmatter) + "\n\n" + content, encoding="utf-8")
    return fname


def build_content_plan(company: str, slug: str, results: list[dict]) -> str:
    """Assemble the human-readable content-plan summary with a scores table."""
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(results)
    revised = sum(1 for r in results if r["revisions"] > 0)

    lines = [
        f"# {company} — Content Plan",
        "",
        f"*Generated {today} by the Signalyser asset generator (010).*",
        "",
        f"**{total} assets · {revised} revised**",
        "",
        "| Persona | Asset | Traceable | Objection | CTA | Revisions | File |",
        "|---------|-------|----------:|----------:|----:|----------:|------|",
    ]
    for r in results:
        s = r["scores"]
        lines.append(
            f"| {r['persona']} | {r['asset_type']} "
            f"| {s.get('traceable', 0)} | {s.get('objection', 0)} | {s.get('cta', 0)} "
            f"| {r['revisions']} | `{r['filename']}` |"
        )
    lines.append("")

    for r in results:
        lines += [
            f"## [{r['asset_type']}] {r['persona']}",
            "",
            f"**Why:** {r['why']}",
            "",
            f"**File:** `{r['filename']}`",
            "",
        ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate persona-targeted written assets with a reflection loop."
    )
    parser.add_argument(
        "--company", required=True, metavar="NAME",
        help="company to generate assets for, e.g. notion (matches inputs/<company>-*.md)",
    )
    sc.add_processing_args(parser)
    args = parser.parse_args()

    company = args.company.strip()

    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    personas, positioning = load_sources(company)

    slug = sc.slugify(company)
    out_dir = sc.OUTPUTS_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Plan ────────────────────────────────────────────────────────────────
    print(f"\nPlanning assets for {company}...\n")
    print("=" * 70)
    plan_raw = sc.analyze(
        PLAN_SYSTEM,
        plan_prompt(company, personas, positioning),
        processor=processor, model_key=model_key, max_tokens=PLAN_MAX_TOKENS,
    )
    plan = parse_json("plan", plan_raw)
    if not isinstance(plan, list) or not plan:
        print("\nError: plan step did not return a non-empty JSON array of assets.")
        sys.exit(1)

    print("\n\nPlanned assets:")
    for item in plan:
        print(f"  - [{item.get('asset_type', '?')}] for {item.get('persona', '?')}")

    # ── 2-4. Generate + reflect + revise each asset ────────────────────────────
    results: list[dict] = []
    for i, item in enumerate(plan, 1):
        # Tolerate a sparse plan entry rather than crashing the whole run.
        item = {
            "persona": str(item.get("persona", "Unknown persona")),
            "asset_type": str(item.get("asset_type", "asset")),
            "why": str(item.get("why", "")),
        }
        print(f"\n{'-' * 70}")
        print(f"  Asset {i}/{len(plan)}: [{item['asset_type']}] for {item['persona']}")
        print(f"{'-' * 70}\n")

        content, scores, revisions = generate_with_reflection(
            company, item, personas, positioning, processor, model_key
        )

        # Use the asset's first markdown heading as the title, else a fallback.
        title = f"{item['asset_type']} for {item['persona']}"
        for line in content.splitlines():
            if line.strip().startswith("#"):
                title = line.lstrip("#").strip() or title
                break

        fname = write_asset_file(out_dir, slug, company, item, content, scores, title)
        print(f"\n  Saved: {out_dir / fname}")

        results.append({
            "persona": item["persona"],
            "asset_type": item["asset_type"],
            "why": item["why"],
            "scores": scores,
            "revisions": revisions,
            "filename": fname,
        })

    # ── 5. Content plan ────────────────────────────────────────────────────────
    plan_md = build_content_plan(company, slug, results)
    plan_path = out_dir / f"{slug}-content-plan.md"
    plan_path.write_text(plan_md, encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"\nDone. {len(results)} asset(s) written to {out_dir}")
    print(f"Content plan:  {plan_path}\n")


if __name__ == "__main__":
    main()
