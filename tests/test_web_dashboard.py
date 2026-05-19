import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport

from tracker.db import ALL_TABLES
from tracker.backfill import BackfillStatus
from web.app import create_app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def empty_app(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    status = BackfillStatus()
    return create_app(db_path=db_path, status=status), db_path, status


@pytest.fixture
async def seeded_app(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.execute(
            "INSERT INTO messages (message_id, author_id, author_name, channel_id, channel_name, guild_id, timestamp, content, word_count, char_count) "
            "VALUES ('m1','u1','Alice','c1','general','g1',datetime('now'),'hello world',2,11)"
        )
        await db.execute(
            "INSERT INTO messages (message_id, author_id, author_name, channel_id, channel_name, guild_id, timestamp, content, word_count, char_count) "
            "VALUES ('m2','u2','Bob','c2','random','g1',datetime('now'),'hey',1,3)"
        )
        await db.execute(
            "INSERT INTO reactions (message_id, channel_id, guild_id, emoji, count, target_author_id, last_updated) "
            "VALUES ('m1','c1','g1','👍',4,'u1',datetime('now'))"
        )
        await db.execute(
            "INSERT INTO members (user_id, user_name, guild_id, event_type, timestamp) "
            "VALUES ('u1','Alice','g1','join',datetime('now'))"
        )
        await db.commit()
    status = BackfillStatus()
    return create_app(db_path=db_path, status=status), db_path, status


# ── GET / — basic response ────────────────────────────────────────────────────

async def test_dashboard_returns_200(seeded_app):
    app, _, _ = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code == 200


async def test_dashboard_html_content_type(seeded_app):
    app, _, _ = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert "text/html" in r.headers["content-type"]


async def test_dashboard_shows_stat_values(seeded_app):
    app, _, _ = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    body = r.text
    assert "Total Messages" in body
    assert "Unique Users" in body
    assert "Channels Tracked" in body


async def test_dashboard_shows_top_users(seeded_app):
    app, _, _ = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert "Alice" in r.text
    assert "Bob" in r.text


# ── Empty DB ──────────────────────────────────────────────────────────────────

async def test_dashboard_empty_db_shows_no_data_notice(empty_app):
    app, _, _ = empty_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code == 200
    assert "No data yet" in r.text


# ── Backfill banner ───────────────────────────────────────────────────────────

async def test_dashboard_banner_present_when_running(seeded_app):
    app, _, status = seeded_app
    status.running = True
    status.channels_done = 2
    status.channels_total = 5
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert "backfill-banner" in r.text


async def test_dashboard_banner_absent_when_not_running(seeded_app):
    app, _, status = seeded_app
    status.running = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert "backfill-banner" not in r.text


# ── /api/backfill-status ──────────────────────────────────────────────────────

async def test_backfill_status_endpoint_returns_json(empty_app):
    app, _, _ = empty_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/backfill-status")
    assert r.status_code == 200
    data = r.json()
    assert "running" in data
    assert "channels_done" in data
    assert "channels_total" in data
    assert "messages_ingested" in data


async def test_backfill_status_reflects_state(empty_app):
    app, _, status = empty_app
    status.running = True
    status.channels_done = 3
    status.channels_total = 7
    status.messages_ingested = 42
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/backfill-status")
    data = r.json()
    assert data["running"] is True
    assert data["channels_done"] == 3
    assert data["channels_total"] == 7
    assert data["messages_ingested"] == 42


async def test_backfill_status_not_running_by_default(empty_app):
    app, _, _ = empty_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/backfill-status")
    assert r.json()["running"] is False


# ── Scope filtering ───────────────────────────────────────────────────────────

async def test_dashboard_channel_scope(seeded_app):
    app, _, _ = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/?scope=channel&channel_id=c1")
    assert r.status_code == 200
    # channel scope hides top-users table header but shows stat cards
    assert "Total Messages" in r.text


async def test_dashboard_user_scope(seeded_app):
    app, _, _ = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/?scope=user&user_id=u1")
    assert r.status_code == 200
    assert "Total Messages" in r.text


async def test_dashboard_invalid_scope_falls_back_to_server(seeded_app):
    app, _, _ = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/?scope=bogus")
    assert r.status_code == 200
    # server scope shows both top users and top channels sections
    assert "Top Users" in r.text
    assert "Top Channels" in r.text
