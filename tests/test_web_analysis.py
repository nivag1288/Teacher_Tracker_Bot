import pytest
import aiosqlite
import json
from pathlib import Path
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport

from tracker.db import ALL_TABLES
from tracker.backfill import BackfillStatus
from web.app import create_app


_MOCK_RESPONSE = json.dumps({
    "topics": ["python", "testing"],
    "sentiment": "positive",
    "key_themes": ["quality"],
    "summary": "The team discussed testing practices.",
})


def _make_provider():
    p = AsyncMock()
    p.generate.return_value = _MOCK_RESPONSE
    return p


@pytest.fixture
async def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    transcripts_dir = tmp_path / "transcripts"
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m1','u1','Alice','c1','general','g1','2024-03-10T14:00:00','Hello world',2,11)"
        )
        await db.commit()
    return create_app(
        db_path=db_path,
        status=BackfillStatus(),
        transcripts_dir=transcripts_dir,
        llm_provider=_make_provider(),
    ), db_path, transcripts_dir


# ── GET /analysis ─────────────────────────────────────────────────────────────

async def test_analysis_list_returns_200(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/analysis")
    assert r.status_code == 200


async def test_analysis_list_html(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/analysis")
    assert "text/html" in r.headers["content-type"]
    assert "Analysis" in r.text


async def test_analysis_list_shows_run_form(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/analysis")
    assert "Analyze" in r.text
    assert "channel_id" in r.text


async def test_analysis_list_empty_state(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/analysis")
    assert "No analyses yet" in r.text


# ── POST /analysis/run ────────────────────────────────────────────────────────

async def test_run_redirects_to_detail(app):
    a, _, _ = app
    async with AsyncClient(
        transport=ASGITransport(app=a), base_url="http://test", follow_redirects=False
    ) as c:
        r = await c.post("/analysis/run", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
    assert r.status_code == 303
    assert r.headers["location"].startswith("/analysis/")


async def test_run_creates_db_record(app):
    a, db_path, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/analysis/run", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM analysis_results")
        assert (await cur.fetchone())[0] == 1


async def test_run_calls_llm_provider(app):
    a, _, _ = app
    provider = a.state.llm_provider
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/analysis/run", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
    provider.generate.assert_called_once()


async def test_run_caches_result_on_second_call(app):
    a, db_path, _ = app
    provider = a.state.llm_provider
    data = {"channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10"}
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/analysis/run", data=data)
        await c.post("/analysis/run", data=data)
    # LLM called only once — second run uses cache
    assert provider.generate.call_count == 1
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM analysis_results")
        assert (await cur.fetchone())[0] == 1


async def test_run_detail_page_shows_result(app):
    a, _, _ = app
    async with AsyncClient(
        transport=ASGITransport(app=a), base_url="http://test", follow_redirects=True
    ) as c:
        r = await c.post("/analysis/run", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
    assert r.status_code == 200
    assert "positive" in r.text
    assert "python" in r.text or "testing" in r.text


# ── GET /analysis/{id} ────────────────────────────────────────────────────────

async def test_analysis_detail_returns_200(app):
    a, db_path, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/analysis/run", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        r = await c.get("/analysis/1")
    assert r.status_code == 200


async def test_analysis_detail_shows_sentiment(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/analysis/run", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        r = await c.get("/analysis/1")
    assert "positive" in r.text


async def test_analysis_detail_shows_summary(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/analysis/run", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        r = await c.get("/analysis/1")
    assert "The team discussed testing practices" in r.text


async def test_analysis_detail_404_for_unknown(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/analysis/9999")
    assert r.status_code == 404


async def test_analysis_list_shows_past_results(app):
    a, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        await c.post("/analysis/run", data={
            "channel_id": "c1", "guild_id": "g1",
            "date_from": "2024-03-10", "date_to": "2024-03-10",
        })
        r = await c.get("/analysis")
    assert "c1" in r.text
    assert "2024-03-10" in r.text
