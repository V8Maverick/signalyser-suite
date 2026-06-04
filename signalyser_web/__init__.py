"""Signalyser Suite web front end.

A FastAPI/uvicorn layer over the existing CLI tools: it launches each tool as a
subprocess (reusing the proven scripts), streams the tool's live output to the
browser over Server-Sent Events, and browses the shared inputs/ corpus and
outputs/ reports. The shared core is untouched.

Run it with:  python -m signalyser_web      (then open http://localhost:8000)
"""

__all__ = ["create_app"]


def create_app():
    """Lazy factory so `import signalyser_web` doesn't require FastAPI installed."""
    from .app import create_app as _create_app
    return _create_app()
