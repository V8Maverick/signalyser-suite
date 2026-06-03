#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# RedAlyser setup.
#
# REQUIRED: your Reddit username. RedAlyser will NOT run until it is set, so this
# script makes you provide one. It then creates a virtualenv, installs deps, and
# records the username in .env.
#
#   Usage:  ./setup.sh <your_reddit_username>
#   (or:    bash setup.sh <your_reddit_username>)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

USERNAME="${1:-}"
USERNAME="${USERNAME#/}"      # tolerate a leading "/u/"
USERNAME="${USERNAME#u/}"     # tolerate a leading "u/"

usage() {
  echo "Usage: ./setup.sh <your_reddit_username>"
  echo "Example: ./setup.sh jane_doe"
}

if [ -z "$USERNAME" ]; then
  echo "ERROR: you must provide your Reddit username." >&2
  usage
  exit 1
fi

# Reject obvious placeholders.
case "$(printf '%s' "$USERNAME" | tr '[:upper:]' '[:lower:]')" in
  your_username|your-reddit-username|reddit_username|username|changeme|unknown)
    echo "ERROR: '$USERNAME' is a placeholder — use your REAL Reddit username." >&2
    usage
    exit 1 ;;
esac

# Basic shape check (Reddit handles are 3-20 of [A-Za-z0-9_-]).
if ! printf '%s' "$USERNAME" | grep -Eq '^[A-Za-z0-9_-]{3,20}$'; then
  echo "ERROR: '$USERNAME' is not a valid Reddit username (3-20 chars: letters, digits, _ or -)." >&2
  exit 1
fi

# Locate Python.
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "ERROR: Python 3.10+ not found. Install it (e.g. 'brew install python')." >&2
  exit 1
fi

echo "==> Creating virtual environment (.venv)"
"$PY" -m venv .venv

echo "==> Installing dependencies"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

echo "==> Recording your Reddit username in .env"
[ -f .env ] || cp .env.example .env
if grep -q '^REDDIT_USERNAME=' .env; then
  sed -i.bak "s/^REDDIT_USERNAME=.*/REDDIT_USERNAME=$USERNAME/" .env && rm -f .env.bak
else
  printf '\nREDDIT_USERNAME=%s\n' "$USERNAME" >> .env
fi

cat <<EOF

Setup complete. Reddit username set to: $USERNAME

Next steps:
  1. Make sure Ollama is running with a model pulled:
       ollama serve            # or just launch the Ollama app
       ollama pull qwen3.5:9b
  2. Run RedAlyser:
       .venv/bin/python reddit_miner.py devops
EOF
