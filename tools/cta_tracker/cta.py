#!/usr/bin/env python3
"""
CTA Tracker (012) — a weekly call-to-action scoreboard for the competitive set.

Reads the shared corpus (all companies, or a comma-separated subset), extracts the
key calls-to-action each company leans on (from their page copy, personas and
positioning), and scores every company 0-10 across the CTA themes that matter in
THIS market. One company can be flagged as "ours" — per session (set on the Signal
Desk) or with --own — so the report calls out where we're gaining or losing ground
and where the genuine USPs sit — ours and theirs.

Usage: python cta.py [--companies a,b,c] [--own NAME] [--inputs DIR] [-p ...] [-m ...]

Writes (timestamped, so weekly runs build a history):
  - outputs/cta-tracker_<ts>.png   heatmap: companies x CTA themes (ours highlighted)
  - a markdown report via save_report (CTAs, USPs, gaining/losing)
"""
# Self-heal: re-exec under the suite .venv so signalyser_core and third-party deps
# resolve no matter which Python / working dir launched this tool. See _bootstrap.py.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if __name__ == "__main__":
    import _bootstrap
    _bootstrap.ensure_venv(__file__)

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import signalyser_core as sc

OWN = "#E7B33D"       # signal amber — our company highlight
COMP = "#6B7280"      # neutral grey — competitor labels


def read_inputs(folder: Path, only: set[str] | None) -> dict[str, str]:
    """Group .md files by company (prefix before the first '-'); optional subset."""
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for f in sorted(folder.glob("*.md")):
        company = f.stem.split("-")[0].strip().lower()
        if not company or (only is not None and company not in only):
            continue
        groups[company].append((f.stem, f.read_text(encoding="utf-8")))
    combined: dict[str, str] = {}
    for company, files in groups.items():
        parts = [f"## COMPANY: {company.upper()}"]
        for stem, content in files:
            parts.append(f"### Source: {stem}\n\n{content}")
        combined[company] = "\n\n".join(parts)
    return combined


SYSTEM_PROMPT = """\
You are a senior Product Marketing Manager auditing the calls-to-action (CTAs) \
across a competitive set. A CTA is what a company asks the visitor to DO and the \
promise wrapped around it (e.g. "Start free trial", "Free next-day delivery", \
"Money-back guarantee", "Get a quote"). You read each company's page copy, \
personas and positioning, identify the CTA THEMES that matter in this market, and \
score how strongly each company leans on each theme. You always answer with \
strict, valid JSON and nothing else."""


def build_user_prompt(combined: dict[str, str], own: str | None) -> str:
    all_content = "\n\n---\n\n".join(combined.values())
    names = ", ".join(c.upper() for c in combined)
    own_line = (
        f"OUR COMPANY is {own.upper()}; every other company is a competitor. "
        "Use this to populate `our_position`."
        if own else
        "No company is designated as ours — set every is_own to false and leave "
        "`our_position` arrays empty."
    )
    return f"""\
{all_content}

---

Audit the calls-to-action across these {len(combined)} companies: {names}.
{own_line}

Identify 5-8 CTA THEMES that actually differentiate this set (grounded in the
evidence — not generic filler). Score every company 0-10 on each theme (0 = does
not use it, 10 = it is a defining, front-and-centre CTA). Pull each company's
2-3 strongest verbatim CTAs and its genuine USPs.

Return STRICT JSON ONLY — no preamble, no markdown fences, exactly this shape:
{{
  "themes": ["Theme A", "Theme B", "..."],
  "companies": [
    {{"name": "Company", "is_own": false, "scores": {{"Theme A": 7, "Theme B": 2}},
      "primary_ctas": ["verbatim CTA", "..."], "usps": ["genuine USP", "..."]}}
  ],
  "our_position": {{
    "gaining": ["where we lead / are pulling ahead"],
    "losing": ["where competitors out-CTA us"],
    "our_usps": ["CTAs/USPs only we own"],
    "their_usps": ["CTAs/USPs competitors own that we lack"]
  }}
}}"""


def parse_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    for key in ("themes", "companies"):
        if key not in data:
            raise ValueError(f"missing required key '{key}'")
    if not data["themes"] or not isinstance(data["companies"], list) or not data["companies"]:
        raise ValueError("'themes' and 'companies' must be non-empty")
    data.setdefault("our_position", {})
    return data


