"""Suite-wide .env handling: load, sticky writes, and API-key prompting."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# One .env for the whole suite, at the repo root (parent of this package).
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env() -> None:
    """Load the suite .env into the environment (does not override real env vars)."""
    load_dotenv(ENV_FILE)


def set_env_var(key: str, value: str) -> None:
    """Create or update KEY=value in the suite .env file (sticky settings)."""
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value  # reflect immediately for this run


def prompt_for_api_key() -> str | None:
    """Ask the user to paste an Anthropic API key. Returns None if they decline."""
    if not sys.stdin.isatty():
        return None
    try:
        entered = input(
            "\nNo ANTHROPIC_API_KEY found. Paste your Anthropic API key "
            "(sk-ant-...), or press Enter to use Local processing instead: "
        ).strip()
    except EOFError:
        return None
    return entered or None
