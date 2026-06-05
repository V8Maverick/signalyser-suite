# Signalyser Suite — instructions for Claude Code

A local-first market-intelligence suite. Tools collect a public signal about a
company/market and produce a PMM report, analyzed **locally** (Ollama/Qwen) or in
the **cloud** (Anthropic/Claude), switchable per run via shared flags.

## Shared core (use it — don't reinvent)

All analysis goes through `signalyser_core` (`import signalyser_core as sc`):
- `sc.add_processing_args(parser)` → adds `-p/--processor`, `-m/--model`
- `sc.resolve_processing(args)` → `(processor, model_key)` (call after `sc.load_env()`)
- `sc.print_backend(processor, model_key)` → status line
- `sc.analyze(system, user, processor=, model_key=)` and
  `sc.analyze_large(system, header, body, processor=, model_key=)` for big inputs
- `sc.save_report`, `sc.save_intel`, `sc.read_company_intel`, `sc.SOURCE_IDS`, `sc.slugify`

Never call `anthropic`/`ollama` directly in a tool — route through the core so
local/cloud, fallback, and the API-key flow stay consistent.

## Setup

```bash
./setup.sh        # venv + deps + editable install (pip install -e .)
```
The suite is installed **editable** (`pip install -e .`, run by `setup.sh`) so
`import signalyser_core` / `import signalyser_web` resolve from any cwd.

Tools also **self-heal**: each entry point re-execs under the suite `.venv` (see
`_bootstrap.py` + the shim at the top of every `tools/*/*.py`), so running a tool
with the wrong Python — e.g. the system `python` instead of the venv — Just Works
instead of failing with `ModuleNotFoundError`. Keep that shim above all
third-party imports, and **don't remove `_bootstrap.py`**.

Local mode needs Ollama running (`ollama pull qwen3.5:9b`). Cloud mode needs
`ANTHROPIC_API_KEY` — the tools prompt to paste one (saved to `.env`) or fall
back to local. **Never hardcode or guess an API key.**

## Conventions

- Work is organised into **sessions**: `sessions/<name>/{inputs,outputs}`. The
  active session is sticky in `.env` (`SESSION=`, default `default`). `sc.INPUTS_DIR`
  / `sc.OUTPUTS_DIR` resolve live to the active session (module __getattr__), so the
  same tool code reads/writes the active workspace. Switch/create/delete sessions in
  the web **Sessions** tab; the CLI follows the active session automatically.
- Collectors write `inputs/{company}-{NNN}.md` (within the active session); synthesis
  tools (personas/arc/quadrant) read that corpus; the asset generator (010) consumes
  personas + arc.
- Per-tool code lives in `tools/<name>/`; tests in `tests/test_<name>.py` (offline).
- `tools/reddit/` is the original RedAlyser — keep it self-contained (it has its own
  copies of the processing/env logic; don't couple it to the core). Its report now
  saves into the active session's `outputs/` so it shows in Reports.
- `tools/opportunities/` (011) cross-references a company's corpus with subreddit
  signal (via `signalyser_core.reddit`) → actionable opportunities + SEO keywords,
  saved as a report + `inputs/<slug>-opportunities.md`.
- `tools/cta_tracker/` (012) reads the corpus (all or a `--companies` subset) →
  a matplotlib heatmap of CTA-theme intensity per company + a report. One company
  can be flagged as ours via the sticky `OWN_COMPANY` setting (or `--own`) for
  us-vs-them analysis; the tool enforces the is_own flag itself (never trusts the model).
- `signalyser.py` is the top-level launcher: `python signalyser.py <cmd> [args]`
  dispatches to a tool (page/jobs/tenk/youtube/personas/arc/quadrant/assets/reddit).
- `signalyser_web/` is the web layer (FastAPI): `python -m signalyser_web` serves
  a browser UI on http://localhost:8000 that runs each tool as a subprocess and
  streams its output. It reuses the same `.env` / sticky `-p/-m` as the CLI.
- Console output stays ASCII-only (no box-drawing chars) — the Windows cp1252
  console raises `UnicodeEncodeError` on them.

## Tests

Keep these green after any change:
```bash
.venv/bin/python tests/test_core.py
.venv/bin/python tests/test_<tool>.py
```

## Do not

- Don't put secrets in tracked files; `.env` is gitignored.
- Don't edit `signalyser_core/` casually — every tool depends on it.
