# Persona Generator (009)

Read every intel file a company has accumulated in the shared corpus and have a
senior PMM synthesise 2-3 evidence-based buyer personas — where every attribute
traces back to a specific source file/signal.

Part of the Signalyser market-intelligence suite. Analysis runs through the
shared `signalyser_core` backend, so it supports the same sticky local (Ollama)
vs cloud (Anthropic) processor selection as every other tool.

## What it does

1. Reads all `inputs/<company>-*.md` intel files via `sc.read_company_intel`
   (produced by the collector tools: page / jobs / 10-K, etc.). Exits with a
   clear error if the company has no intel yet.
2. Concatenates the intel files, each labelled by filename, into one prompt.
3. Sends them to the model under a PMM system prompt that produces 2-3 personas,
   each with:
   - **PERSONA NAME** — a real job title
   - **EVIDENCE BASE** — which files/signals revealed this persona
   - **WHO THEY ARE**, **WHAT THEY ARE TRYING TO DO**
   - **WHY THEY BUY**, **WHY THEY DON'T BUY**
   - **EXACT LANGUAGE THEY USE** — verbatim quotes from the sources
   - **WHERE TO REACH THEM**
   - **SEGMENT PRIORITY RECOMMENDATION**

   Every attribute traces to a source; inferred fields are flagged `(inferred)`.

## Usage

```bash
# from the suite root, using the suite venv
.venv/Scripts/python.exe tools/personas/personas.py --company notion

# choose / switch backend (sticky in .env afterwards)
.venv/Scripts/python.exe tools/personas/personas.py --company notion -p cloud -m opus-4.8
.venv/Scripts/python.exe tools/personas/personas.py --company linear -p local
```

Run the collectors first so there is intel to synthesise — otherwise the tool
exits with: `No intel for <company> in inputs/ — run collectors first
(page/jobs/10-K).`

## Output

The personas document is saved twice:

- `outputs/<slug>-personas_<timestamp>.md` — a timestamped report.
- `inputs/<slug>-personas.md` — so the downstream asset generator can read it.

## Requirements

`requests`, `python-dotenv`, `anthropic` (all from the shared core). No
tool-specific dependencies — see `requirements.txt`. All are already installed in
the suite venv.
