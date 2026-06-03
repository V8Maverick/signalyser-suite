"""Tests for RedAlyser processor selection + helpers. No network/model needed.

Run:  .venv/bin/python _tests.py   (exit 0 = all pass)
"""
import os
import sys
import argparse
import tempfile
from pathlib import Path

import reddit_miner as rm

failures = []

def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)

def ns(**kw):
    base = {"processor": None, "model": None, "num": 15, "subreddit": "devops"}
    base.update(kw)
    return argparse.Namespace(**base)

def fresh_env(tmp):
    """Point ENV_FILE at a clean temp file and clear sticky env vars."""
    rm.ENV_FILE = Path(tmp) / ".env"
    if rm.ENV_FILE.exists():
        rm.ENV_FILE.unlink()
    for k in ("PROCESSOR", "CLOUD_MODEL", "ANTHROPIC_API_KEY"):
        os.environ.pop(k, None)

with tempfile.TemporaryDirectory() as tmp:
    # 1. Default with no flags / no .env → local
    fresh_env(tmp)
    check("default resolves to local", rm.resolve_processing(ns()) == ("local", None))

    # 2. -p cloud -m opus-4.8 with API key → cloud + persisted to .env
    fresh_env(tmp)
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    res = rm.resolve_processing(ns(processor="cloud", model="opus-4.8"))
    check("explicit cloud+model resolves", res == ("cloud", "opus-4.8"))
    saved = rm.ENV_FILE.read_text()
    check("processor persisted to .env", "PROCESSOR=cloud" in saved)
    check("cloud model persisted to .env", "CLOUD_MODEL=opus-4.8" in saved)

    # 3. Sticky: no flags, but saved .env says cloud/opus → reused
    os.environ.pop("PROCESSOR", None); os.environ.pop("CLOUD_MODEL", None)
    rm.load_dotenv(rm.ENV_FILE)
    check("sticky cloud reused from .env", rm.resolve_processing(ns()) == ("cloud", "opus-4.8"))

    # 4. -p cloud, no -m, no saved model → exits "Which model?"
    fresh_env(tmp)
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    try:
        rm.resolve_processing(ns(processor="cloud"))
        check("cloud without model exits", False)
    except SystemExit:
        check("cloud without model exits", True)

    # 5. -p cloud -m bogus → exits "unknown model"
    fresh_env(tmp)
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    try:
        rm.resolve_processing(ns(processor="cloud", model="bogus"))
        check("unknown model exits", False)
    except SystemExit:
        check("unknown model exits", True)

    # 6. -p cloud -m haiku-4.5, no API key, non-interactive → falls back to local
    fresh_env(tmp)  # no ANTHROPIC_API_KEY; stdin is not a tty in this runner
    check("no-key cloud falls back to local",
          rm.resolve_processing(ns(processor="cloud", model="haiku-4.5")) == ("local", None))

    # 7. set_env_var updates existing key in place (no duplicate)
    fresh_env(tmp)
    rm.set_env_var("PROCESSOR", "local")
    rm.set_env_var("PROCESSOR", "cloud")
    body = rm.ENV_FILE.read_text()
    check("set_env_var updates in place", body.count("PROCESSOR=") == 1 and "PROCESSOR=cloud" in body)

# 8. Model maps line up
check("model map keys match labels", set(rm.CLOUD_MODELS) == set(rm.CLOUD_MODEL_LABELS))
check("opus maps to claude-opus-4-8", rm.CLOUD_MODELS["opus-4.8"] == "claude-opus-4-8")
check("sonnet maps to claude-sonnet-4-6", rm.CLOUD_MODELS["sonnet-4.6"] == "claude-sonnet-4-6")
check("haiku maps to claude-haiku-4-5", rm.CLOUD_MODELS["haiku-4.5"] == "claude-haiku-4-5")

# 9. Username gate still enforced
os.environ.pop("REDDIT_USERNAME", None)
try:
    rm.require_username(); check("username gate blocks when unset", False)
except SystemExit:
    check("username gate blocks when unset", True)
os.environ["REDDIT_USERNAME"] = "u/Jane_Doe"
check("username gate strips u/ prefix", rm.require_username() == "Jane_Doe")

# 10. -u override semantics: setting REDDIT_USERNAME (as -u does) wins
os.environ["REDDIT_USERNAME"] = "from_env"
os.environ["REDDIT_USERNAME"] = "from_flag"   # mimics: if args.user: os.environ[...] = args.user
check("-u override takes effect", rm.require_username() == "from_flag")

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
