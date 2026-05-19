import time
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from tracker.queries import StatsQuery, Scope

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

_start_time = time.time()


def _uptime_str() -> str:
    delta = int(time.time() - _start_time)
    h, rem = divmod(delta, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


@router.get("/status", response_class=HTMLResponse)
async def status(request: Request):
    db_path = request.app.state.db_path
    provider = request.app.state.llm_provider

    q = StatsQuery(db_path)
    total_messages = await q.messages_count(Scope(mode="server"))
    backfill_timestamps = await q.backfill_timestamps()

    ollama_ok: bool | None = None
    if provider is not None and hasattr(provider, "ping"):
        ollama_ok = await provider.ping()

    return templates.TemplateResponse(
        request,
        "status.html",
        {
            "total_messages": total_messages,
            "backfill_timestamps": backfill_timestamps,
            "ollama_ok": ollama_ok,
            "uptime": _uptime_str(),
        },
    )


@router.get("/api/status")
async def status_json(request: Request):
    db_path = request.app.state.db_path
    provider = request.app.state.llm_provider

    q = StatsQuery(db_path)
    total_messages = await q.messages_count(Scope(mode="server"))
    backfill_timestamps = await q.backfill_timestamps()

    ollama_ok: bool | None = None
    if provider is not None and hasattr(provider, "ping"):
        ollama_ok = await provider.ping()

    return {
        "total_messages": total_messages,
        "backfill_channels": len(backfill_timestamps),
        "ollama_ok": ollama_ok,
        "uptime": _uptime_str(),
    }
