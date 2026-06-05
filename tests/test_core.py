"""Tests for signalyser_core (processor selection + helpers). No network/model.

Run:  .venv/bin/python tests/test_core.py   (exit 0 = all pass)
"""
import os
import sys
import argparse
import tempfile
from pathlib import Path

# Make the suite root importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import signalyser_core as sc
import signalyser_core.env as cenv

failures = []

def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)

def ns(**kw):
    base = {"processor": None, "model": None}
    base.update(kw)
    return argparse.Namespace(**base)

def fresh_env(tmp):
    cenv.ENV_FILE = Path(tmp) / ".env"
    if cenv.ENV_FILE.exists():
        cenv.ENV_FILE.unlink()
    for k in ("PROCESSOR", "CLOUD_MODEL", "ANTHROPIC_API_KEY"):
        os.environ.pop(k, None)

with tempfile.TemporaryDirectory() as tmp:
    # 1. Default → local
    fresh_env(tmp)
    check("default resolves to local", sc.resolve_processing(ns()) == ("local", None))

    # 2. Explicit cloud + model → persisted
    fresh_env(tmp)
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    check("explicit cloud+model", sc.resolve_processing(ns(processor="cloud", model="opus-4.8")) == ("cloud", "opus-4.8"))
    saved = cenv.ENV_FILE.read_text()
    check("processor persisted", "PROCESSOR=cloud" in saved)
    check("cloud model persisted", "CLOUD_MODEL=opus-4.8" in saved)

    # 3. Sticky reuse
    os.environ.pop("PROCESSOR", None); os.environ.pop("CLOUD_MODEL", None)
    sc.load_env() if False else None  # explicit: read the temp file we just wrote
    from dotenv import load_dotenv; load_dotenv(cenv.ENV_FILE)
    check("sticky cloud reused", sc.resolve_processing(ns()) == ("cloud", "opus-4.8"))

    # 4. cloud, no model, none saved → exit
    fresh_env(tmp); os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    try:
        sc.resolve_processing(ns(processor="cloud")); check("cloud without model exits", False)
    except SystemExit:
        check("cloud without model exits", True)

    # 5. unknown model → exit
    fresh_env(tmp); os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    try:
        sc.resolve_processing(ns(processor="cloud", model="bogus")); check("unknown model exits", False)
    except SystemExit:
        check("unknown model exits", True)

    # 6. cloud, no key, non-interactive → fall back to local
    fresh_env(tmp)
    check("no-key cloud falls back", sc.resolve_processing(ns(processor="cloud", model="haiku-4.5")) == ("local", None))

    # 7. set_env_var idempotent
    fresh_env(tmp)
    sc.set_env_var("PROCESSOR", "local"); sc.set_env_var("PROCESSOR", "cloud")
    body = cenv.ENV_FILE.read_text()
    check("set_env_var updates in place", body.count("PROCESSOR=") == 1 and "PROCESSOR=cloud" in body)

# 8. Model maps
check("model map keys match labels", set(sc.CLOUD_MODELS) == set(sc.CLOUD_MODEL_LABELS))
check("opus id", sc.CLOUD_MODELS["opus-4.8"] == "claude-opus-4-8")
check("sonnet id", sc.CLOUD_MODELS["sonnet-4.6"] == "claude-sonnet-4-6")
check("haiku id", sc.CLOUD_MODELS["haiku-4.5"] == "claude-haiku-4-5")

# 9. io helpers
check("slugify", sc.slugify("Acme Corp! Inc.") == "acme-corp-inc")
check("intel_path naming", sc.intel_path("Acme Corp", "004").name == "acme-corp-004.md")

# 10. Local model selection — choosing the 9B means NO 35B attempt; the 35B keeps
#     the 9B as automatic fallback. (Why the user wants it: the 35B can OOM-crash.)
import signalyser_core.processing as _proc
_orig_ollama = os.environ.get("OLLAMA_MODEL")
os.environ["OLLAMA_MODEL"] = "qwen3.5:9b"
check("force 9B -> only 9B (no 35B attempt)", _proc._ollama_models() == ["qwen3.5:9b"])
os.environ["OLLAMA_MODEL"] = "qwen3.6:35b-a3b"
check("35B -> 35B then 9B fallback", _proc._ollama_models() == ["qwen3.6:35b-a3b", "qwen3.5:9b"])
if _orig_ollama is None:
    os.environ.pop("OLLAMA_MODEL", None)
else:
    os.environ["OLLAMA_MODEL"] = _orig_ollama
check("both local models valid + labelled", set(sc.LOCAL_MODELS) == {"qwen3.6:35b-a3b", "qwen3.5:9b"})

# 11. Local corpus trimming — stops a big multi-company corpus overflowing the
#     local context (the CTA tracker failed with empty output before this).
_big = {"a": "x" * 20000, "b": "y" * 20000}
check("cloud corpus untrimmed", sc.fit_corpus_for_local(_big, "cloud") == _big)
_trimmed = sc.fit_corpus_for_local(_big, "local", char_budget=6000)
check("local big corpus trimmed down",
      sum(len(v) for v in _trimmed.values()) < sum(len(v) for v in _big.values()))
_small = {"a": "short", "b": "also short"}
check("local small corpus untouched", sc.fit_corpus_for_local(_small, "local", char_budget=6000) == _small)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}"); sys.exit(1)
print("ALL TESTS PASSED")
