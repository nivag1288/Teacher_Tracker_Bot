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
            "VALUES ('m2','u2','Bob','c1','general','g1',datetime('now'),'hey',1,3)"
        )
        await db.execute(
            "INSERT INTO messages (message_id, author_id, author_name, channel_id, channel_name, guild_id, timestamp, content, word_count, char_count) "
            "VALUES ('m3','u1','Alice','c2','random','g1',datetime('now'),'hi',1,2)"
        )
        await db.execute(
            "INSERT INTO reactions (message_id, channel_id, guild_id, emoji, count, target_author_id, last_updated) "
            "VALUES ('m1','c1','g1','👍',3,'u1',datetime('now'))"
        )
        await db.commit()
    return create_app(db_path=db_path, status=BackfillStatus())


# ── GET /channels ─────────────────────────────────────────────────────────────

async def test_channel_list_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels")
    assert r.status_code == 200


async def test_channel_list_shows_channels(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels")
    assert "general" in r.text
    assert "random" in r.text


async def test_channel_list_html_content(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels")
    assert "text/html" in r.headers["content-type"]
    assert "Channels" in r.text


async def test_channel_list_sorted_by_message_count(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels")
    # general has 2 messages, random has 1
    general_pos = r.text.index("general")
    random_pos = r.text.index("random")
    assert general_pos < random_pos


async def test_channel_list_shows_unique_authors(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels")
    assert "Unique Users" in r.text


# ── GET /channels/{channel_id} ────────────────────────────────────────────────

async def test_channel_detail_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels/c1")
    assert r.status_code == 200


async def test_channel_detail_shows_name(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels/c1")
    assert "general" in r.text


async def test_channel_detail_shows_stat_cards(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels/c1")
    assert "Total Messages" in r.text
    assert "Total Reactions" in r.text


async def test_channel_detail_shows_top_contributors(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels/c1")
    assert "Top Contributors" in r.text
    assert "Alice" in r.text


async def test_channel_detail_dashboard_link(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels/c1")
    assert "scope=channel&channel_id=c1" in r.text


async def test_channel_detail_back_link(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels/c1")
    assert "/channels" in r.text


async def test_channel_detail_404_for_unknown(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels/does_not_exist")
    assert r.status_code == 404


async def test_channel_detail_shows_unique_authors_count(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/channels/c1")
    # c1 has Alice and Bob → 2 unique authors
    assert "2 unique author" in r.text
