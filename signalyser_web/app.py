"""FastAPI application for the Signalyser suite.

Thin HTTP layer: render pages from the tool registry / corpus, launch runs as
subprocesses (runner.py), and stream their output over SSE. No business logic
lives here — it delegates to config / runner / corpus / settings.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse, FileResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import TOOLS, CATEGORY_LABELS, build_argv
from .runner import manager
from . import corpus as corpus_mod
from . import settings as settings_mod

_HERE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))


def _tools_by_category() -> dict[str, list]:
    grouped: dict[str, list] = {cat: [] for cat in CATEGORY_LABELS}
    for tool in TOOLS.values():
        grouped.setdefault(tool.category, []).append(tool)
    return grouped


def create_app() -> FastAPI:
    app = FastAPI(title="Signalyser Suite")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    # ── Pages ────────────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse(url="/tools")

    @app.get("/tools", response_class=HTMLResponse)
    def tools_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "tools.html", {
            "active": "tools",
            "grouped": _tools_by_category(),
            "category_labels": CATEGORY_LABELS,
            "settings": settings_mod.get_settings(),
        })

    @app.get("/corpus", response_class=HTMLResponse)
    def corpus_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "corpus.html", {
            "active": "corpus",
            "companies": corpus_mod.list_inputs(),
        })

    @app.get("/reports", response_class=HTMLResponse)
    def reports_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "reports.html", {
            "active": "reports",
            "reports": corpus_mod.list_outputs(),
        })

    @app.get("/view", response_class=HTMLResponse)
    def view_page(request: Request, root: str, rel: str):
        view = corpus_mod.read_view(root, rel)
        if view is None:
            return HTMLResponse("<h1>404</h1><p>File not found.</p>", status_code=404)
        return TEMPLATES.TemplateResponse(request, "view.html", {
            "active": "corpus" if root == "inputs" else "reports",
            "view": view,
        })

    @app.get("/raw")
    def raw_file(root: str, rel: str):
        path = corpus_mod.file_path(root, rel)
        if path is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(str(path))

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, saved: int = 0):
        return TEMPLATES.TemplateResponse(request, "settings.html", {
            "active": "settings",
            "settings": settings_mod.get_settings(),
            "saved": bool(saved),
        })

    # ── Actions ──────────────────────────────────────────────────────────────
    @app.post("/run")
    async def run(request: Request):
        form = dict(await request.form())
        tool_key = str(form.get("tool", ""))
        tool = TOOLS.get(tool_key)
        if tool is None:
            return JSONResponse({"ok": False, "error": f"Unknown tool: {tool_key}"},
                                status_code=400)

        s = settings_mod.get_settings()
        processor, model = s["processor"], s["model"]

        gate = settings_mod.validate_run(tool, processor, model, form)
        if gate:
            return JSONResponse({"ok": False, "error": gate}, status_code=400)

        tool_args, errors = build_argv(tool, form, processor, model)
        if errors:
            return JSONResponse({"ok": False, "error": " ".join(errors)},
                                status_code=400)

        job = manager.start(tool, tool_args)
        return JSONResponse({"ok": True, "job_id": job.id,
                             "processor": processor, "model": model})

    @app.get("/stream/{job_id}")
    def stream(job_id: str):
        return StreamingResponse(
            manager.sse(job_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/cancel/{job_id}")
    def cancel(job_id: str):
        return JSONResponse({"ok": manager.cancel(job_id)})

    @app.post("/settings")
    async def save_settings(request: Request):
        form = dict(await request.form())
        settings_mod.update_settings(
            processor=str(form.get("processor") or "") or None,
            model=str(form.get("model") or "") or None,
            api_key=str(form.get("api_key") or "") or None,
            reddit_username=(str(form["reddit_username"])
                             if "reddit_username" in form else None),
        )
        return RedirectResponse(url="/settings?saved=1", status_code=303)

    return app


app = create_app()
