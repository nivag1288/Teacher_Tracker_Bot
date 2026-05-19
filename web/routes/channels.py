from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from tracker.queries import StatsQuery, Scope
from visualization import charts

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/channels", response_class=HTMLResponse)
async def channel_list(request: Request):
    q = StatsQuery(request.app.state.db_path)
    channels = await q.channel_list()
    return templates.TemplateResponse(request, "channel_list.html", {"channels": channels})


@router.get("/channels/{channel_id}", response_class=HTMLResponse)
async def channel_detail(request: Request, channel_id: str):
    q = StatsQuery(request.app.state.db_path)
    summary = await q.channel_summary(channel_id)
    if summary is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Channel not found")

    scope = Scope(mode="channel", channel_id=channel_id)
    stats = {
        "total_messages": await q.messages_count(scope),
        "messages_today": await q.messages_today(scope),
        "messages_this_week": await q.messages_this_week(scope),
        "reaction_totals": await q.reaction_totals(scope),
        "top_users": await q.top_users(scope),
        "daily_trend": await q.daily_trend(scope),
        "active_hours": await q.active_hours(scope),
        "most_reacted": await q.most_reacted_messages(scope),
    }
    chart_trend = charts.daily_trend(stats["daily_trend"])
    chart_heatmap = charts.hourly_heatmap(stats["active_hours"])
    chart_users = charts.user_bar(stats["top_users"])

    return templates.TemplateResponse(
        request,
        "channel_detail.html",
        {
            "summary": summary,
            "channel_id": channel_id,
            "stats": stats,
            "chart_trend": chart_trend,
            "chart_heatmap": chart_heatmap,
            "chart_users": chart_users,
        },
    )
