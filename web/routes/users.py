from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from tracker.queries import StatsQuery, Scope
from visualization import charts

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/users", response_class=HTMLResponse)
async def user_list(request: Request):
    q = StatsQuery(request.app.state.db_path)
    users = await q.user_list()
    return templates.TemplateResponse(request, "user_list.html", {"users": users})


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: str):
    q = StatsQuery(request.app.state.db_path)
    summary = await q.user_summary(user_id)
    if summary is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")

    scope = Scope(mode="user", user_id=user_id)
    stats = {
        "total_messages": await q.messages_count(scope),
        "messages_today": await q.messages_today(scope),
        "messages_this_week": await q.messages_this_week(scope),
        "reaction_totals": await q.reaction_totals(scope),
        "top_channels": await q.top_channels(scope),
        "daily_trend": await q.daily_trend(scope),
        "active_hours": await q.active_hours(scope),
        "most_reacted": await q.most_reacted_messages(scope),
    }
    chart_trend = charts.daily_trend(stats["daily_trend"])
    chart_heatmap = charts.hourly_heatmap(stats["active_hours"])

    return templates.TemplateResponse(
        request,
        "user_detail.html",
        {
            "summary": summary,
            "user_id": user_id,
            "stats": stats,
            "chart_trend": chart_trend,
            "chart_heatmap": chart_heatmap,
        },
    )
