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
`import signalyser_core` / `import signalyser_web` resolve from any cwd. This is
required: tools are launched as subprocesses (by the launcher and the web app)
and would otherwise fail with `ModuleNotFoundError: signalyser_core`.

Local mode needs Ollama running (`ollama pull qwen3.5:9b`). Cloud mode needs
`ANTHROPIC_API_KEY` — the tools prompt to paste one (saved to `.env`) or fall
back to local. **Never hardcode or guess an API key.**

## Conventions

- Collectors write `inputs/{company}-{NNN}.md`; synthesis tools (personas/arc/
  quadrant) read that corpus; the asset generator (010) consumes personas + arc.
- Per-tool code lives in `tools/<name>/`; tests in `tests/test_<name>.py` (offline).
- `tools/reddit/` is the original RedAlyser — **leave it unchanged**.
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
