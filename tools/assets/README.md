# Written Asset Generator (010)

The capstone of the Signalyser suite. Reads everything the suite knows about a
company — its buyer personas and its positioning arc — then has the model decide
which written assets to create for each persona, generates them, and runs a
**reflection loop** that scores every asset and revises any that fall short.

Part of the Signalyser market-intelligence suite. Analysis runs through the
shared `signalyser_core` backend, so it supports the same sticky local (Ollama)
vs cloud (Anthropic) processor selection as every other tool.

## What it does

1. Reads the two required intel files from the shared corpus:
   - `inputs/<company>-personas.md` (from tool 009 — the persona source)
   - `inputs/<company>-positioning-arc.md` (from tool 008 — the positioning source)

   If either is missing it prints a clear error naming the upstream tool to run,
   and exits 1. There is no separate content brief — content angles are derived
   from the positioning arc by the model itself.
2. **PLAN** (strict JSON): chooses 2-3 assets per persona, each matched to where
   the persona is reachable and grounded in their trigger / objection / language.
3. **GENERATE**: writes each asset in full, streamed.
4. **REFLECT** (strict JSON): scores each asset 0-10 on three criteria —
   `traceable` (claims grounded in the sources), `objection` (addresses the
   persona's documented top objection), `cta` (tied to the buying trigger).
5. **REVISE**: any criterion below 7 triggers a revision (max 2 per asset).

## Usage

```bash
# from the suite root, using the suite venv
.venv/Scripts/python.exe tools/assets/assets.py --company notion

# choose / switch backend (sticky in .env afterwards)
.venv/Scripts/python.exe tools/assets/assets.py --company notion -p cloud -m opus-4.8
.venv/Scripts/python.exe tools/assets/assets.py --company linear -p local
```

Run the upstream synthesis tools first so the sources exist:

```bash
.venv/Scripts/python.exe tools/personas/personas.py --company notion
.venv/Scripts/python.exe tools/positioning_arc/arc.py --company notion
```

## Output

Everything is written under `outputs/<slug>/`:

- `<slug>-content-plan.md` — a summary with a per-asset scores table.
- `<slug>-<persona-slug>-<asset-type-slug>.md` — one file per asset, each with
  YAML frontmatter (company, persona, asset_type, title, scores).

## Requirements

`python-dotenv`, `anthropic` (all from the shared core). No tool-specific
dependencies — see `requirements.txt`. All are already installed in the suite
venv.
