"""Shared I/O: slugs, report saving, and the per-session inputs/ intel corpus.

Work is organised into **sessions** — named workspaces under `sessions/<name>/`,
each with its own `inputs/` (intel corpus) and `outputs/` (reports/charts). The
active session is sticky in `.env` (`SESSION=`, default `default`), so collectors
write into it and synthesis tools read from it, and switching sessions gives a
clean slate without deleting anything.

`INPUTS_DIR` / `OUTPUTS_DIR` resolve **live** to the active session on each access
(via module __getattr__) — important because tools call `load_env()` (which loads
the sticky SESSION) only inside main(), after importing this module.
"""
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

from .env import set_env_var

SUITE_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_ROOT = SUITE_ROOT / "sessions"
DEFAULT_SESSION = "default"

# Map a source-tool id to its intel-file suffix (the suite's shared naming).
SOURCE_IDS = {
    "youtube": "001",
    "g2": "002",
    "reddit": "003",
    "page": "004",
    "jobs": "005",
    "tenk": "006",
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Sessions ──────────────────────────────────────────────────────────────────

def _session_slug(name: str | None) -> str:
    return (slugify(name) if name else "") or DEFAULT_SESSION


def active_session() -> str:
    """Current session slug (sticky in .env as SESSION; defaults to 'default')."""
    return _session_slug(os.getenv("SESSION"))


def set_active_session(name: str) -> str:
    """Persist the active session to .env (sticky) and return its slug."""
    slug = _session_slug(name)
    set_env_var("SESSION", slug)
    return slug


def session_dir(session: str | None = None) -> Path:
    return SESSIONS_ROOT / _session_slug(session or active_session())


def inputs_dir(session: str | None = None, create: bool = True) -> Path:
    """The active (or given) session's intel corpus folder."""
    d = session_dir(session) / "inputs"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def outputs_dir(session: str | None = None, create: bool = True) -> Path:
    """The active (or given) session's reports/charts folder."""
    d = session_dir(session) / "outputs"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def list_sessions() -> list[str]:
    """All session slugs (dirs under sessions/), sorted; 'default' always present."""
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in SESSIONS_ROOT.iterdir() if p.is_dir())
    if DEFAULT_SESSION not in names:
        names.insert(0, DEFAULT_SESSION)
    return names


def create_session(name: str) -> str:
    """Create a session's folders and return its slug (idempotent)."""
    slug = _session_slug(name)
    inputs_dir(slug)
    outputs_dir(slug)
    return slug


def delete_session(name: str) -> None:
    """Remove a session and everything in it. No-op if it doesn't exist."""
    target = SESSIONS_ROOT / _session_slug(name)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


# ── Reports & intel corpus (always the active session) ────────────────────────

def save_report(name: str, text: str, outdir: Path | str | None = None) -> Path:
    """Save a timestamped markdown report; returns the path."""
    outdir = Path(outdir) if outdir is not None else outputs_dir()
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = outdir / f"{slugify(name)}_{stamp}.md"
    path.write_text(text, encoding="utf-8")
    return path


def intel_path(company: str, source_id: str) -> Path:
    """Path for a company's intelligence file from a given source (e.g. '004')."""
    return inputs_dir() / f"{slugify(company)}-{source_id}.md"


def save_intel(company: str, source_id: str, text: str) -> Path:
    """Write a collector's output into the active session's inputs/ corpus."""
    path = intel_path(company, source_id)
    path.write_text(text, encoding="utf-8")
    return path


def read_company_intel(company: str) -> dict[str, str]:
    """Return {filename: contents} for all inputs/{company}-*.md in this session."""
    d = inputs_dir()
    slug = slugify(company)
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(d.glob(f"{slug}-*.md"))
    }


def __getattr__(name: str):
    """Resolve INPUTS_DIR / OUTPUTS_DIR live, so they track the active session."""
    if name == "INPUTS_DIR":
        return inputs_dir()
    if name == "OUTPUTS_DIR":
        return outputs_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
