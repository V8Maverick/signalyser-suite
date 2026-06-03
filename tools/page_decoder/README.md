# Competitor Page Decoder (004)

Fetch a competitor's web page, strip it to clean visible text, and have a senior
PMM decode their positioning into a tight strategic briefing.

Part of the Signalyser market-intelligence suite. Analysis runs through the
shared `signalyser_core` backend, so it supports the same sticky local (Ollama)
vs cloud (Anthropic) processor selection as every other tool.

## What it does

1. Fetches the URL with a browser-like User-Agent.
2. Strips nav / header / footer / scripts / styles / cookie-and-consent banners
   with BeautifulSoup, then collapses whitespace to clean text.
3. Sends the text to the model under a PMM system prompt that produces:
   - **Their core pitch** — one sentence
   - **Who they're targeting**
   - **Top 3 positioning bets**
   - **What they're NOT saying**
   - **PMM actions**
4. Pages can be long, so analysis goes through `sc.analyze_large` (cloud =
   single pass; local = map-reduce across chunks).

## Usage

```bash
# from the suite root, using the suite venv
.venv/Scripts/python.exe tools/page_decoder/decode.py https://www.notion.com

# choose / switch backend (sticky in .env afterwards)
.venv/Scripts/python.exe tools/page_decoder/decode.py notion.com -p cloud -m opus-4.8
.venv/Scripts/python.exe tools/page_decoder/decode.py https://linear.app -p local
```

A bare domain (`notion.com`) is fine — `https://` is added automatically.

## Output

The briefing is saved twice:

- `outputs/<slug>-page_<timestamp>.md` — a timestamped report.
- `inputs/<slug>-004.md` — the company intel file that joins the suite's shared
  corpus, where `<slug>` is derived from the URL domain (e.g.
  `https://www.notion.com` -> `notion`) and `004` is this tool's source id.

## Requirements

`requests`, `python-dotenv`, `beautifulsoup4`, `lxml` (see `requirements.txt`).
All are already installed in the suite venv.
