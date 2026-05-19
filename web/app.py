from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from tracker.backfill import BackfillStatus
from web.routes import dashboard, users, channels, leaderboard, transcripts


def create_app(
    db_path: str,
    status: BackfillStatus,
    transcripts_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Teacher Tracker Bot")
    app.state.db_path = db_path
    app.state.backfill_status = status
    app.state.transcripts_dir = transcripts_dir or Path("transcripts")

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(dashboard.router)
    app.include_router(users.router)
    app.include_router(channels.router)
    app.include_router(leaderboard.router)
    app.include_router(transcripts.router)
    return app
