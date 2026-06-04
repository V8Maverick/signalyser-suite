#!/usr/bin/env python3
"""
YouTube Video Summarizer — Signalyser Suite, tool 001.

Takes a YouTube URL, extracts the transcript, and uses the suite's shared
analysis backend (local Ollama or cloud Anthropic) to generate a structured
B2B-marketer summary: a one-sentence TL;DR, 3 key takeaways, and 1 action.

Usage:
    python summarize.py https://www.youtube.com/watch?v=XXXXXXXXXXX
    python summarize.py                # prompts for the URL

Backend selection (shared across the suite, sticky in .env):
    -p local|cloud      processing backend (Ollama vs Anthropic)
    -m opus-4.8|...      cloud model (cloud only)
"""

# Self-heal: re-exec under the suite .venv so signalyser_core and third-party deps
# resolve no matter which Python / working dir launched this tool. See _bootstrap.py.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if __name__ == "__main__":
    import _bootstrap
    _bootstrap.ensure_venv(__file__)

import argparse
import re
import sys

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

import signalyser_core as sc

# ── YouTube helpers ───────────────────────────────────────────────────────────

# Common YouTube URL forms: watch?v=, youtu.be/, /embed/, /shorts/. The video id
# is the canonical 11-char [A-Za-z0-9_-] token.
_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?(?:[^&]*&)*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)"
    r"([a-zA-Z0-9_-]{11})"
)


def extract_video_id(url: str) -> str:
    """Extract the 11-character video ID from any common YouTube URL format."""
    match = _VIDEO_ID_RE.search(url)
    if not match:
        raise ValueError(
            f"Could not find a YouTube video ID in: {url}\n"
            "Accepted forms: watch?v=ID | youtu.be/ID | /embed/ID | /shorts/ID"
        )
    return match.group(1)


def get_transcript(video_id: str) -> str:
    """Download and concatenate the video transcript into a single text blob.

    Tries English first, then falls back to any available language.
    """
    api = YouTubeTranscriptApi()
    try:
        try:
            fetched = api.fetch(video_id, languages=["en"])
        except (NoTranscriptFound, CouldNotRetrieveTranscript):
            transcript_list = api.list(video_id)
            fetched = next(iter(transcript_list)).fetch()
    except TranscriptsDisabled:
        raise RuntimeError("Transcripts are disabled for this video.")
    except (NoTranscriptFound, CouldNotRetrieveTranscript):
        raise RuntimeError(
            "No transcript found. The video may not have captions enabled."
        )
    return " ".join(snippet.text for snippet in fetched.snippets)


# ── Analysis ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior B2B marketing strategist. When given a YouTube video transcript,
you extract the most relevant insights and turn them into a concise, actionable
summary that a busy marketer can read in under two minutes.

Always respond with exactly the five labeled lines below — nothing else:

TL;DR: <one sentence capturing the core message>
Key Takeaway 1: <first key insight>
Key Takeaway 2: <second key insight>
Key Takeaway 3: <third key insight>
Action for B2B Marketers: <one specific, practical recommendation>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize a YouTube video for B2B marketers."
    )
    parser.add_argument(
        "url", nargs="?",
        help="YouTube URL (watch?v= | youtu.be/ | /embed/ | /shorts/). "
             "If omitted, you'll be prompted for it.",
    )
    sc.add_processing_args(parser)
    args = parser.parse_args()

    # Accept the URL from the command line or an interactive prompt.
    url = (args.url or "").strip()
    if not url:
        url = input("Paste a YouTube URL: ").strip()
    if not url:
        print("No URL provided. Exiting.")
        sys.exit(1)

    # Load credentials and resolve the shared backend (sticky via .env).
    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    print(f"\nProcessing: {url}\n")

    # 1 — Video ID
    try:
        video_id = extract_video_id(url)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    # 2 — Transcript
    print("Extracting transcript ...")
    try:
        transcript = get_transcript(video_id)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    print(f"  -> {len(transcript.split()):,} words extracted\n")

    # 3 — Analyze (transcripts can be long; analyze_large map-reduces for local)
    report = sc.analyze_large(
        SYSTEM_PROMPT,
        header=f"YouTube video: {url}",
        body=transcript,
        processor=processor,
        model_key=model_key,
    )

    # 4 — Save
    path = sc.save_report(video_id, report)
    print("\n" + "-" * 60 + "\n")
    print(report)
    print("\n" + "-" * 60)
    print(f"\nSaved to: {path}")


if __name__ == "__main__":
    main()
