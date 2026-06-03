# Competitive Quadrant

Turns the suite's shared competitive-intelligence corpus into a positioning map.
Instead of generic axes ("vision vs execution", "price vs quality"), it asks the
model to derive the **two most differentiating axes for THIS specific set of
companies**, grounded in the evidence, then places each company on a -10..+10
scale for both and plots a quadrant chart.

Part of the Signalyser suite — analysis runs through the shared core
(`signalyser_core`), so it uses the same switchable Local (Ollama/Qwen) vs Cloud
(Anthropic/Claude) backend and the same sticky `-p` / `-m` selection as every
other tool.

## Usage

```bash
# From the suite root, using the suite's venv:
.venv/Scripts/python.exe tools/quadrant/quadrant.py [--inputs DIR] [-p local|cloud] [-m MODEL]
```

- `--inputs DIR` — folder of `.md` intelligence files. Defaults to the suite's
  shared `inputs/` folder.
- `-p local|cloud` — processing backend (sticky; persists in `.env`).
- `-m opus-4.8 | sonnet-4.6 | haiku-4.5` — cloud model (cloud only, sticky).

### How inputs are grouped

Every `*.md` in the inputs dir is grouped by **company = the filename prefix
before the first `-`**, and each company's files are concatenated. This matches
the suite's shared naming, e.g. `acme-004.md`, `acme-006.md`, `globex-005.md`
→ companies `acme`, `globex`. At least two companies are required.

## Outputs

Written to the suite `outputs/` folder:

- `quadrant-1.png` — the quadrant chart (rendered headless via the matplotlib
  Agg backend; no display needed).
- `axes-rationale.md` — the derived axis definitions (what the low/high ends
  mean) plus a one-line rationale for each company's placement.

If the model returns text that isn't valid quadrant JSON, the tool prints the
raw output and exits with status 1.

## Testing

Offline tests (no network, no LLM):

```bash
.venv/Scripts/python.exe tests/test_quadrant.py
```

They feed canned JSON (including ```` ```json ```` fenced) to the parser and call
the plotting function on sample data, asserting a real PNG is written.
