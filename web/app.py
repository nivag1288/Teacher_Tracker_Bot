from fastapi import FastAPI
from tracker.backfill import BackfillStatus


def create_app(db_path: str, status: BackfillStatus) -> FastAPI:
    app = FastAPI(title="Teacher Tracker Bot")
    app.state.db_path = db_path
    app.state.backfill_status = status
    return app
