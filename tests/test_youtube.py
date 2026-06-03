"""Offline tests for the YouTube summarizer (tool 001). No network/model.

Run:  .venv/Scripts/python.exe tests/test_youtube.py   (exit 0 = all pass)

Covers:
  - video-id extraction across common URL forms
  - transcript assembly with a mocked youtube_transcript_api
  - the system prompt / body wiring into sc.analyze_large (sc.analyze stubbed)
"""
import sys
from pathlib import Path

# Make the suite root (for signalyser_core) and the tool dir (for summarize)
# importable when run directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "youtube"))

import signalyser_core as sc
import summarize

failures = []


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


# ── 1. Video-id extraction across URL forms ────────────────────────────────────
VID = "dQw4w9WgXcQ"
url_cases = {
    "watch?v=": f"https://www.youtube.com/watch?v={VID}",
    "watch?v= with extra params": f"https://www.youtube.com/watch?v={VID}&t=42s",
    "watch with leading params": f"https://www.youtube.com/watch?feature=share&v={VID}",
    "youtu.be": f"https://youtu.be/{VID}",
    "youtu.be with query": f"https://youtu.be/{VID}?t=10",
    "embed": f"https://www.youtube.com/embed/{VID}",
    "shorts": f"https://www.youtube.com/shorts/{VID}",
    "no scheme": f"youtu.be/{VID}",
}
for label, url in url_cases.items():
    try:
        got = summarize.extract_video_id(url)
        check(f"extract id [{label}]", got == VID)
    except Exception as exc:  # noqa: BLE001 - test harness
        check(f"extract id [{label}] (raised {exc!r})", False)

# Invalid URL → ValueError
try:
    summarize.extract_video_id("https://example.com/not-a-video")
    check("invalid url raises ValueError", False)
except ValueError:
    check("invalid url raises ValueError", True)
except Exception:  # noqa: BLE001
    check("invalid url raises ValueError", False)


# ── 2. Transcript assembly (mock youtube_transcript_api) ───────────────────────
class _Snippet:
    def __init__(self, text):
        self.text = text


class _Fetched:
    def __init__(self, texts):
        self.snippets = [_Snippet(t) for t in texts]


class _FakeApi:
    """Stand-in for YouTubeTranscriptApi returning a fixed transcript."""
    def __init__(self):
        pass

    def fetch(self, video_id, languages=None):
        return _Fetched(["Hello world.", "This is a fake", "transcript."])


orig_api = summarize.YouTubeTranscriptApi
summarize.YouTubeTranscriptApi = _FakeApi
try:
    blob = summarize.get_transcript(VID)
    check("transcript joined into one blob",
          blob == "Hello world. This is a fake transcript.")
finally:
    summarize.YouTubeTranscriptApi = orig_api


# ── 3. Prompt/body wiring into sc.analyze_large (stub sc.analyze) ──────────────
captured = {}


def _fake_analyze(system_prompt, prompt, *, processor, model_key, max_tokens=8192):
    # analyze_large for cloud/short input calls analyze(system, f"{header}\n\n{body}")
    captured["system_prompt"] = system_prompt
    captured["prompt"] = prompt
    captured["processor"] = processor
    captured["model_key"] = model_key
    return "TL;DR: stub\nKey Takeaway 1: a\nKey Takeaway 2: b\nKey Takeaway 3: c\nAction for B2B Marketers: do x"


# analyze_large imports `analyze` into its own module namespace; patch there.
import signalyser_core.chunking as chunking
orig_chunk_analyze = chunking.analyze
chunking.analyze = _fake_analyze
try:
    test_url = f"https://www.youtube.com/watch?v={VID}"
    transcript = "Hello world. This is a fake transcript."
    report = sc.analyze_large(
        summarize.SYSTEM_PROMPT,
        header=f"YouTube video: {test_url}",
        body=transcript,
        processor="cloud",
        model_key="opus-4.8",
    )
    check("analyze_large returns the stubbed report", report.startswith("TL;DR:"))
    check("system prompt forwarded verbatim",
          captured.get("system_prompt") == summarize.SYSTEM_PROMPT)
    check("header included in prompt body",
          f"YouTube video: {test_url}" in captured.get("prompt", ""))
    check("transcript included in prompt body",
          transcript in captured.get("prompt", ""))
    check("processor/model forwarded",
          captured.get("processor") == "cloud" and captured.get("model_key") == "opus-4.8")
finally:
    chunking.analyze = orig_chunk_analyze


# ── 4. System prompt asserts the required B2B shape ───────────────────────────
sp = summarize.SYSTEM_PROMPT
check("system prompt mentions TL;DR", "TL;DR:" in sp)
check("system prompt has 3 takeaways",
      all(f"Key Takeaway {i}:" in sp for i in (1, 2, 3)))
check("system prompt has a B2B action line", "Action for B2B Marketers:" in sp)


print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
