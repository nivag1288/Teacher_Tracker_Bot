from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from tracker.queries import StatsQuery

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

_VALID_TYPES = {"messages", "reactions", "replies_sent", "replies_received"}


@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request):
    lb_type = request.query_params.get("type", "messages")
    if lb_type not in _VALID_TYPES:
        lb_type = "messages"

    try:
        limit = min(int(request.query_params.get("limit", 25)), 100)
    except ValueError:
        limit = 25

    q = StatsQuery(request.app.state.db_path)
    rows = await q.leaderboard(type=lb_type, limit=limit)

    return templates.TemplateResponse(
        request,
        "leaderboard.html",
        {"rows": rows, "lb_type": lb_type, "limit": limit},
    )
