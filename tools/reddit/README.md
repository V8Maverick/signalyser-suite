# Reddit Signal Miner

Pulls hot posts + top comments from any subreddit, sends them to a **local Ollama model (Qwen)** *or* the **cloud Anthropic API (Claude)** for PMM analysis, and saves a structured markdown report.

By default it runs entirely on your machine and reads Reddit's **public RSS feeds — no account, no credentials, no API approval needed.** You can switch analysis to the cloud with `-p cloud` (see [Processing backend](#processing-backend-local-vs-cloud)). Optionally, if you have Reddit API credentials, it will use the authenticated Reddit API instead of RSS (richer data). Cross-platform: Windows, macOS (incl. Apple Silicon), and Linux.

> Adapted from the upstream version, which used Claude via the Anthropic API. Analysis now runs locally through Ollama. Reddit's unauthenticated `.json` endpoints return `403 Blocked` and new API apps are gated behind Reddit's "Responsible Builder Policy" approval, so the default path uses public RSS feeds, which remain open.

## ⚠️ Set your Reddit username first (required)

**RedAlyser will not run until you set your own Reddit username.** It's used in
the request User-Agent so traffic goes out under *your* handle (Reddit asks for
this). There is no default — you must provide it.

The quickest way (macOS / Linux) is the setup script, which also creates the
virtualenv and installs dependencies:

```bash
./setup.sh <your_reddit_username>      # e.g. ./setup.sh jane_doe
```

