import json
import aiosqlite
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from analysis.transcript import TranscriptBuilder
from analysis.semantic import SemanticAnalyzer
from tracker.queries import StatsQuery

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


async def _list_results(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT id, channel_id, guild_id, date_from, date_to, topics, sentiment, summary, created_at "
            "FROM analysis_results ORDER BY created_at DESC"
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "channel_id": r[1],
            "guild_id": r[2],
            "date_from": r[3],
            "date_to": r[4],
            "topics": json.loads(r[5]) if r[5] else [],
            "sentiment": r[6],
            "summary": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


async def _find_cached(db_path: str, channel_id: str, guild_id: str, date_from: str, date_to: str):
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT id FROM analysis_results "
            "WHERE channel_id=? AND guild_id=? AND date_from=? AND date_to=? "
            "ORDER BY created_at DESC LIMIT 1",
            [channel_id, guild_id, date_from, date_to],
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def _save_result(db_path: str, channel_id: str, guild_id: str,
                       date_from: str, date_to: str, result: dict) -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT INTO analysis_results (channel_id, guild_id, date_from, date_to, "
            "topics, sentiment, summary, created_at) VALUES (?,?,?,?,?,?,?,?)",
            [
                channel_id, guild_id, date_from, date_to,
                json.dumps(result["topics"]),
                result["sentiment"],
                result["summary"],
                datetime.now(timezone.utc).isoformat(),
            ],
        )
        await db.commit()
        return cur.lastrowid


@router.get("/analysis", response_class=HTMLResponse)
async def analysis_list(request: Request):
    db_path = request.app.state.db_path
    q = StatsQuery(db_path)
    return templates.TemplateResponse(
        request,
        "analysis.html",
        {
            "results": await _list_results(db_path),
            "all_channels": await q.all_channels(),
        },
    )


@router.post("/analysis/run")
async def run_analysis(
    request: Request,
    channel_id: str = Form(...),
    guild_id: str = Form(...),
    date_from: str = Form(...),
    date_to: str = Form(...),
):
    db_path = request.app.state.db_path
    transcripts_dir: Path = request.app.state.transcripts_dir
    provider = request.app.state.llm_provider

    # Return cached result if one exists for same params
    cached_id = await _find_cached(db_path, channel_id, guild_id, date_from, date_to)
    if cached_id is not None:
        return RedirectResponse(url=f"/analysis/{cached_id}", status_code=303)

    # Build transcript
    builder = TranscriptBuilder(db_path, transcripts_dir)
    path = await builder.build(channel_id, guild_id, date_from, date_to)
    transcript_text = path.read_text(encoding="utf-8")

    # Run analysis
    analyzer = SemanticAnalyzer(provider)
    result = await analyzer.analyze(transcript_text)

    # Persist and redirect
    result_id = await _save_result(db_path, channel_id, guild_id, date_from, date_to, result)
    return RedirectResponse(url=f"/analysis/{result_id}", status_code=303)


@router.get("/analysis/{result_id}", response_class=HTMLResponse)
async def analysis_detail(request: Request, result_id: int):
    db_path = request.app.state.db_path
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT id, channel_id, guild_id, date_from, date_to, topics, sentiment, summary, created_at "
            "FROM analysis_results WHERE id = ?",
            [result_id],
        )
        row = await cur.fetchone()

    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Analysis result not found")

    result = {
        "id": row[0],
        "channel_id": row[1],
        "guild_id": row[2],
        "date_from": row[3],
        "date_to": row[4],
        "topics": json.loads(row[5]) if row[5] else [],
        "sentiment": row[6],
        "summary": row[7],
        "created_at": row[8],
    }
    return templates.TemplateResponse(request, "analysis_detail.html", {"result": result})
