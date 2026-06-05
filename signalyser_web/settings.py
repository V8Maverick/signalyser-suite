"""Read/write the suite's sticky settings (the one .env), reusing the core.

The web Settings panel is the GUI equivalent of the -p/-m flags + the API-key
prompt. Everything is persisted to the same .env the CLI tools read, so the two
front ends stay in sync.
"""
from __future__ import annotations

import os

from signalyser_core.env import load_env, set_env_var
from signalyser_core.processing import CLOUD_MODELS, CLOUD_MODEL_LABELS

# Re-exported so templates can render the model dropdown from one source.
MODEL_CHOICES: list[tuple[str, str]] = list(CLOUD_MODEL_LABELS.items())

UI_VERSIONS = ("v1", "v2")


def ui_version() -> str:
    """Which front-end design is active (sticky in .env). Defaults to v2."""
    v = (os.getenv("UI_VERSION") or "v2").strip().lower()
    return v if v in UI_VERSIONS else "v2"


def set_ui_version(v: str) -> str:
    v = (v or "").strip().lower()
    if v not in UI_VERSIONS:
        v = "v2"
    set_env_var("UI_VERSION", v)
    return v


def get_settings() -> dict:
    """Current sticky settings. The API key is never returned — only whether set."""
    load_env()
    processor = (os.getenv("PROCESSOR") or "local").strip().lower()
    if processor not in ("local", "cloud"):
        processor = "local"
    model = (os.getenv("CLOUD_MODEL") or "").strip().lower()
    return {
        "processor": processor,
        "model": model if model in CLOUD_MODELS else "",
        "has_api_key": bool(os.getenv("ANTHROPIC_API_KEY")),
        "reddit_username": os.getenv("REDDIT_USERNAME") or "",
        "own_company": os.getenv("OWN_COMPANY") or "",
        "ollama_host": os.getenv("OLLAMA_HOST") or "http://localhost:11434",
        "model_choices": MODEL_CHOICES,
    }


def update_settings(*, processor: str | None = None, model: str | None = None,
                    api_key: str | None = None,
                    reddit_username: str | None = None,
                    own_company: str | None = None) -> list[str]:
    """Persist any provided settings to .env. Returns a list of validation errors.

    Blank strings are ignored (treated as "leave unchanged") except reddit_username,
    where a blank explicitly clears it. The API key is only written when non-blank,
    so submitting the form without re-typing it preserves the existing key.
    """
    errors: list[str] = []

    if processor:
        if processor not in ("local", "cloud"):
            errors.append(f"Unknown processor: {processor!r}")
        else:
            set_env_var("PROCESSOR", processor)

    if model:
        if model not in CLOUD_MODELS:
            errors.append(f"Unknown cloud model: {model!r}")
        else:
            set_env_var("CLOUD_MODEL", model)

    if api_key:
        set_env_var("ANTHROPIC_API_KEY", api_key.strip())

    if reddit_username is not None:
        set_env_var("REDDIT_USERNAME", reddit_username.strip())

    if own_company is not None:
        set_env_var("OWN_COMPANY", own_company.strip())

    return errors


def validate_run(tool, processor: str, model: str | None, form: dict) -> str | None:
    """Pre-flight a run so a subprocess never blocks on an interactive prompt.

    Returns an error string (shown in the UI) or None if the run may proceed.
    """
    if processor == "cloud":
        if not model or model not in CLOUD_MODELS:
            return ("Cloud processing needs a model — pick Opus-4.8 / Sonnet-4.6 / "
                    "Haiku-4.5 in Settings.")
        if not os.getenv("ANTHROPIC_API_KEY"):
            return ("Cloud processing needs an ANTHROPIC_API_KEY — add one in "
                    "Settings, or switch to Local.")
    if getattr(tool, "needs_reddit_username", False):
        per_run_user = (form.get("user") or "").strip()
        if not per_run_user and not os.getenv("REDDIT_USERNAME"):
            return ("This tool needs a Reddit username — set one in Settings, or "
                    "fill the per-run username field.")
    return None
