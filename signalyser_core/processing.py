"""Switchable local (Ollama/Qwen) <-> cloud (Anthropic/Claude) analysis engine.

Lifted and generalized from the RedAlyser reddit tool so every Signalyser tool
shares one backend: sticky processor selection, local primary->fallback, cloud
streaming, and the paste-key-or-fall-back flow.
"""
import os
import sys
import json
import argparse

import requests

from .env import set_env_var, prompt_for_api_key

# ── Cloud models ──────────────────────────────────────────────────────────────
# Keyed by the friendly name passed to -m, mapped to the canonical API model ID.
CLOUD_MODELS = {
    "opus-4.8": "claude-opus-4-8",
    "sonnet-4.6": "claude-sonnet-4-6",
    "haiku-4.5": "claude-haiku-4-5",
}
CLOUD_MODEL_LABELS = {
    "opus-4.8": "Opus-4.8",
    "sonnet-4.6": "Sonnet-4.6",
    "haiku-4.5": "Haiku-4.5",
}
CLOUD_MAX_TOKENS = 8192

# ── Local (Ollama) models ─────────────────────────────────────────────────────
# Selectable via OLLAMA_MODEL. The 35B is faster but needs more *usable* RAM —
# some machines report enough free RAM yet OOM-crash when it actually loads, so
# the 9B is the safe deliberate choice there. Picking the 9B means no 35B attempt
# at all (it's also the automatic fallback when the 35B can't start).
LOCAL_MODELS = {
    "qwen3.6:35b-a3b": "Qwen3.6 35B — faster, needs plenty of free RAM",
    "qwen3.5:9b": "Qwen3.5 9B — lighter, safe on modest machines",
}
DEFAULT_LOCAL_MODEL = "qwen3.6:35b-a3b"


def _ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _ollama_models() -> list[str]:
    """Ordered, de-duplicated [primary, fallback] local model list (read at call time)."""
    primary = os.getenv("OLLAMA_MODEL", "qwen3.6:35b-a3b")
    fallback = os.getenv("OLLAMA_FALLBACK_MODEL", "qwen3.5:9b")
    models = [primary]
    if fallback and fallback not in models:
        models.append(fallback)
    return models


class ModelUnavailable(Exception):
    """Raised when a local model can't run (not enough memory, not pulled)."""


# ── Local (Ollama) ────────────────────────────────────────────────────────────

def _stream_chat(model: str, messages: list[dict]) -> str:
    """Stream one Ollama chat completion, printing tokens live. Returns full text.

    Raises ModelUnavailable on a clean startup failure (before any output) — the
    signal to try a fallback model. Other failures propagate.
    """
    url = f"{_ollama_host()}/api/chat"
    payload = {
        "model": model,
        "stream": True,
        "messages": messages,
        "options": {"temperature": 0.4, "num_ctx": 8192},
    }
    chunks: list[str] = []
    with requests.post(url, json=payload, stream=True, timeout=600) as resp:
        if resp.status_code != 200:
            try:
                reason = resp.json().get("error", resp.text[:200])
            except ValueError:
                reason = resp.text[:200]
            raise ModelUnavailable(reason)
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            event = json.loads(line)
            if "error" in event:
                if not chunks:
                    raise ModelUnavailable(event["error"])
                raise RuntimeError(f"{model} failed mid-stream: {event['error']}")
            text = event.get("message", {}).get("content", "")
            if text:
                print(text, end="", flush=True)
                chunks.append(text)
            if event.get("done"):
                break
    return "".join(chunks)


def analyze_with_ollama(system_prompt: str, user_prompt: str) -> str:
    """Stream analysis from a local model, trying primary then fallback."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    candidates = _ollama_models()
    last_error: Exception | None = None
    for i, model in enumerate(candidates):
        print(f"Analyzing with Ollama model '{model}'...\n")
        print("=" * 70)
        try:
            return _stream_chat(model, messages)
        except requests.ConnectionError:
            print(
                f"\nError: could not reach Ollama at {_ollama_host()}. "
                "Is the Ollama server running? (`ollama serve`)"
            )
            sys.exit(1)
        except ModelUnavailable as e:
            last_error = e
            remaining = candidates[i + 1:]
            if remaining:
                print(f"\n[!] '{model}' can't run: {e}\n    Falling back to '{remaining[0]}'...\n")
            else:
                print(f"\n[!] '{model}' can't run: {e}")
    print(f"\nError: no usable Ollama model. Last error: {last_error}")
    sys.exit(1)


# ── Cloud (Anthropic) ─────────────────────────────────────────────────────────

def analyze_with_cloud(system_prompt: str, user_prompt: str, model_key: str,
                       max_tokens: int = CLOUD_MAX_TOKENS) -> str:
    """Stream analysis from the Anthropic API (cloud processing)."""
    try:
        import anthropic
    except ImportError:
        print(
            "\nError: the 'anthropic' package is required for cloud processing.\n"
            "Install it:  .venv/bin/python -m pip install -r requirements.txt"
        )
        sys.exit(1)

    model_id = CLOUD_MODELS[model_key]
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    print(f"Analyzing with Anthropic model '{model_id}'...\n")
    print("=" * 70)

    chunks: list[str] = []
    try:
        with client.messages.stream(
            model=model_id,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                chunks.append(text)
    except anthropic.AuthenticationError:
        print(
            "\nError: Anthropic rejected the API key (authentication failed).\n"
            "Check ANTHROPIC_API_KEY in .env, or switch back to local with -p local."
        )
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"\nAnthropic API error: {e}")
        sys.exit(1)
    return "".join(chunks)


# ── Unified entry point ───────────────────────────────────────────────────────

def analyze(system_prompt: str, user_prompt: str, *, processor: str,
            model_key: str | None, max_tokens: int = CLOUD_MAX_TOKENS) -> str:
    """Run analysis on the selected backend and return the full text."""
    if processor == "cloud":
        return analyze_with_cloud(system_prompt, user_prompt, model_key, max_tokens)
    return analyze_with_ollama(system_prompt, user_prompt)


# ── Processor selection (sticky via .env) ─────────────────────────────────────

def resolve_processing(args: argparse.Namespace) -> tuple[str, str | None]:
    """Decide local vs cloud (and which cloud model), honoring sticky .env state.

    `-p` persists the processor; `-m` persists the cloud model. With neither flag,
    the saved preference is reused. Returns (processor, model_key); model_key is
    None for local. Handles the no-model and no-API-key cases.
    """
    if getattr(args, "processor", None):
        processor = args.processor
        set_env_var("PROCESSOR", processor)
    else:
        processor = (os.getenv("PROCESSOR") or "local").strip().lower()
        if processor not in ("local", "cloud"):
            processor = "local"

    if processor == "local":
        return "local", None

    if getattr(args, "model", None):
        if args.model not in CLOUD_MODELS:
            print(f"Unknown model '{args.model}'. Choose: Opus-4.8 | Sonnet-4.6 | Haiku-4.5")
            sys.exit(1)
        model_key = args.model
        set_env_var("CLOUD_MODEL", model_key)
    else:
        model_key = (os.getenv("CLOUD_MODEL") or "").strip().lower()
        if model_key not in CLOUD_MODELS:
            print("Which model? Opus-4.8 | Sonnet-4.6 | Haiku-4.5?")
            sys.exit(1)

    if not os.getenv("ANTHROPIC_API_KEY"):
        key = prompt_for_api_key()
        if key:
            set_env_var("ANTHROPIC_API_KEY", key)
        else:
            print("No API key provided — falling back to Local processing.\n")
            return "local", None

    return "cloud", model_key
