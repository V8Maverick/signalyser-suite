#!/usr/bin/env python3
"""
Competitive Quadrant — reads the shared competitive-intelligence corpus, asks the
model to derive the TWO most differentiating axes for THIS set of companies (data
-driven, not generic "vision vs execution"), places each company on a -10..+10
scale for both axes, and plots a single quadrant chart.

Ported from varshp/marketer-that-ships 007-competitive-quadrant, rebuilt on the
Signalyser shared core: analysis runs through sc.analyze (local Ollama or cloud
Anthropic, sticky -p/-m), and inputs/outputs come from the shared corpus.

Usage: python3 quadrant.py [--inputs DIR] [-p local|cloud] [-m MODEL]

Reads every *.md in the inputs dir, groups them by company (the filename prefix
before the first '-'), concatenates each company's files, and feeds the lot to
the model. Writes:
  - outputs/quadrant-1.png   the quadrant chart
  - outputs/axes-rationale.md axis definitions + per-company placement rationale
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
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless: no display, write straight to a PNG
import matplotlib.pyplot as plt

import signalyser_core as sc

# Company dot colours, cycled in order.
COLORS = [
    "#2563EB",  # blue
    "#DC2626",  # red
    "#16A34A",  # green
    "#D97706",  # amber
    "#7C3AED",  # purple
    "#0891B2",  # cyan
    "#DB2777",  # pink
]


# ── Input reading ──────────────────────────────────────────────────────────────

def read_inputs(folder: Path) -> dict[str, str]:
    """Group .md files by company (the filename prefix before the first '-').

    Concatenates each company's files into one block. Returns
    {company: combined_text}. Empty if the folder has no .md files.
    """
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for f in sorted(folder.glob("*.md")):
        company = f.stem.split("-")[0].strip().lower()
        if not company:
            continue
        groups[company].append((f.stem, f.read_text(encoding="utf-8")))

    combined: dict[str, str] = {}
    for company, files in groups.items():
        parts = [f"## COMPANY: {company.upper()}"]
        for stem, content in files:
            parts.append(f"### Source: {stem}\n\n{content}")
        combined[company] = "\n\n".join(parts)
    return combined


# ── Prompting ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior Product Marketing Manager building a competitive positioning \
map. You read raw competitive intelligence and identify the dimensions that \
TRULY separate the players in THIS specific market. You reject generic, \
off-the-shelf axes (vision vs execution, price vs quality) in favour of axes \
grounded in the actual evidence. You always answer with strict, valid JSON and \
nothing else."""


def build_user_prompt(combined: dict[str, str]) -> str:
    all_content = "\n\n---\n\n".join(combined.values())
    names = ", ".join(c.upper() for c in combined)
    return f"""\
{all_content}

---

Analyse the competitive landscape across these {len(combined)} companies: {names}.

Based ONLY on the intelligence above, derive the TWO most differentiating axes
for this competitive set. The axes must:
  - be specific to THIS market and grounded in the evidence provided,
  - be genuinely distinct from each other (two different strategic dimensions),
  - NOT be generic axes like "vision vs execution" or "price vs quality".

Place every company on BOTH axes using a -10 to +10 scale (negative = the "low"
end of the axis, positive = the "high" end). Give a one-sentence rationale for
each placement, citing what in the data drove it.

Return STRICT JSON ONLY — no preamble, no markdown fences, exactly this shape:
{{
  "x_axis": {{"label": "short label", "low": "what -10 means", "high": "what +10 means"}},
  "y_axis": {{"label": "short label", "low": "what -10 means", "high": "what +10 means"}},
  "companies": [
    {{"name": "Company Name", "x": -3.5, "y": 7.0, "rationale": "one sentence"}}
  ]
}}"""


# ── Response parsing ─────────────────────────────────────────────────────────────

def parse_response(raw: str) -> dict:
    """Parse the model's JSON reply into a quadrant dict.

    Strips ```json / ``` fences if present, then json.loads. Raises
    json.JSONDecodeError on malformed JSON (caller handles by printing raw +
    exiting). Validates the expected top-level keys are present.
    """
    text = raw.strip()
    if text.startswith("```"):
        # Drop the opening fence line (``` or ```json) and any trailing fence.
        lines = text.splitlines()
        lines = lines[1:]  # remove opening ```/```json
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    data = json.loads(text)

    for key in ("x_axis", "y_axis", "companies"):
        if key not in data:
            raise ValueError(f"missing required key '{key}' in model response")
    if not isinstance(data["companies"], list) or not data["companies"]:
        raise ValueError("'companies' must be a non-empty list")
    return data


# ── Plotting ─────────────────────────────────────────────────────────────────────

def _wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width=width))


