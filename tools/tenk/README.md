# 10-K / Earnings Analyzer (006)

Pulls a company's most recent annual SEC filing (10-K, or 20-F for foreign
filers) straight from EDGAR, strips it to plain text, and runs it through the
shared Signalyser analysis backend to produce a structured **PMM signal
report** — how the company describes its market, where it's investing vs
pulling back, the risk factors a competitor should know, who it names as
competition, and what shifted from prior years.

## Usage

From the suite root, using the suite's virtualenv:

```bash
# Cloud (single pass — recommended for huge 10-Ks):
.venv/Scripts/python tools/tenk/analyse.py CRM -p cloud -m opus-4.8

# Local (Ollama; map-reduces the filing across chunks):
.venv/Scripts/python tools/tenk/analyse.py CRM -p local
```

`-p` (processor) and `-m` (cloud model) are **sticky** — once set they persist
in `.env` for every run until changed, so subsequent runs only need the ticker:

```bash
.venv/Scripts/python tools/tenk/analyse.py MSFT
```

### Arguments

| Arg | Description |
|-----|-------------|
| `ticker` | Stock ticker symbol, e.g. `CRM`, `MSFT`, `MNDY` (required, positional). |
| `-p, --processor` | `local` (Ollama) or `cloud` (Anthropic). Sticky. |
| `-m, --model` | Cloud model: `opus-4.8` \| `sonnet-4.6` \| `haiku-4.5`. Sticky. |

## How it works

1. **CIK lookup** — `GET company_tickers.json`, match the ticker, zero-pad the
   CIK to 10 digits.
2. **Latest filing** — `GET submissions/CIK{cik}.json`, take the most recent
   `10-K` (or `20-F`) accession + primary document.
3. **Fetch + strip** — download the primary document from the EDGAR Archives and
   strip HTML to plain text. Input is capped at ~200,000 characters.
4. **Analyse** — `sc.analyze_large(...)`: cloud runs a single pass; local
   map-reduces the filing to fit the model's context window.

> SEC requires a descriptive `User-Agent` on every request. This tool sends
> `signalyser-suite (contact@example.com)`.

## Output

- A timestamped report in `outputs/` (via `sc.save_report`).
- An intel file in the shared corpus at `inputs/<ticker-slug>-006.md` (via
  `sc.save_intel`), so downstream suite tools (positioning arc, quadrant, etc.)
  can read it.

## Requirements

Nothing beyond the shared core (`requests`, `python-dotenv`, `anthropic`) — see
`requirements.txt`.
