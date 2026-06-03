# Company Positioning Arc

A senior-PMM advisor for the CMO. It reads everything the Signalyser suite has
collected about a company from the shared `inputs/` corpus and produces a
**three-horizon positioning arc**:

- **Current state** — inferred positioning, the gap between what the company
  claims and what customers perceive, and the biggest competitive vulnerability.
- **Horizon 1 (0-6 months)** — defend and sharpen.
- **Horizon 2 (6-12 months)** — anticipate and move.
- **Horizon 3 (12-18 months)** — own the category.

The model is instructed to quote the **exact language** from the sources and to
stay specific to the company (no generic B2B-SaaS advice).

## Usage

```bash
# from the suite root, using the suite venv
.venv/Scripts/python.exe tools/positioning_arc/arc.py --company notion

# pick a backend (sticky across the whole suite once set)
.venv/Scripts/python.exe tools/positioning_arc/arc.py --company notion -p cloud -m opus-4.8
```

### Arguments

| Flag | Required | Description |
|------|----------|-------------|
| `--company NAME` | yes | Company to analyze; matches `inputs/<company>-*.md`. |
| `-p, --processor local\|cloud` | no | Backend (Ollama vs Anthropic). Sticky in `.env`. |
| `-m, --model MODEL` | no | Cloud model: `opus-4.8` \| `sonnet-4.6` \| `haiku-4.5`. Sticky. |

## Inputs

Reads all `inputs/<company>-*.md` intel files via `sc.read_company_intel`. If no
files exist for the company, the tool prints a clear error and exits with code 1
— run the collector tools (page decoder, job analyzer, etc.) first.

It will **optionally** fold in a competitive-quadrant rationale if one exists at
`outputs/axes-rationale.md` or `tools/quadrant/axes-rationale.md`. This is a soft
dependency: if neither file is present, the quadrant context is simply skipped.

## Outputs

- A timestamped report in `outputs/` (via `sc.save_report`).
- `inputs/<slug>-positioning-arc.md`, joining the shared corpus so the asset
  generator and other downstream tools can read it.

## Backend

All analysis goes through the shared `signalyser_core` (`sc.analyze`). The tool
never calls Anthropic or Ollama directly, and the `-p`/`-m` selection is shared
with every other tool in the suite.
