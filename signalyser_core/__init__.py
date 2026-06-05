"""Signalyser Suite shared core: switchable local/cloud analysis + shared I/O.

Every tool imports from here so the backend (local Ollama with primary->fallback,
or cloud Anthropic), the sticky -p/-m selection, the .env handling, and the
shared inputs/outputs corpus are written once.
"""
from .env import load_env, set_env_var, prompt_for_api_key, ENV_FILE
from .processing import (
    analyze,
    analyze_with_ollama,
    analyze_with_cloud,
    resolve_processing,
    ModelUnavailable,
    CLOUD_MODELS,
    CLOUD_MODEL_LABELS,
    CLOUD_MAX_TOKENS,
    LOCAL_MODELS,
    DEFAULT_LOCAL_MODEL,
)
from .cli import add_processing_args, print_backend
from .chunking import analyze_large, fit_corpus_for_local
from .io import (
    slugify,
    save_report,
    save_intel,
    intel_path,
    read_company_intel,
    SOURCE_IDS,
    SUITE_ROOT,
    SESSIONS_ROOT,
    DEFAULT_SESSION,
    active_session,
    set_active_session,
    session_dir,
    inputs_dir,
    outputs_dir,
    list_sessions,
    create_session,
    delete_session,
    read_session_meta,
    write_session_meta,
    get_own_company,
    set_own_company,
)

__all__ = [
    "load_env", "set_env_var", "prompt_for_api_key", "ENV_FILE",
    "analyze", "analyze_with_ollama", "analyze_with_cloud", "resolve_processing",
    "ModelUnavailable", "CLOUD_MODELS", "CLOUD_MODEL_LABELS", "CLOUD_MAX_TOKENS",
    "LOCAL_MODELS", "DEFAULT_LOCAL_MODEL",
    "add_processing_args", "print_backend", "analyze_large", "fit_corpus_for_local",
    "slugify", "save_report", "save_intel", "intel_path", "read_company_intel",
    "SOURCE_IDS", "INPUTS_DIR", "OUTPUTS_DIR", "SUITE_ROOT",
    "SESSIONS_ROOT", "DEFAULT_SESSION", "active_session", "set_active_session",
    "session_dir", "inputs_dir", "outputs_dir", "list_sessions",
    "create_session", "delete_session",
    "read_session_meta", "write_session_meta", "get_own_company", "set_own_company",
]


def __getattr__(name: str):
    """Delegate the session-dependent path constants to io (resolved live)."""
    if name in ("INPUTS_DIR", "OUTPUTS_DIR"):
        from . import io
        return getattr(io, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
