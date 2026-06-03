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
signalyser_core/        # shared engine: local/cloud analyze, sticky -p/-m, .env, io, chunking
tools/
  reddit/               # 003 Reddit Signal (verbatim RedAlyser — self-contained)
  page_decoder/         # 004 Competitor page -> strategic briefing
  job_postings/         # 005 Ashby/Greenhouse jobs -> hiring signals
  tenk/                 # 006 SEC 10-K -> competitive intel
  youtube/              # 001 YouTube transcript -> B2B summary
  personas/             # 009 intel -> evidence-based buyer personas
  positioning_arc/      # 008 intel -> 3-horizon positioning arc
  quadrant/             # 007 intel -> competitive quadrant chart
inputs/                 # shared corpus: {company}-{NNN}.md (gitignored)
outputs/                # generated reports/charts (gitignored)
tests/                  # offline tests (core + per tool)
```

**Pipeline:** collectors (004/005/006/001 + reddit) write `inputs/{company}-{NNN}.md`
→ synthesis (009/008/007) read that corpus → (planned 010 asset generator) consumes
personas + positioning.

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
./setup.sh              # macOS/Linux: venv + all deps
# Windows: py -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

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

# Flip to cloud (sticky thereafter)
$PY tools/page_decoder/decode.py https://www.linear.app -p cloud -m sonnet-4.6
```

The reddit tool keeps its own interface (`tools/reddit/`, see its README).

## Tests

```bash
.venv/bin/python tests/test_core.py        # shared engine
.venv/bin/python tests/test_<tool>.py      # per tool (offline, no network/LLM)
```

## Status

Phase 1 (core) ✅ · Phase 2–4 (collectors + synthesis) in progress ·
Phase 5 (010 asset generator + `redalyser`/`signalyser` launcher) planned ·
G2 (002) skipped (paid Firecrawl + anti-scraping). See `../RedAlyser/SUITE_PLAN.md`.
