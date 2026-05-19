from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from analysis.transcript import TranscriptBuilder
from tracker.queries import StatsQuery

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _safe_path(transcripts_dir: Path, filename: str) -> Path | None:
    """Resolve filename inside transcripts_dir; return None on path traversal."""
    resolved = (transcripts_dir / filename).resolve()
    if transcripts_dir.resolve() not in resolved.parents and resolved != transcripts_dir.resolve():
        return None
    if not resolved.is_file():
        return None
    return resolved


@router.get("/transcripts", response_class=HTMLResponse)
async def transcripts_list(request: Request):
    transcripts_dir: Path = request.app.state.transcripts_dir
    db_path: str = request.app.state.db_path
    builder = TranscriptBuilder(db_path, transcripts_dir)
    q = StatsQuery(db_path)
    return templates.TemplateResponse(
        request,
        "transcripts.html",
        {
            "transcripts": builder.list_transcripts(),
            "all_channels": await q.all_channels(),
        },
    )


@router.post("/transcripts/generate")
async def generate_transcript(
    request: Request,
    channel_id: str = Form(...),
    guild_id: str = Form(...),
    date_from: str = Form(...),
    date_to: str = Form(...),
):
    transcripts_dir: Path = request.app.state.transcripts_dir
    db_path: str = request.app.state.db_path
    builder = TranscriptBuilder(db_path, transcripts_dir)
    await builder.build(channel_id, guild_id, date_from, date_to)
    return RedirectResponse(url="/transcripts", status_code=303)


@router.get("/transcripts/{filename}/download")
async def download_transcript(request: Request, filename: str):
    transcripts_dir: Path = request.app.state.transcripts_dir
    path = _safe_path(transcripts_dir, filename)
    if path is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Transcript not found")
    return FileResponse(
        path=str(path),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/transcripts/{filename}/view", response_class=HTMLResponse)
async def view_transcript(request: Request, filename: str):
    transcripts_dir: Path = request.app.state.transcripts_dir
    path = _safe_path(transcripts_dir, filename)
    if path is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Transcript not found")
    content = path.read_text(encoding="utf-8")
    return templates.TemplateResponse(
        request,
        "transcript_view.html",
        {"filename": filename, "content": content},
    )
