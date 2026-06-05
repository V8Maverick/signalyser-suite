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
from . import sessions as sessions_mod

_HERE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))


def _asset_ver() -> str:
    """Cache-buster for static assets: newest mtime in static/ (changes on edit)."""
    try:
        mtimes = [p.stat().st_mtime for p in (_HERE / "static").glob("*")]
        return str(int(max(mtimes))) if mtimes else "0"
    except OSError:
        return "0"


# Made available to every template; appended to /static links so a browser never
# serves a stale stylesheet/script after the files change.
TEMPLATES.env.globals["asset_ver"] = _asset_ver()


def _tools_by_category() -> dict[str, list]:
    grouped: dict[str, list] = {cat: [] for cat in CATEGORY_LABELS}
    for tool in TOOLS.values():
        grouped.setdefault(tool.category, []).append(tool)
    return grouped


def create_app() -> FastAPI:
    app = FastAPI(title="Signalyser Suite")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    @app.middleware("http")
    async def no_store_html(request: Request, call_next):
        # Never let the browser serve a stale HTML page — state (active session,
        # our-company, corpus) changes between requests. Static assets keep their
        # own caching via the ?v= buster.
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ── Pages ────────────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse(url="/tools")

    @app.get("/tools", response_class=HTMLResponse)
    def tools_page(request: Request):
        ui = settings_mod.ui_version()
        ctx = {
            "active": "tools",
            "ui": ui,
            "session": sessions_mod.current(),
            "grouped": _tools_by_category(),
            "category_labels": CATEGORY_LABELS,
            "settings": settings_mod.get_settings(),
        }
        if ui == "v2":
            ctx["companies"] = corpus_mod.list_inputs()
            ctx["own_company"] = sessions_mod.own_company()
            ctx["tools"] = TOOLS
            return TEMPLATES.TemplateResponse(request, "dashboard.html", ctx)
        return TEMPLATES.TemplateResponse(request, "tools.html", ctx)

    @app.get("/corpus", response_class=HTMLResponse)
    def corpus_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "corpus.html", {
            "active": "corpus",
            "ui": settings_mod.ui_version(),
            "session": sessions_mod.current(),
            "companies": corpus_mod.list_inputs(),
        })

    @app.get("/reports", response_class=HTMLResponse)
    def reports_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "reports.html", {
            "active": "reports",
            "ui": settings_mod.ui_version(),
            "session": sessions_mod.current(),
            "reports": corpus_mod.list_outputs(),
        })

    @app.get("/view", response_class=HTMLResponse)
    def view_page(request: Request, root: str, rel: str):
        view = corpus_mod.read_view(root, rel)
        if view is None:
            return HTMLResponse("<h1>404</h1><p>File not found.</p>", status_code=404)
        return TEMPLATES.TemplateResponse(request, "view.html", {
            "active": "corpus" if root == "inputs" else "reports",
            "ui": settings_mod.ui_version(),
            "session": sessions_mod.current(),
            "view": view,
        })

    @app.get("/sessions", response_class=HTMLResponse)
    def sessions_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "sessions.html", {
            "active": "sessions",
            "ui": settings_mod.ui_version(),
            "session": sessions_mod.current(),
            "sessions": sessions_mod.list_sessions(),
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
            "ui": settings_mod.ui_version(),
            "session": sessions_mod.current(),
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

    @app.post("/sessions/switch")
    async def session_switch(request: Request):
        form = dict(await request.form())
        sessions_mod.switch(str(form.get("name") or ""))
        return RedirectResponse(url="/sessions", status_code=303)

    @app.post("/sessions/new")
    async def session_new(request: Request):
        form = dict(await request.form())
        name = str(form.get("name") or "").strip()
        if name:
            sessions_mod.create(name)
        return RedirectResponse(url="/sessions", status_code=303)

    @app.post("/sessions/delete")
    async def session_delete(request: Request):
        form = dict(await request.form())
        sessions_mod.delete(str(form.get("name") or ""))
        return RedirectResponse(url="/sessions", status_code=303)

    @app.post("/session/own")
    async def session_own(request: Request):
        form = dict(await request.form())
        sessions_mod.set_own(str(form.get("own_company") or ""))
        back = request.headers.get("referer") or "/tools"
        return RedirectResponse(url=back, status_code=303)

    @app.get("/ui/{version}")
    def switch_ui(version: str, request: Request):
        settings_mod.set_ui_version(version)
        back = request.headers.get("referer") or "/tools"
        return RedirectResponse(url=back, status_code=303)

    return app


app = create_app()
