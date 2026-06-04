#!/usr/bin/env python3
"""
Offline test for the Opportunity Finder (011) + the core Reddit signal helper.

Never hits the network or a model: monkeypatches read_company_intel, the Reddit
fetch, and sc.analyze. Asserts the prompt fuses the company corpus with the
subreddit signal, that the system prompt asks for SEO keywords, that output is
saved to outputs/ + inputs/<slug>-opportunities.md, and that a missing corpus
exits 1. Also unit-tests core.reddit.format_signal (no network).

Run: <venv-python> tests/test_opportunities.py   (exit 0 = PASS)
"""

import sys
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))
sys.path.insert(0, str(SUITE_ROOT / "tools" / "opportunities"))

import signalyser_core as sc
from signalyser_core import reddit as reddit_signal
import opportunities


COMPANY = "ZZOppCo"
SUB = "giftideas"
FAKE_INTEL = {
    f"{sc.slugify(COMPANY)}-positioning-arc.md": "Positioning: premium photo keepsakes for gifting.",
    f"{sc.slugify(COMPANY)}-personas.md": "Persona: the occasion-driven gift buyer.",
}
FAKE_SIGNAL = ("# Reddit signal from r/giftideas\n\n"
               "## Post 1 — need a last-minute personalised gift\n"
               "**Body:** can't find a good photo book service that ships fast\n")
CANNED = "# Opportunity Scan\n\n## SEO keywords & search phrases\n- personalised photo book\n"


def _format_signal_unit() -> list[str]:
    fails = []
    posts = [{"title": "flaky gifts", "body": "need ideas", "comments": ["try a photo book", "[deleted]"]}]
    text = reddit_signal.format_signal("giftideas", posts)
    if "r/giftideas" not in text:
        fails.append("format_signal missing subreddit header")
    if "flaky gifts" not in text or "try a photo book" not in text:
        fails.append("format_signal dropped post/comment content")
    if "[deleted]" in text:
        fails.append("format_signal did not drop [deleted] comments")
    return fails


def main() -> None:
    failures = _format_signal_unit()
    captured = {}
    slug = sc.slugify(COMPANY)

    def fake_read_company_intel(name):
        captured["company"] = name
        return dict(FAKE_INTEL)

    def fake_fetch_signal(subreddit, *, username=None, num=12):
        captured["subreddit"] = subreddit
        return FAKE_SIGNAL

    def fake_analyze(system_prompt, user_prompt, *, processor, model_key, **kw):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return CANNED

    opportunities.sc.read_company_intel = fake_read_company_intel
    opportunities.sc.analyze = fake_analyze
    opportunities.reddit_signal.fetch_signal = fake_fetch_signal
    opportunities.sc.load_env = lambda: None
    opportunities.sc.resolve_processing = lambda args: ("local", None)
    opportunities.sc.print_backend = lambda p, m: None

    intel_file = sc.inputs_dir() / f"{slug}-opportunities.md"
    out_before = set(sc.outputs_dir().glob(f"{slug}-opportunities-*.md"))
    new_out = set()
    intel_pre = intel_file.exists()

    sys.argv = ["opportunities.py", "--company", COMPANY, "--subreddit", SUB]
    try:
        opportunities.main()

        if captured.get("company") != COMPANY:
            failures.append("read_company_intel not called with the company")
        if captured.get("subreddit") != SUB:
            failures.append("reddit fetch not called with the subreddit")
        up = captured.get("user", "")
        if "premium photo keepsakes" not in up:
            failures.append("prompt missing the company corpus")
        if "photo book service that ships fast" not in up:
            failures.append("prompt missing the reddit signal")
        if "SEO" not in captured.get("system", ""):
            failures.append("system prompt does not ask for SEO keywords")

        if not intel_file.exists() or intel_file.read_text(encoding="utf-8") != CANNED:
            failures.append("did not write inputs/<slug>-opportunities.md")
        new_out = set(sc.outputs_dir().glob(f"{slug}-opportunities-*.md")) - out_before
        if not new_out:
            failures.append("no report written to outputs/")

        # Missing corpus -> exit 1.
        opportunities.sc.read_company_intel = lambda name: {}
        try:
            opportunities.main()
            failures.append("missing corpus did not exit")
        except SystemExit as e:
            if e.code != 1:
                failures.append(f"missing-corpus exit code {e.code}, expected 1")
    finally:
        for p in new_out:
            p.unlink(missing_ok=True)
        if not intel_pre:
            intel_file.unlink(missing_ok=True)

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS  opportunities: corpus x subreddit -> opportunities + SEO, persisted")


if __name__ == "__main__":
    main()
