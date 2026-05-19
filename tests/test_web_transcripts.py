import pytest
import aiosqlite
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from tracker.db import ALL_TABLES
from tracker.backfill import BackfillStatus
from web.app import create_app


@pytest.fixture
async def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    transcripts_dir = tmp_path / "transcripts"
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m1','u1','Alice','c1','general','g1','2024-03-10T14:32:00','Hello world',2,11)"
        )
        await db.commit()
    return create_app(
        db_path=db_path,
        status=BackfillStatus(),
        transcripts_dir=transcripts_dir,
    ), transcripts_dir, db_path


# ── GET /transcripts ──────────────────────────────────────────────────────────

async def test_transcripts_list_returns_200(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/transcripts")
    assert r.status_code == 200


async def test_transcripts_list_html(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/transcripts")
    assert "text/html" in r.headers["content-type"]
    assert "Transcripts" in r.text


async def test_transcripts_list_shows_generate_form(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/transcripts")
    assert "Generate" in r.text
    assert "channel_id" in r.text


async def test_transcripts_list_empty_message(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/transcripts")
    assert "No transcripts yet" in r.text


# ── POST /transcripts/generate ────────────────────────────────────────────────

async def test_generate_creates_file(app):
    a, transcripts_dir, _ = app
    async with AsyncClient(
        transport=ASGITransport(app=a), base_url="http://test", follow_redirects=True
    ) as c:
        r = await c.post("/transcripts/generate", data={
            "channel_id": "c1",
            "guild_id": "g1",
            "date_from": "2024-03-10",
            "date_to": "2024-03-10",
        })
    assert r.status_code == 200
    files = list(transcripts_dir.glob("*.txt"))
    assert len(files) == 1


async def test_generate_redirects_to_list(app):
    a, _, _ = app
    async with AsyncClient(
        transport=ASGITransport(app=a), base_url="http://test", follow_redirects=False
    ) as c:
        r = await c.post("/transcripts/generate", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
    assert r.status_code == 303
    assert r.headers["location"] == "/transcripts"


async def test_generate_then_list_shows_file(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/transcripts/generate", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        r = await c.get("/transcripts")
    assert "c1" in r.text
    assert "2024-03-10" in r.text


# ── GET /transcripts/{filename}/download ──────────────────────────────────────

async def test_download_returns_file(app):
    a, transcripts_dir, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/transcripts/generate", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        filename = list(transcripts_dir.glob("*.txt"))[0].name
        r = await c.get(f"/transcripts/{filename}/download")
    assert r.status_code == 200


async def test_download_content_disposition_attachment(app):
    a, transcripts_dir, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/transcripts/generate", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        filename = list(transcripts_dir.glob("*.txt"))[0].name
        r = await c.get(f"/transcripts/{filename}/download")
    assert "attachment" in r.headers["content-disposition"]
    assert filename in r.headers["content-disposition"]


async def test_download_contains_transcript_content(app):
    a, transcripts_dir, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/transcripts/generate", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        filename = list(transcripts_dir.glob("*.txt"))[0].name
        r = await c.get(f"/transcripts/{filename}/download")
    assert "Alice" in r.text
    assert "Hello world" in r.text


async def test_download_404_for_nonexistent(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/transcripts/ghost.txt/download")
    assert r.status_code == 404


async def test_download_404_for_path_traversal(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/transcripts/../../.env/download")
    assert r.status_code in (404, 422)


# ── GET /transcripts/{filename}/view ─────────────────────────────────────────

async def test_view_returns_200(app):
    a, transcripts_dir, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/transcripts/generate", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        filename = list(transcripts_dir.glob("*.txt"))[0].name
        r = await c.get(f"/transcripts/{filename}/view")
    assert r.status_code == 200


async def test_view_renders_inline_content(app):
    a, transcripts_dir, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/transcripts/generate", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        filename = list(transcripts_dir.glob("*.txt"))[0].name
        r = await c.get(f"/transcripts/{filename}/view")
    assert "Alice" in r.text
    assert "Hello world" in r.text
    assert "<pre" in r.text


async def test_view_shows_download_link(app):
    a, transcripts_dir, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/transcripts/generate", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        filename = list(transcripts_dir.glob("*.txt"))[0].name
        r = await c.get(f"/transcripts/{filename}/view")
    assert "download" in r.text.lower()


async def test_view_404_for_nonexistent(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/transcripts/ghost.txt/view")
    assert r.status_code == 404
