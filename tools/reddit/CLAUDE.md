# RedAlyser — instructions for Claude Code

RedAlyser mines a subreddit's hot posts + comments and produces a Product
Marketing signal report using a **local Ollama model** (no cloud LLM). Reddit
data is read from **public RSS feeds by default** (no account/API key needed).

## ⚠️ DO THIS FIRST — get the user's Reddit username

**RedAlyser will not run until a Reddit username is configured.** It is required
so requests go out under the *user's own* Reddit handle (in the User-Agent), not
anyone else's. There is intentionally no default.

Before running `reddit_miner.py` for the first time, you MUST:

1. **Ask the user for their Reddit username** if you don't already know it.
   Do not invent one, do not reuse an example, and do not proceed without it.
2. Run the setup script with that username:
   ```bash
   ./setup.sh <their_reddit_username>      # or: bash setup.sh <their_reddit_username>
   ```
   This creates `.venv`, installs dependencies, and writes `REDDIT_USERNAME`
   into `.env`.

If `reddit_miner.py` is run before this, it exits with an error telling the user
to set `REDDIT_USERNAME`. That is expected — set the username, don't work around it.

## Prerequisites the user must have

- **Python 3.10+**
- **[Ollama](https://ollama.com)** running locally with a model pulled:
  ```bash
  ollama pull qwen3.5:9b     # default fallback; runs on ~16 GB RAM / Apple Silicon
  ```
  The default primary model is `qwen3.6:35b-a3b` (~18.5 GiB free RAM). If it
  can't run, RedAlyser automatically falls back to `qwen3.5:9b`. If the user
  only has the 9B model, set `OLLAMA_MODEL=qwen3.5:9b` in `.env`.

## Running

```bash
.venv/bin/python reddit_miner.py <subreddit> [-n NUM] [-p local|cloud] [-m MODEL]   # macOS / Linux
```
`-n` / `--num` = how many top posts to analyze (default 15). The report streams
to the console and is saved to `reddit_signal_<subreddit>_<timestamp>.md`.

## Processing backend (local vs cloud)

- Default is **local** (Ollama/Qwen). `-p cloud` switches to the **Anthropic API**;
  `-p local` switches back. The choice is **sticky** (persisted in `.env`).
- Cloud requires `-m` to pick the model: `Opus-4.8`, `Sonnet-4.6`, or `Haiku-4.5`.
- Cloud needs `ANTHROPIC_API_KEY`. If asked to enable cloud and no key is set,
  ask the user for their key (or have them paste it when the tool prompts). Do not
  invent a key. Without one, the tool falls back to local.

## Tests

After changing logic, run the test suite and keep it green:
```bash
.venv/bin/python _tests.py        # exit 0 = all pass
```

## Do not

- Do not put the user's Reddit **password** in `.env` unless they explicitly ask
  for the authenticated API path (RSS mode needs no password).
- Do not hardcode or guess an `ANTHROPIC_API_KEY` — it must come from the user.
- Do not commit `.env` (it is gitignored).
