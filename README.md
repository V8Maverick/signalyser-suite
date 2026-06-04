# Signalyser Suite

A local-first **market-intelligence suite** for Product Marketing. Each tool
collects a public signal about a company/market and turns it into a structured
PMM report — running **locally** on Ollama/Qwen by default, or in the **cloud**
on the Anthropic API (Claude), switchable per run.

Built by adapting the `marketer-that-ships` experiments onto a shared engine
(`signalyser_core`) with switchable processing and free/public data sources.
The original **RedAlyser** Reddit tool is included verbatim and unchanged under
`tools/reddit/`.

## Architecture

```
signalyser.py           # one launcher for every tool (python signalyser.py <cmd> ...)
pyproject.toml          # editable install metadata (pip install -e .)
signalyser_core/        # shared engine: local/cloud analyze, sticky -p/-m, .env, io, chunking
signalyser_web/         # FastAPI web UI (python -m signalyser_web) — forms + live run streaming
tools/
  reddit/               # 003 Reddit Signal (verbatim RedAlyser — self-contained)
  page_decoder/         # 004 Competitor page -> strategic briefing
  job_postings/         # 005 Ashby/Greenhouse jobs -> hiring signals
  tenk/                 # 006 SEC 10-K -> competitive intel
  youtube/              # 001 YouTube transcript -> B2B summary
  personas/             # 009 intel -> evidence-based buyer personas
  positioning_arc/      # 008 intel -> 3-horizon positioning arc
  quadrant/             # 007 intel -> competitive quadrant chart
  assets/               # 010 personas + positioning -> written assets (reflection loop)
sessions/               # named workspaces: <name>/{inputs,outputs} (gitignored)
tests/                  # offline tests (core + per tool)
```

## Sessions

Work is organised into **sessions** — named workspaces, each with its own intel
corpus and reports, under `sessions/<name>/{inputs,outputs}`. This keeps separate
analyses from mixing and lets you start fresh without deleting anything.

- The **active session** is sticky in `.env` (`SESSION=`, default `default`),
  shared by the CLI and the web UI. Collectors write into it; synthesis tools read
  from it.
- Manage sessions in the web **Sessions** tab: create + switch, browse a session's
  corpus/reports, or delete one. The CLI automatically follows the active session
  (no extra flags).

**Pipeline:** collectors (004/005/006/001 + reddit) write `inputs/{company}-{NNN}.md`
→ synthesis (009/008/007) read that corpus → the asset generator (010) consumes
the personas + positioning arc and writes persona-targeted assets.

## Web UI

A FastAPI front end gives every tool a browser-based form, so you don't have to
remember each tool's flags:

```bash
python -m signalyser_web            # serves http://localhost:8000 (flags: --host/--port/--reload)
```

Then open <http://localhost:8000>. Four tabs:

- **Tools** — pick a tool, fill its form, and launch a run; output **streams live**
  in the browser (each tool runs as the same subprocess the launcher uses).
- **Corpus** — browse the collected `inputs/{company}-{NNN}.md` intel.
- **Reports** — browse generated `outputs/` reports and charts.
- **Settings** — the GUI for the sticky `-p/-m` backend selectors and the
  `ANTHROPIC_API_KEY`.

The web app **reuses the same `.env`** as the CLI: the Settings tab and the
`-p/-m` flags are two front ends to one sticky config, so they stay in sync.

> The suite must be installed editable (`pip install -e .`, done by `setup.sh`)
> for the web app to work: it launches each tool as a subprocess, and those
> children need to `import signalyser_core` from any working directory.

## Processing backend (local vs cloud)

Every tool takes the same flags, shared from the core:

```
-p, --processor   local | cloud      # sticky: persists in .env until changed
-m, --model       Opus-4.8 | Sonnet-4.6 | Haiku-4.5   # cloud only
```

- **Local (default):** Ollama, primary `qwen3.6:35b-a3b` with automatic fallback
  to `qwen3.5:9b`. Free, private, offline.
- **Cloud:** Anthropic API; needs `ANTHROPIC_API_KEY` (the tool offers to save a
  pasted key to `.env`, else falls back to local).
- Large inputs (10-K, long pages): cloud analyzes in one pass; local map-reduces
  to fit context (slower/lossier — a notice is printed).

## Setup

```bash
./setup.sh              # macOS/Linux: venv + all deps + editable install (pip install -e .)
# Windows:
#   py -m venv .venv
#   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
#   .\.venv\Scripts\python.exe -m pip install -e .   # editable install of the suite
```

The editable install (`pip install -e .`) makes `import signalyser_core` /
`import signalyser_web` resolve from any working directory.

You don't have to remember to use the venv's Python, either: every tool
**self-heals** — if you launch it with the wrong interpreter (e.g. a bare
`python tools/page_decoder/decode.py ...` that resolves to the system Python), it
transparently re-execs itself under the suite `.venv`. So direct runs, the
launcher, and the web app all work regardless of which `python` you type.

Ollama must be running with a model pulled for local mode:
```bash
ollama pull qwen3.5:9b
```

## Usage (examples)

```bash
PY=.venv/bin/python      # Windows: .\.venv\Scripts\python.exe

# Collect (writes inputs/{company}-NNN.md)
$PY tools/page_decoder/decode.py https://www.notion.com
$PY tools/job_postings/analyse.py notion
$PY tools/tenk/analyse.py CRM
$PY tools/youtube/summarize.py https://youtu.be/<id>

# Synthesize from the collected corpus
$PY tools/personas/personas.py --company notion
$PY tools/positioning_arc/arc.py --company notion
$PY tools/quadrant/quadrant.py

# Generate persona-targeted written assets (capstone)
$PY tools/assets/assets.py --company notion

# ...or drive any tool through the one launcher
$PY signalyser.py page https://www.notion.com
$PY signalyser.py assets --company notion

# Flip to cloud (sticky thereafter)
$PY tools/page_decoder/decode.py https://www.linear.app -p cloud -m sonnet-4.6
```

The reddit tool keeps its own interface (`tools/reddit/`, see its README).

## Tests

```bash
.venv/bin/python tests/test_core.py        # shared engine
.venv/bin/python tests/test_<tool>.py      # per tool (offline, no network/LLM)
.venv/bin/python tests/test_web.py         # web UI (offline, via TestClient — no server)
```

## Status

Phase 1 (core) ✅ · Phase 2–4 (collectors + synthesis) ✅ ·
Phase 5 (010 asset generator + `signalyser` launcher) ✅ ·
G2 (002) skipped (paid Firecrawl + anti-scraping). See `../RedAlyser/SUITE_PLAN.md`.

All tools run offline-tested green (`tests/test_*.py`). Live model runs (local
Ollama / cloud Anthropic) are exercised manually, not in the test suite.
