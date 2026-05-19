import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport

from tracker.db import ALL_TABLES
from tracker.backfill import BackfillStatus
from web.app import create_app


@pytest.fixture
async def app(tmp_path):
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
            "VALUES ('m2','u1','Alice','c2','random','g1',datetime('now'),'hey',1,3)"
        )
        await db.execute(
            "INSERT INTO messages (message_id, author_id, author_name, channel_id, channel_name, guild_id, timestamp, content, word_count, char_count) "
            "VALUES ('m3','u2','Bob','c1','general','g1',datetime('now'),'hi',1,2)"
        )
        await db.execute(
            "INSERT INTO reactions (message_id, channel_id, guild_id, emoji, count, target_author_id, last_updated) "
            "VALUES ('m1','c1','g1','👍',5,'u1',datetime('now'))"
        )
        await db.commit()
    return create_app(db_path=db_path, status=BackfillStatus())


# ── GET /users ────────────────────────────────────────────────────────────────

async def test_user_list_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users")
    assert r.status_code == 200


async def test_user_list_shows_users(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users")
    assert "Alice" in r.text
    assert "Bob" in r.text


async def test_user_list_html_content(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users")
    assert "text/html" in r.headers["content-type"]
    assert "Users" in r.text


async def test_user_list_sorted_by_message_count(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users")
    # Alice has 2 messages, Bob has 1 — Alice should appear first
    alice_pos = r.text.index("Alice")
    bob_pos = r.text.index("Bob")
    assert alice_pos < bob_pos


# ── GET /users/{user_id} ──────────────────────────────────────────────────────

async def test_user_detail_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/u1")
    assert r.status_code == 200


async def test_user_detail_shows_name(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/u1")
    assert "Alice" in r.text


async def test_user_detail_shows_stat_cards(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/u1")
    assert "Total Messages" in r.text
    assert "Reactions Received" in r.text


async def test_user_detail_shows_top_channels(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/u1")
    assert "Top Channels" in r.text
    assert "general" in r.text


async def test_user_detail_dashboard_link(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/u1")
    assert "scope=user&user_id=u1" in r.text


async def test_user_detail_back_link(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/u1")
    assert "/users" in r.text


async def test_user_detail_404_for_unknown(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/does_not_exist")
    assert r.status_code == 404


async def test_user_detail_shows_reactions(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/u1")
    # Alice received 5 reactions
    assert "5" in r.text
