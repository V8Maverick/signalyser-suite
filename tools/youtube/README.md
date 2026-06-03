# YouTube Summarizer (tool 001)

Turn any YouTube video into a tight B2B-marketing brief. Given a URL, the tool
pulls the video transcript and runs it through the Signalyser shared analysis
backend (local Ollama **or** cloud Anthropic) to produce:

- a one-sentence **TL;DR**
- **3 key takeaways**
- **1 recommended action** for a B2B marketer

The summary is printed to the terminal and saved as a timestamped markdown
report under the suite's shared `outputs/` directory.

## Usage

```bash
# From the suite root, using the suite venv:
.venv/Scripts/python.exe tools/youtube/summarize.py https://www.youtube.com/watch?v=XXXXXXXXXXX

# Omit the URL to be prompted for it:
.venv/Scripts/python.exe tools/youtube/summarize.py
```

Accepted URL forms:

- `https://www.youtube.com/watch?v=VIDEOID`
- `https://youtu.be/VIDEOID`
- `https://www.youtube.com/embed/VIDEOID`
- `https://www.youtube.com/shorts/VIDEOID`

## Backend selection

The processing backend is shared across the suite and sticky in `.env`:

```bash
# Use cloud (Anthropic) with a specific model — persists for later runs:
.venv/Scripts/python.exe tools/youtube/summarize.py <url> -p cloud -m opus-4.8

# Switch back to local (Ollama):
.venv/Scripts/python.exe tools/youtube/summarize.py <url> -p local
```

- `-p local|cloud` — backend (Local Ollama or Cloud Anthropic). Sticky.
- `-m opus-4.8 | sonnet-4.6 | haiku-4.5` — cloud model (cloud only). Sticky.

Long transcripts are handled automatically: cloud analyzes in a single pass,
while local map-reduces the transcript into context-sized chunks before
synthesizing the final summary.

## Requirements

- `youtube-transcript-api` (see `requirements.txt`)
- The shared `signalyser_core` package and its dependencies (installed at the
  suite level)
- For cloud processing, an `ANTHROPIC_API_KEY` in the suite `.env`

## Notes

- The video must have captions/transcripts available; videos with transcripts
  disabled cannot be summarized.
- Output filenames are derived from the video ID plus a timestamp.