(If you skip this, running the tool prints an error telling you to set
`REDDIT_USERNAME`. See [Setup](#setup) for the manual/Windows steps.)

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** running locally with at least one model pulled.

Pull the model(s) you want (same command on every OS):

```
ollama pull qwen3.5:9b          # ~6.6 GB, runs comfortably on ~16 GB RAM / Apple Silicon
ollama pull qwen3.6:35b-a3b     # ~23 GB, needs ~18.5 GiB free; optional
```

The default **primary** model is `qwen3.6:35b-a3b`; if it can't run (e.g. not pulled, or low memory), the tool **automatically falls back** to `OLLAMA_FALLBACK_MODEL` (default `qwen3.5:9b`). If you only intend to use the 9B model, set `OLLAMA_MODEL=qwen3.5:9b` (see Setup) to make it primary and skip the fallback step.

> **macOS (Apple Silicon, e.g. M1):** install Ollama with `brew install ollama`, then start the server with `ollama serve` (or launch the Ollama app). `qwen3.5:9b` runs well on M1 via Metal.

## Setup

### macOS / Linux (recommended: setup script)

```bash
./setup.sh <your_reddit_username>
```
This creates `.venv`, installs dependencies, and writes your `REDDIT_USERNAME`
into `.env`. (If the file isn't executable: `bash setup.sh <your_reddit_username>`.)

### Windows (PowerShell) — manual

There's no `.ps1` yet, so do it by hand:
```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# then edit .env and set:  REDDIT_USERNAME=your_reddit_username
```

### Optional settings (in `.env`)

- **Use the 9B model as primary** (recommended if you're not running the 35B):
  ```
  OLLAMA_MODEL=qwen3.5:9b
  ```
- **Use the authenticated Reddit API instead of RSS** (only if you have an
  approved Reddit script app):
  ```
  REDDIT_CLIENT_ID=your_client_id_here
  REDDIT_CLIENT_SECRET=your_client_secret_here
  ```
  Add `REDDIT_PASSWORD` (with your username) for a user-context grant; leave it
  blank for read-only. If no credentials are present, the tool uses public RSS
  automatically.

## Run

**macOS / Linux:**
```bash
.venv/bin/python reddit_miner.py <subreddit> [-n NUM]
```

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\python.exe reddit_miner.py <subreddit> [-n NUM]
```

`-n` / `--num` sets how many top posts to analyze (default: 15).

Examples (macOS / Linux):
```bash
.venv/bin/python reddit_miner.py projectmanagement
.venv/bin/python reddit_miner.py SaaS -n 25
.venv/bin/python reddit_miner.py devops -n 10
```

Force a specific local model for a single run (otherwise it tries the primary, then falls back):

```bash
# macOS / Linux
OLLAMA_MODEL=qwen3.5:9b .venv/bin/python reddit_miner.py devops
```
```powershell
# Windows (PowerShell)
$env:OLLAMA_MODEL="qwen3.5:9b"; .\.venv\Scripts\python.exe reddit_miner.py devops
```

## Processing backend (local vs cloud)

RedAlyser can analyze either **locally** with Ollama/Qwen (default, free, private) or in the **cloud** with the Anthropic API (Claude). The choice is **sticky** — once you set it with `-p`, it persists in `.env` for every run until you change it. Each run prints which backend and model it's using, e.g. `Using Cloud Processing with model Opus-4.8`.

```bash
# Switch to cloud — -m picks the Claude model (required when switching to cloud)
.venv/bin/python reddit_miner.py devops -p cloud -m opus-4.8

# Subsequent runs stay on cloud automatically — no flags needed
.venv/bin/python reddit_miner.py SaaS

# Switch back to local (Ollama). -m is not used for local.
.venv/bin/python reddit_miner.py devops -p local
```

- **`-p` / `--processor`** — `local` or `cloud`.
- **`-m` / `--model`** — cloud model: `Opus-4.8`, `Sonnet-4.6`, or `Haiku-4.5`. Switching to cloud without `-m` (and no previously saved model) prints `Which model? Opus-4.8 | Sonnet-4.6 | Haiku-4.5?`.
- **API key** — cloud needs `ANTHROPIC_API_KEY`. If it isn't in `.env`, the tool prompts you to paste one (and saves it to `.env`); press Enter to fall back to local instead.

## Configuration

All settings are read from `.env` (or the environment):

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROCESSOR` | `local` | Analysis backend: `local` (Ollama) or `cloud` (Anthropic). Sticky; set via `-p`. |
| `CLOUD_MODEL` | *(none)* | Cloud model: `opus-4.8` / `sonnet-4.6` / `haiku-4.5`. Sticky; set via `-m`. |
| `ANTHROPIC_API_KEY` | *(none)* | Required for cloud processing. Tool offers to save a pasted key here. |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL (local) |
| `OLLAMA_MODEL` | `qwen3.6:35b-a3b` | Primary local model used for analysis |
| `OLLAMA_FALLBACK_MODEL` | `qwen3.5:9b` | Used automatically if the primary can't run (e.g. low memory) |
| `REDDIT_USERNAME` | **(required)** | Your Reddit handle; used in the User-Agent. The tool won't run without it. |
| `REDDIT_CLIENT_ID` | *(optional)* | Reddit script app — switches to the authenticated API |
| `REDDIT_CLIENT_SECRET` | *(optional)* | Reddit script app secret |
| `REDDIT_PASSWORD` | *(optional)* | With the username, enables a user-context (password) grant |

## Output

The report streams to stdout as the model generates it, then saves to a timestamped file:

```
reddit_signal_devops_20260602_102917.md
```

## Report format

```
## Reddit Signal Report: r/<subreddit>

### Top recurring complaints
### Top recurring praise
### Exact Reddit language
### Questions nobody is answering well
### Emerging themes
### PMM action items
```

## How it works

1. Picks a data source: if `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` are set, it authenticates via OAuth2 and uses `https://oauth.reddit.com`; otherwise it uses public RSS feeds (`https://www.reddit.com/r/{subreddit}/hot.rss`) — no credentials.
2. Fetches the top *N* hot posts (`-n`, default 15) and up to 8 top comments each.
3. Formats posts + comments into a structured prompt.
4. Streams the prompt to the analysis backend: **local** Ollama (`OLLAMA_MODEL`, with automatic fallback to `OLLAMA_FALLBACK_MODEL` if it can't run), or **cloud** Anthropic (`CLOUD_MODEL`) when `PROCESSOR=cloud`.
5. Saves the markdown report to a timestamped file.

A 0.5 s delay is added between Reddit requests to be polite.

## Tests

```bash
.venv/bin/python _tests.py      # selection logic + helpers; exit 0 = all pass
```

## Files

- `reddit_miner.py` — the tool (local Ollama or cloud Anthropic; Reddit RSS with optional OAuth API).
- `reddit_miner.original.py` — the unmodified upstream version (Claude + unauthenticated JSON), kept for reference.
- `_tests.py` — fast tests for processor selection and helpers (no network/model needed).
- `.env.example` — template for optional config (processor, models, credentials).
