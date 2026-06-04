"""Make any suite entry point run under the suite's own virtualenv.

Every tool does a bare `import signalyser_core` and depends on third-party
packages (requests, bs4, anthropic, matplotlib, ...). Those only resolve under
the suite's `.venv`. A user may launch a tool with whatever `python` happens to
be on PATH (commonly the system Python, which has none of this) — so this module
transparently re-execs the process under `.venv` and it Just Works.

It is a no-op when already running under the venv, or when no `.venv` exists
(then the normal import path proceeds, and any error surfaces clearly). Kept
dependency-free (stdlib only) so it can run under *any* interpreter.
"""
import os
import sys
import subprocess


def _venv_python(root: str) -> str | None:
    for cand in (os.path.join(root, ".venv", "Scripts", "python.exe"),  # Windows
                 os.path.join(root, ".venv", "bin", "python")):          # POSIX
        if os.path.exists(cand):
            return cand
    return None


def _find_root(entry: str) -> str:
    """Walk up from the script until a suite marker (.venv / pyproject.toml) is found."""
    d = os.path.dirname(os.path.abspath(entry))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, ".venv")) or \
           os.path.exists(os.path.join(d, "pyproject.toml")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.dirname(os.path.abspath(entry))


def ensure_venv(entry: str, root: str | None = None, module: str | None = None) -> None:
    """Re-exec `entry` (or `python -m module`) under the suite venv if needed.

    entry  : the calling script's __file__.
    root   : suite root; defaults to the parent of the script's directory.
    module : if given, re-exec as `python -m module` rather than by file path.
    """
    entry = os.path.abspath(entry)
    if root is None:
        root = _find_root(entry)
    venv_py = _venv_python(root)
    if not venv_py:
        return  # no venv found — proceed; a clear ImportError will follow if deps miss
    if os.path.realpath(venv_py) == os.path.realpath(sys.executable):
        return  # already the venv interpreter
    cmd = [venv_py, "-m", module, *sys.argv[1:]] if module else [venv_py, entry, *sys.argv[1:]]
    sys.exit(subprocess.run(cmd).returncode)
