from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from tracker.queries import StatsQuery, Scope

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _scope(request: Request) -> Scope:
    mode = request.query_params.get("scope", "server")
    if mode not in ("server", "channel", "user"):
        mode = "server"
    return Scope(
        mode=mode,
        channel_id=request.query_params.get("channel_id"),
        user_id=request.query_params.get("user_id"),
    )


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db_path = request.app.state.db_path
    status = request.app.state.backfill_status
    scope = _scope(request)
    q = StatsQuery(db_path)

    stats = {
        "total_messages": await q.messages_count(scope),
        "unique_users": await q.unique_users(scope),
        "channels_tracked": await q.channels_tracked(scope),
        "messages_today": await q.messages_today(scope),
        "messages_this_week": await q.messages_this_week(scope),
        "top_users": await q.top_users(scope),
        "top_channels": await q.top_channels(scope),
        "recent_members": await q.recent_member_events(),
        "backfill_timestamps": await q.backfill_timestamps(),
        "reaction_totals": await q.reaction_totals(scope),
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "scope": scope,
            "all_channels": await q.all_channels(),
            "all_users": await q.all_users(),
            "backfill_running": status.running,
            "backfill_status": status,
            "is_empty": stats["total_messages"] == 0,
        },
    )


@router.get("/api/backfill-status")
async def backfill_status_endpoint(request: Request):
    s = request.app.state.backfill_status
    return {
        "running": s.running,
        "channels_done": s.channels_done,
        "channels_total": s.channels_total,
        "messages_ingested": s.messages_ingested,
    }
