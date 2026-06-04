"""Browse the shared inputs/ intel corpus and outputs/ reports.

Read-only views over the two folders the CLI tools already write to. All file
access goes through `_safe` so a crafted name can never escape the intended
directory (path-traversal guard).
"""
from __future__ import annotations

from pathlib import Path

from signalyser_core.io import INPUTS_DIR, OUTPUTS_DIR

# Folders the web layer is allowed to read, keyed by the name used in URLs.
ROOTS = {"inputs": INPUTS_DIR, "outputs": OUTPUTS_DIR}

_MARKDOWN_EXT = {".md", ".markdown"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg"}


def _safe(root_key: str, relname: str) -> Path | None:
    """Resolve `relname` under ROOTS[root_key], or None if it escapes/doesn't exist."""
    root = ROOTS.get(root_key)
    if root is None:
        return None
    root = root.resolve()
    try:
        target = (root / relname).resolve()
    except (OSError, ValueError):
        return None
    if root != target and root not in target.parents:
        return None  # traversal attempt
    if not target.is_file():
        return None
    return target


def list_inputs() -> list[dict]:
    """All intel files in inputs/, grouped by company slug (the {slug}-*.md corpus)."""
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    by_company: dict[str, list[dict]] = {}
    for p in sorted(INPUTS_DIR.glob("*.md")):
        # Filenames are "{slug}-{suffix}.md"; company slug is everything before the
        # last hyphen group is unreliable, so derive it as the leading token set.
        stem = p.stem
        company = stem.rsplit("-", 1)[0] if "-" in stem else stem
        by_company.setdefault(company, []).append({
            "name": p.name,
            "suffix": stem.rsplit("-", 1)[1] if "-" in stem else "",
            "size": p.stat().st_size,
        })
    return [{"company": c, "files": files} for c, files in sorted(by_company.items())]


def list_outputs() -> list[dict]:
    """All report/asset files under outputs/ (recursive), newest first."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for p in OUTPUTS_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (_MARKDOWN_EXT | _IMAGE_EXT):
            continue
        rel = p.relative_to(OUTPUTS_DIR).as_posix()
        items.append({
            "rel": rel,
            "name": p.name,
            "is_image": p.suffix.lower() in _IMAGE_EXT,
            "size": p.stat().st_size,
            "mtime": p.stat().st_mtime,
        })
    items.sort(key=lambda d: d["mtime"], reverse=True)
    return items


def render_markdown(text: str) -> str:
    """Markdown -> HTML. Falls back to a <pre> block if markdown isn't installed."""
    try:
        import markdown as _md
    except ImportError:
        import html
        return f"<pre>{html.escape(text)}</pre>"
    return _md.markdown(text, extensions=["tables", "fenced_code", "toc"])


def read_view(root_key: str, relname: str) -> dict | None:
    """Return a view dict for a file: rendered markdown HTML, or an image marker.

    Returns None if the file is missing or the name escapes the root.
    """
    path = _safe(root_key, relname)
    if path is None:
        return None
    suffix = path.suffix.lower()
    if suffix in _IMAGE_EXT:
        return {"name": path.name, "kind": "image", "root": root_key, "rel": relname}
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "name": path.name, "kind": "markdown", "root": root_key, "rel": relname,
        "html": render_markdown(text), "raw": text,
    }


def file_path(root_key: str, relname: str) -> Path | None:
    """Safe absolute path for serving a raw file (e.g. images via FileResponse)."""
    return _safe(root_key, relname)
