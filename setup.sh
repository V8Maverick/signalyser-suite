#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Signalyser Suite setup — one venv + all dependencies for every tool.
#   Usage:  ./setup.sh   (or: bash setup.sh)
# Then ensure Ollama is running for local mode:  ollama pull qwen3.5:9b
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "ERROR: Python 3.10+ not found. Install it (e.g. 'brew install python')." >&2
  exit 1
fi

echo "==> Creating virtual environment (.venv)"
"$PY" -m venv .venv

echo "==> Upgrading pip"
.venv/bin/python -m pip install --quiet --upgrade pip

echo "==> Installing core dependencies"
.venv/bin/python -m pip install --quiet -r requirements.txt

# Install any per-tool requirements too.
for req in tools/*/requirements.txt; do
  [ -f "$req" ] || continue
  # skip files that are just a comment placeholder
  if grep -qvE '^\s*(#.*)?$' "$req"; then
    echo "==> Installing deps for ${req%/requirements.txt}"
    .venv/bin/python -m pip install --quiet -r "$req"
  fi
done

cat <<'EOF'

Setup complete.

Next:
  1. Local mode: start Ollama and pull a model
       ollama serve            # or launch the Ollama app
       ollama pull qwen3.5:9b
  2. Run a tool, e.g.:
       .venv/bin/python tools/job_postings/analyse.py notion
  3. Cloud mode (optional): add -p cloud -m sonnet-4.6 (needs ANTHROPIC_API_KEY)

The reddit tool (tools/reddit/) is self-contained — see its own README.
EOF
