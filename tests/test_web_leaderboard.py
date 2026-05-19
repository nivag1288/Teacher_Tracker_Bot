import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta

from tracker.db import ALL_TABLES
from tracker.backfill import BackfillStatus
from tracker.queries import StatsQuery
from web.app import create_app


def _ts(delta_days=0):
    return (datetime.now(timezone.utc) - timedelta(days=delta_days)).isoformat()


@pytest.fixture
async def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        # Alice: 3 messages (2 this week, 1 last week), 1 reply sent
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count,is_reply,reply_to_author_id) "
            "VALUES ('m1','u1','Alice','c1','general','g1',?,'hi',1,2,0,NULL)", [_ts(0)]
        )
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count,is_reply,reply_to_author_id) "
            "VALUES ('m2','u1','Alice','c1','general','g1',?,'hey',1,3,0,NULL)", [_ts(3)]
        )
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count,is_reply,reply_to_author_id) "
            "VALUES ('m3','u1','Alice','c1','general','g1',?,'reply msg',2,9,1,'u2')", [_ts(10)]
        )
        # Bob: 1 message this week
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count,is_reply,reply_to_author_id) "
            "VALUES ('m4','u2','Bob','c1','general','g1',?,'yo',1,2,0,NULL)", [_ts(1)]
        )
        # Reactions: Bob's message gets 4, Alice's gets 2
        await db.execute(
            "INSERT INTO reactions (message_id,channel_id,guild_id,emoji,count,target_author_id,last_updated) "
            "VALUES ('m4','c1','g1','👍',4,'u2',?)", [_ts(0)]
        )
        await db.execute(
            "INSERT INTO reactions (message_id,channel_id,guild_id,emoji,count,target_author_id,last_updated) "
            "VALUES ('m1','c1','g1','❤️',2,'u1',?)", [_ts(0)]
        )
        await db.commit()
    return create_app(db_path=db_path, status=BackfillStatus()), db_path


@pytest.fixture
async def empty_app(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    return create_app(db_path=db_path, status=BackfillStatus())


# ── GET /leaderboard ──────────────────────────────────────────────────────────

async def test_leaderboard_returns_200(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard")
    assert r.status_code == 200


async def test_leaderboard_html_content(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard")
    assert "text/html" in r.headers["content-type"]
    assert "Leaderboard" in r.text


async def test_leaderboard_default_type_is_messages(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard")
    assert "Messages" in r.text
    # Alice (3 msgs) should rank above Bob (1 msg)
    alice_pos = r.text.index("Alice")
    bob_pos = r.text.index("Bob")
    assert alice_pos < bob_pos


async def test_leaderboard_messages_type_explicit(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard?type=messages")
    assert r.status_code == 200
    assert "Alice" in r.text


async def test_leaderboard_reactions_type(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard?type=reactions")
    assert r.status_code == 200
    # Bob has 4 reactions, Alice has 2 → Bob first
    bob_pos = r.text.index("Bob")
    alice_pos = r.text.index("Alice")
    assert bob_pos < alice_pos


async def test_leaderboard_replies_sent_type(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard?type=replies_sent")
    assert r.status_code == 200
    # Only Alice sent a reply
    assert "Alice" in r.text
    assert "Bob" not in r.text


async def test_leaderboard_replies_received_type(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard?type=replies_received")
    assert r.status_code == 200
    # Alice's reply was directed at u2 (Bob)
    assert r.status_code == 200


async def test_leaderboard_invalid_type_falls_back_to_messages(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard?type=bogus")
    assert r.status_code == 200
    # fallback: should show Alice and Bob (messages ranking)
    assert "Alice" in r.text


async def test_leaderboard_limit_param(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard?type=messages&limit=1")
    assert r.status_code == 200
    # Only Alice (top 1) should appear
    assert "Alice" in r.text
    assert "Bob" not in r.text


async def test_leaderboard_invalid_limit_falls_back(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard?limit=abc")
    assert r.status_code == 200


async def test_leaderboard_empty_db_shows_no_data(empty_app):
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as c:
        r = await c.get("/leaderboard")
    assert r.status_code == 200
    assert "No data yet" in r.text


async def test_leaderboard_shows_trend_column(app):
    a, _ = app
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/leaderboard")
    assert "Trend" in r.text
    assert "This Week" in r.text
    assert "Last Week" in r.text


# ── StatsQuery.leaderboard() unit tests ──────────────────────────────────────

async def test_leaderboard_query_messages_sorted(app):
    _, db_path = app
    q = StatsQuery(db_path)
    rows = await q.leaderboard(type="messages", limit=10)
    assert rows[0]["author_name"] == "Alice"
    assert rows[0]["total"] == 3


async def test_leaderboard_query_reactions_sorted(app):
    _, db_path = app
    q = StatsQuery(db_path)
    rows = await q.leaderboard(type="reactions", limit=10)
    assert rows[0]["author_name"] == "Bob"
    assert rows[0]["total"] == 4


async def test_leaderboard_query_replies_sent(app):
    _, db_path = app
    q = StatsQuery(db_path)
    rows = await q.leaderboard(type="replies_sent", limit=10)
    assert len(rows) == 1
    assert rows[0]["author_name"] == "Alice"
    assert rows[0]["total"] == 1


async def test_leaderboard_query_limit_respected(app):
    _, db_path = app
    q = StatsQuery(db_path)
    rows = await q.leaderboard(type="messages", limit=1)
    assert len(rows) == 1


async def test_leaderboard_query_unknown_type_returns_empty(app):
    _, db_path = app
    q = StatsQuery(db_path)
    rows = await q.leaderboard(type="invalid", limit=10)
    assert rows == []


async def test_leaderboard_query_trend_field_present(app):
    _, db_path = app
    q = StatsQuery(db_path)
    rows = await q.leaderboard(type="messages", limit=10)
    for row in rows:
        assert "trend" in row
        assert row["trend"] in ("up", "down", "flat")
