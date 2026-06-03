# Job Posting Analyzer

Fetches a company's current open roles from **Ashby's public posting API** (with an automatic **Greenhouse** fallback), builds a compact digest, and sends it to the shared Signalyser analysis backend — a **local Ollama model (Qwen)** *or* the **cloud Anthropic API (Claude)** — to produce a PMM **Job Signal Report**.

The report surfaces hiring signals a product marketer can act on: where the company is hiring (by department), keywords repeated across postings, technology/tool bets, inferred strategic priorities, and concrete PMM action items.

Part of the **Signalyser** market-intelligence suite. Tool id: **005** (jobs).

## Prerequisites

- **Python 3.10+**
- The suite virtualenv with the shared core installed. All analysis runs through `signalyser_core`; the only third-party dependency this tool adds is `requests` (already in the core).
- For **cloud** analysis: an `ANTHROPIC_API_KEY` (the tool offers to save a pasted key to `.env`).
- For **local** analysis: a running [Ollama](https://ollama.com) server with a Qwen model pulled.

No authentication is needed to fetch jobs — both Ashby and Greenhouse expose public, read-only job-board endpoints.

## Run

From the suite root, using the suite's Python:

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\python.exe tools\job_postings\analyse.py <slug>
```

**macOS / Linux:**
```bash
.venv/bin/python tools/job_postings/analyse.py <slug>
```

`<slug>` is the company's job-board slug (e.g. `notion`, `vercel`) or a full job-board URL — `https://jobs.ashbyhq.com/<slug>` or `https://boards.greenhouse.io/<slug>` — from which the slug is extracted automatically.

Examples:
```bash
.venv/bin/python tools/job_postings/analyse.py notion
.venv/bin/python tools/job_postings/analyse.py https://jobs.ashbyhq.com/dash0
.venv/bin/python tools/job_postings/analyse.py ramp -p cloud -m opus-4.8
```

## Processing backend (local vs cloud)

Like every Signalyser tool, analysis runs either **locally** with Ollama/Qwen (default, free, private) or in the **cloud** with the Anthropic API (Claude). The choice is **sticky** — once set with `-p` it persists in `.env` for every run until changed. Each run prints which backend and model it's using, e.g. `Using Cloud Processing with model Opus-4.8`.

- **`-p` / `--processor`** — `local` or `cloud`.
- **`-m` / `--model`** — cloud model: `Opus-4.8`, `Sonnet-4.6`, or `Haiku-4.5` (required the first time you switch to cloud).

These flags are provided by the shared core (`sc.add_processing_args` / `sc.resolve_processing`), so they behave identically across all tools in the suite.

## How it works

1. **Fetch** — calls Ashby's public posting API: `GET https://api.ashbyhq.com/posting-api/job-board/{slug}`. If that board is missing or returns no postings, it falls back to Greenhouse: `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`.
2. **Extract** — per job: title, department, location, and a plain-text description (HTML stripped, capped at 1500 chars).
3. **Digest** — serialises the roles into one compact text block.
4. **Analyze** — sends the digest to the selected backend via `sc.analyze` with a PMM job-signal system prompt.
5. **Save** — writes the report two ways:
   - a timestamped report to `outputs/` via `sc.save_report("<slug>-jobs", report)`
   - a shared-corpus intel file to `inputs/<slug>-005.md` via `sc.save_intel(slug, sc.SOURCE_IDS["jobs"], report)`, so downstream suite tools can read it.

## Report format

```
## Job Signal Report: <company>

### Where they're hiring (by department)
### Repeated keywords across postings
### Technology and tool signals
### Inferred strategic priorities
### PMM action items
```

## Tests

Offline tests (mock `requests.get`; no network, no model call):
```bash
.venv/bin/python tests/test_job_postings.py     # exit 0 = all pass
```

They verify (a) Ashby JSON is parsed into jobs and a digest is built, and (b) when Ashby returns no jobs the Greenhouse fallback is used.

## Files

- `analyse.py` — the tool.
- `requirements.txt` — none beyond the shared core.
- `README.md` — this file.
