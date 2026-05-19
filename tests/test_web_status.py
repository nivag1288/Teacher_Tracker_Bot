import pytest
import aiosqlite
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport

from tracker.db import ALL_TABLES
from tracker.backfill import BackfillStatus
from web.app import create_app


@pytest.fixture
async def empty_app(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    return create_app(db_path=db_path, status=BackfillStatus())


@pytest.fixture
async def seeded_app(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m1','u1','Alice','c1','general','g1',datetime('now'),'hi',1,2)"
        )
        await db.execute(
            "INSERT INTO backfill_state (channel_id,guild_id,newest_message_id,last_backfill) "
            "VALUES ('c1','g1','m1',datetime('now'))"
        )
        await db.commit()
    return create_app(db_path=db_path, status=BackfillStatus())


# ── GET /status (HTML) ────────────────────────────────────────────────────────

async def test_status_returns_200(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/status")
    assert r.status_code == 200


async def test_status_html_content_type(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/status")
    assert "text/html" in r.headers["content-type"]


async def test_status_shows_uptime(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/status")
    assert "Uptime" in r.text


async def test_status_shows_message_count(seeded_app):
    async with AsyncClient(transport=ASGITransport(app=seeded_app), base_url="http://test") as c:
        r = await c.get("/status")
    assert "Total Messages" in r.text
    assert "1" in r.text


async def test_status_shows_backfill_table(seeded_app):
    async with AsyncClient(transport=ASGITransport(app=seeded_app), base_url="http://test") as c:
        r = await c.get("/status")
    assert "general" in r.text


async def test_status_empty_db_renders_gracefully(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/status")
    assert r.status_code == 200
    assert "No backfill data yet" in r.text


async def test_status_ollama_not_configured_when_no_provider(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/status")
    assert "not configured" in r.text


async def test_status_ollama_online_badge(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    provider = AsyncMock()
    provider.ping = AsyncMock(return_value=True)
    app = create_app(db_path=db_path, status=BackfillStatus(), llm_provider=provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/status")
    assert "online" in r.text


async def test_status_ollama_offline_badge(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    provider = AsyncMock()
    provider.ping = AsyncMock(return_value=False)
    app = create_app(db_path=db_path, status=BackfillStatus(), llm_provider=provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/status")
    assert "offline" in r.text


# ── GET /api/status (JSON) ────────────────────────────────────────────────────

async def test_api_status_returns_200(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/api/status")
    assert r.status_code == 200


async def test_api_status_json_fields(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/api/status")
    data = r.json()
    assert "total_messages" in data
    assert "backfill_channels" in data
    assert "ollama_ok" in data
    assert "uptime" in data


async def test_api_status_message_count_correct(seeded_app):
    async with AsyncClient(transport=ASGITransport(app=seeded_app), base_url="http://test") as c:
        r = await c.get("/api/status")
    assert r.json()["total_messages"] == 1


async def test_api_status_ollama_none_when_no_provider(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/api/status")
    assert r.json()["ollama_ok"] is None