def plot_quadrant(data: dict, output_path: Path) -> Path:
    """Render the quadrant chart to output_path (PNG). Returns the path.

    Uses the Agg backend (set at import) so no display is needed.
    """
    x_axis = data["x_axis"]
    y_axis = data["y_axis"]
    companies = data["companies"]

    fig, ax = plt.subplots(figsize=(11, 9), facecolor="white")
    ax.set_facecolor("white")

    # Quadrant cross-hairs at the origin; -10..+10 on both axes.
    ax.axvline(0, color="#E5E7EB", linewidth=1.0, zorder=1)
    ax.axhline(0, color="#E5E7EB", linewidth=1.0, zorder=1)
    ax.set_xlim(-10, 10)
    ax.set_ylim(-10, 10)
    ax.set_xticks(range(-10, 11, 5))
    ax.set_yticks(range(-10, 11, 5))
    ax.tick_params(colors="#9CA3AF", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#E5E7EB")

    # Directional descriptors placed just outside the axes box.
    desc_kw = dict(color="#9CA3AF", style="italic", fontsize=7,
                   transform=ax.transAxes, clip_on=False, linespacing=1.3)
    ax.text(0.0, -0.11, f"← {_wrap(x_axis['low'], 38)}", ha="left", va="top", **desc_kw)
    ax.text(1.0, -0.11, f"{_wrap(x_axis['high'], 38)} →", ha="right", va="top", **desc_kw)
    ax.text(-0.02, 1.0, f"↑ {_wrap(y_axis['high'], 30)}", ha="right", va="top", **desc_kw)
    ax.text(-0.02, 0.0, f"↓ {_wrap(y_axis['low'], 30)}", ha="right", va="bottom", **desc_kw)

    ax.set_xlabel(x_axis["label"], fontsize=11, fontweight="bold",
                  color="#111827", labelpad=10)
    ax.set_ylabel(y_axis["label"], fontsize=11, fontweight="bold",
                  color="#111827", labelpad=10)

    for i, co in enumerate(companies):
        color = COLORS[i % len(COLORS)]
        x, y = float(co["x"]), float(co["y"])
        ax.scatter(x, y, s=160, color=color, zorder=5,
                   edgecolors="white", linewidths=1.5)
        ax.text(x + 0.25, y + 0.35, co["name"], fontsize=9, fontweight="bold",
                color=color, ha="left", va="bottom", zorder=6)

    ax.set_title("Competitive Quadrant", fontsize=14, fontweight="bold",
                 color="#111827", pad=14)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight",
                pad_inches=0.4, facecolor="white")
    plt.close(fig)
    return output_path


# ── Rationale markdown ───────────────────────────────────────────────────────────

def build_rationale_md(data: dict) -> str:
    x, y = data["x_axis"], data["y_axis"]
    lines = [
        "# Competitive Quadrant — Axes Rationale",
        "",
        f"## X-axis: {x['label']}",
        f"- **Low (-10):** {x['low']}",
        f"- **High (+10):** {x['high']}",
        "",
        f"## Y-axis: {y['label']}",
        f"- **Low (-10):** {y['low']}",
        f"- **High (+10):** {y['high']}",
        "",
        "## Company Placements",
        "",
    ]
    for co in data["companies"]:
        lines.append(f"### {co['name']}  (x={co['x']}, y={co['y']})")
        lines.append(co.get("rationale", ""))
        lines.append("")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot a data-driven competitive quadrant from the shared intel corpus."
    )
    parser.add_argument(
        "--inputs", default=str(sc.INPUTS_DIR), metavar="DIR",
        help="folder of .md intelligence files (default: the suite inputs/ folder)",
    )
    sc.add_processing_args(parser)
    args = parser.parse_args()

    sc.load_env()

    inputs_dir = Path(args.inputs).resolve()
    if not inputs_dir.is_dir():
        print(f"Not a directory: {inputs_dir}")
        sys.exit(1)

    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    print(f"\nReading intelligence from {inputs_dir} ...")
    combined = read_inputs(inputs_dir)
    if not combined:
        print(f"No .md files found in {inputs_dir}")
        sys.exit(1)
    if len(combined) < 2:
        print(f"Need at least 2 companies for a quadrant, found {len(combined)}: "
              f"{', '.join(combined)}")
        sys.exit(1)
    print(f"Companies: {', '.join(combined)}\n")

    raw = sc.analyze(
        SYSTEM_PROMPT,
        build_user_prompt(combined),
        processor=processor,
        model_key=model_key,
    )
    print("\n" + "=" * 70 + "\n")

    try:
        data = parse_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Failed to parse model response as quadrant JSON: {e}\n")
        print("Raw model output:\n")
        print(raw)
        sys.exit(1)

    png_path = plot_quadrant(data, sc.OUTPUTS_DIR / "quadrant-1.png")
    print(f"Saved chart:     {png_path}")

    rationale_path = sc.OUTPUTS_DIR / "axes-rationale.md"
    rationale_path.parent.mkdir(parents=True, exist_ok=True)
    rationale_path.write_text(build_rationale_md(data), encoding="utf-8")
    print(f"Saved rationale: {rationale_path}")


if __name__ == "__main__":
    main()
