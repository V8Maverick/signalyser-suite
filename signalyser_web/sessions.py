"""Session management for the web layer — thin wrappers over signalyser_core.

A session is a named workspace (sessions/<slug>/{inputs,outputs}). The active one
is sticky in .env, shared with the CLI. This module adds the per-session file
counts and the active flag the Sessions UI renders, plus safe create/switch/delete.
"""
from __future__ import annotations

import signalyser_core as sc


def _counts(name: str) -> tuple[int, int]:
    inp = sc.inputs_dir(name, create=False)
    outp = sc.outputs_dir(name, create=False)
    ic = len(list(inp.glob("*.md"))) if inp.exists() else 0
    oc = len([p for p in outp.rglob("*") if p.is_file()]) if outp.exists() else 0
    return ic, oc


def list_sessions() -> list[dict]:
    """Every session with its file counts; the active one flagged and sorted first."""
    active = sc.active_session()
    rows = []
    for name in sc.list_sessions():
        ic, oc = _counts(name)
        rows.append({"name": name, "active": name == active,
                     "inputs": ic, "outputs": oc,
                     "own_company": sc.get_own_company(name)})
    rows.sort(key=lambda r: (not r["active"], r["name"]))
    return rows


def current() -> str:
    return sc.active_session()


def own_company() -> str:
    """The active session's 'our company' designation ('' if unset)."""
    return sc.get_own_company()


def set_own(name: str) -> str:
    """Set the active session's 'our company'."""
    return sc.set_own_company(name)


def switch(name: str) -> str:
    """Make `name` the active session (creating its folders if needed)."""
    slug = sc.create_session(name)   # idempotent — ensures the folders exist
    return sc.set_active_session(slug)


def create(name: str) -> str:
    """Create a new session and switch to it. Returns its slug."""
    slug = sc.create_session(name)
    sc.set_active_session(slug)
    return slug


def delete(name: str) -> str:
    """Delete a session. If it was active, fall back to 'default'. Returns active slug."""
    slug = sc.slugify(name) or sc.DEFAULT_SESSION
    was_active = sc.active_session() == slug
    sc.delete_session(slug)
    if was_active:
        sc.create_session(sc.DEFAULT_SESSION)
        sc.set_active_session(sc.DEFAULT_SESSION)
    return sc.active_session()
