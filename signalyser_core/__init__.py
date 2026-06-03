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
)
from .cli import add_processing_args, print_backend
from .chunking import analyze_large
from .io import (
    slugify,
    save_report,
    save_intel,
    intel_path,
    read_company_intel,
    SOURCE_IDS,
    INPUTS_DIR,
    OUTPUTS_DIR,
    SUITE_ROOT,
)

__all__ = [
    "load_env", "set_env_var", "prompt_for_api_key", "ENV_FILE",
    "analyze", "analyze_with_ollama", "analyze_with_cloud", "resolve_processing",
    "ModelUnavailable", "CLOUD_MODELS", "CLOUD_MODEL_LABELS", "CLOUD_MAX_TOKENS",
    "add_processing_args", "print_backend", "analyze_large",
    "slugify", "save_report", "save_intel", "intel_path", "read_company_intel",
    "SOURCE_IDS", "INPUTS_DIR", "OUTPUTS_DIR", "SUITE_ROOT",
]