def _score(co: dict, theme: str) -> float:
    try:
        return float(co.get("scores", {}).get(theme, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def plot_cta(data: dict, output_path: Path) -> Path:
    """Heatmap of CTA-theme intensity per company; our company highlighted."""
    themes = data["themes"]
    # Our company first, then competitors — so the eye starts on "us".
    companies = sorted(data["companies"], key=lambda c: (not c.get("is_own"), c["name"].lower()))
    matrix = [[_score(co, t) for t in themes] for co in companies]

    fig_h = max(3.2, 0.62 * len(companies) + 1.8)
    fig_w = max(7.5, 1.15 * len(themes) + 3.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="white")
    im = ax.imshow(matrix, cmap="YlOrBr", vmin=0, vmax=10, aspect="auto")

    ax.set_xticks(range(len(themes)))
    ax.set_xticklabels(themes, rotation=32, ha="right", fontsize=8, color="#374151")
    ax.set_yticks(range(len(companies)))
    labels = [co["name"] + ("  ◆" if co.get("is_own") else "") for co in companies]
    ax.set_yticklabels(labels, fontsize=9)
    for i, co in enumerate(companies):
        tick = ax.get_yticklabels()[i]
        tick.set_color(OWN if co.get("is_own") else COMP)
        if co.get("is_own"):
            tick.set_fontweight("bold")
            ax.add_patch(Rectangle((-0.5, i - 0.5), len(themes), 1, fill=False,
                                   edgecolor=OWN, linewidth=2.2, zorder=5))

    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                    color="#1f2937" if v < 6 else "#ffffff")

    ax.set_title("CTA Tracker — call-to-action intensity (◆ = us)",
                 fontsize=13, fontweight="bold", color="#111827", pad=12)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label("CTA prominence (0-10)", fontsize=8, color="#6B7280")
    cbar.ax.tick_params(labelsize=7, length=0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight", pad_inches=0.35, facecolor="white")
    plt.close(fig)
    return output_path


def build_report_md(data: dict, own: str | None, png_name: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# CTA Tracker — {today}", ""]
    if own:
        lines.append(f"**Our company:** {own}")
    lines += ["", f"![CTA heatmap]({png_name})", "", "## CTA themes", ""]
    lines += [f"- {t}" for t in data["themes"]]
    lines += ["", "## By company", ""]
    for co in sorted(data["companies"], key=lambda c: (not c.get("is_own"), c["name"].lower())):
        tag = " *(us)*" if co.get("is_own") else ""
        lines.append(f"### {co['name']}{tag}")
        if co.get("primary_ctas"):
            lines.append("**Primary CTAs:** " + "; ".join(co["primary_ctas"]))
        if co.get("usps"):
            lines.append("**USPs:** " + "; ".join(co["usps"]))
        lines.append("")
    pos = data.get("our_position") or {}
    if any(pos.get(k) for k in ("gaining", "losing", "our_usps", "their_usps")):
        lines += ["## Us vs them", ""]
        for label, key in (("Gaining ground", "gaining"), ("Losing ground", "losing"),
                           ("Our USPs", "our_usps"), ("Their USPs (we lack)", "their_usps")):
            items = pos.get(key) or []
            if items:
                lines.append(f"**{label}:**")
                lines += [f"- {x}" for x in items]
                lines.append("")
    return "\n".join(lines)


def main() -> None:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    parser = argparse.ArgumentParser(
        description="Track calls-to-action across the corpus (us vs competitors)."
    )
    parser.add_argument("--companies", metavar="A,B,C",
                        help="comma-separated subset (default: every company in the corpus)")
    parser.add_argument("--own", metavar="NAME",
                        help="which company is ours (default: the OWN_COMPANY setting)")
    parser.add_argument("--inputs", default=None, metavar="DIR",
                        help="folder of .md intel files (default: the active session's inputs/)")
    sc.add_processing_args(parser)
    args = parser.parse_args()

    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    inputs_dir = Path(args.inputs).resolve() if args.inputs else sc.inputs_dir()
    if not inputs_dir.is_dir():
        print(f"Not a directory: {inputs_dir}")
        sys.exit(1)

    only = None
    if args.companies:
        only = {sc.slugify(c) for c in args.companies.split(",") if c.strip()}

    own_raw = (args.own or sc.get_own_company() or "").strip()
    own_slug = sc.slugify(own_raw) if own_raw else ""

    print(f"\nReading intelligence from {inputs_dir} ...")
    combined = read_inputs(inputs_dir, only)
    if len(combined) < 2:
        print(f"Need at least 2 companies, found {len(combined)}: {', '.join(combined) or '(none)'}.\n"
              "Run the collectors first (or check the --companies filter).")
        sys.exit(1)

    own_display = ""
    if own_slug:
        if own_slug in combined:
            own_display = own_slug
        else:
            print(f"[!] Our company '{own_raw}' isn't in this corpus — treating all as competitors.")
    print(f"Companies: {', '.join(combined)}"
          + (f"   (ours: {own_display})" if own_display else "   (no 'our company' set)") + "\n")
    print("=" * 70)

    # Local models have a small context window — trim the corpus so it fits (cloud
    # gets the full thing). Without this, a multi-company corpus overflows and the
    # local model returns nothing.
    combined = sc.fit_corpus_for_local(combined, processor)

    # Tag is_own in the prompt by passing the display name; the model echoes it back,
    # but we also enforce it after parsing so the plot/report are correct.
    raw = sc.analyze(
        SYSTEM_PROMPT,
        build_user_prompt(combined, own_display or None),
        processor=processor, model_key=model_key,
    )
    print("\n" + "=" * 70 + "\n")

    try:
        data = parse_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        if not raw.strip():
            print(
                "The model returned no output. On local processing this usually means "
                "the corpus is still too large for the model's context — try a smaller "
                "--companies subset, raise OLLAMA_NUM_CTX, or run on cloud (-p cloud)."
            )
        else:
            print(f"Failed to parse model response as CTA JSON: {e}\n\nRaw model output:\n{raw}")
        sys.exit(1)

    # Enforce the is_own flag from our own setting (don't trust the model).
    for co in data["companies"]:
        co["is_own"] = bool(own_display) and sc.slugify(co.get("name", "")) == own_display

    print("CTA themes: " + ", ".join(data["themes"]) + "\n")
    print("Intensity (0-10):")
    for co in sorted(data["companies"], key=lambda c: (not c.get("is_own"), c["name"].lower())):
        mark = " (us)" if co.get("is_own") else ""
        scores = " ".join(f"{t[:10]}={_score(co, t):.0f}" for t in data["themes"])
        print(f"  {co['name']:<16}{mark:<5} {scores}")
    print()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_path = sc.outputs_dir() / f"cta-tracker_{stamp}.png"
    plot_cta(data, png_path)
    report = build_report_md(data, own_display or None, png_path.name)
    md_path = sc.save_report("cta-tracker", report)

    print(f"Chart (open this):  {png_path}")
    print(f"Report:             {md_path}")


if __name__ == "__main__":
    main()
