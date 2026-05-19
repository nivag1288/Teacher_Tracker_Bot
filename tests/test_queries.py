import pytest
import aiosqlite
from datetime import datetime, timezone, timedelta

from tracker.queries import StatsQuery, Scope
from tracker.db import ALL_TABLES


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    async with aiosqlite.connect(path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    return path


def _ts(delta_days=0):
    return (datetime.now(timezone.utc) - timedelta(days=delta_days)).isoformat()


async def _insert_message(db_path, msg_id, author_id, author_name, channel_id, channel_name, guild_id="g1", ts=None, content="hello"):
    ts = ts or _ts()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO messages "
            "(message_id, author_id, author_name, channel_id, channel_name, guild_id, timestamp, content, word_count, char_count) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [str(msg_id), str(author_id), author_name, str(channel_id), channel_name, guild_id, ts, content, len(content.split()), len(content)],
        )
        await db.commit()


async def _insert_reaction(db_path, msg_id, channel_id, guild_id, emoji, count, target_author_id):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO reactions (message_id, channel_id, guild_id, emoji, count, target_author_id, last_updated) "
            "VALUES (?,?,?,?,?,?,?)",
            [str(msg_id), str(channel_id), guild_id, emoji, count, str(target_author_id), _ts()],
        )
        await db.commit()


async def _insert_member(db_path, user_id, user_name, guild_id, event_type, ts=None):
    ts = ts or _ts()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO members (user_id, user_name, guild_id, event_type, timestamp) VALUES (?,?,?,?,?)",
            [str(user_id), user_name, guild_id, event_type, ts],
        )
        await db.commit()


async def _insert_backfill(db_path, channel_id, guild_id, newest_id=None):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO backfill_state (channel_id, guild_id, newest_message_id, last_backfill) VALUES (?,?,?,?)",
            [str(channel_id), guild_id, str(newest_id) if newest_id else None, _ts()],
        )
        await db.commit()


# ── Scope helpers ─────────────────────────────────────────────────────────────

def server_scope():
    return Scope(mode="server")


def channel_scope(channel_id="c1"):
    return Scope(mode="channel", channel_id=channel_id)


def user_scope(user_id="u1"):
    return Scope(mode="user", user_id=user_id)


# ── messages_count ────────────────────────────────────────────────────────────

async def test_messages_count_server(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u2", "Bob", "c2", "random")
    q = StatsQuery(db_path)
    assert await q.messages_count(server_scope()) == 2


async def test_messages_count_channel_scope(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u2", "Bob", "c2", "random")
    q = StatsQuery(db_path)
    assert await q.messages_count(channel_scope("c1")) == 1


async def test_messages_count_user_scope(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u2", "Bob", "c1", "general")
    q = StatsQuery(db_path)
    assert await q.messages_count(user_scope("u1")) == 1


async def test_messages_count_empty(db_path):
    q = StatsQuery(db_path)
    assert await q.messages_count(server_scope()) == 0


# ── unique_users ──────────────────────────────────────────────────────────────

async def test_unique_users_server(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 3, "u2", "Bob", "c1", "general")
    q = StatsQuery(db_path)
    assert await q.unique_users(server_scope()) == 2


async def test_unique_users_user_scope_returns_one(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    q = StatsQuery(db_path)
    assert await q.unique_users(user_scope("u1")) == 1


async def test_unique_users_user_scope_no_id_returns_zero(db_path):
    q = StatsQuery(db_path)
    assert await q.unique_users(Scope(mode="user")) == 0


# ── channels_tracked ──────────────────────────────────────────────────────────

async def test_channels_tracked_server(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u1", "Alice", "c2", "random")
    q = StatsQuery(db_path)
    assert await q.channels_tracked(server_scope()) == 2


async def test_channels_tracked_channel_scope_returns_one(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    q = StatsQuery(db_path)
    assert await q.channels_tracked(channel_scope("c1")) == 1


async def test_channels_tracked_channel_scope_no_id_returns_zero(db_path):
    q = StatsQuery(db_path)
    assert await q.channels_tracked(Scope(mode="channel")) == 0


# ── messages_today ────────────────────────────────────────────────────────────

async def test_messages_today(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general", ts=_ts(0))
    await _insert_message(db_path, 2, "u1", "Alice", "c1", "general", ts=_ts(2))
    q = StatsQuery(db_path)
    assert await q.messages_today(server_scope()) == 1


async def test_messages_today_channel_scope(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general", ts=_ts(0))
    await _insert_message(db_path, 2, "u1", "Alice", "c2", "random", ts=_ts(0))
    q = StatsQuery(db_path)
    assert await q.messages_today(channel_scope("c1")) == 1


# ── messages_this_week ────────────────────────────────────────────────────────

async def test_messages_this_week(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general", ts=_ts(3))
    await _insert_message(db_path, 2, "u1", "Alice", "c1", "general", ts=_ts(10))
    q = StatsQuery(db_path)
    assert await q.messages_this_week(server_scope()) == 1


# ── top_users ─────────────────────────────────────────────────────────────────

async def test_top_users_server(db_path):
    for i in range(3):
        await _insert_message(db_path, i, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 10, "u2", "Bob", "c1", "general")
    q = StatsQuery(db_path)
    result = await q.top_users(server_scope())
    assert result[0]["author_name"] == "Alice"
    assert result[0]["count"] == 3


async def test_top_users_channel_scope(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u2", "Bob", "c2", "random")
    q = StatsQuery(db_path)
    result = await q.top_users(channel_scope("c1"))
    assert len(result) == 1
    assert result[0]["author_name"] == "Alice"


async def test_top_users_limit(db_path):
    for i in range(10):
        await _insert_message(db_path, i, f"u{i}", f"User{i}", "c1", "general")
    q = StatsQuery(db_path)
    result = await q.top_users(server_scope(), limit=3)
    assert len(result) == 3


# ── top_channels ──────────────────────────────────────────────────────────────

async def test_top_channels_server(db_path):
    for i in range(4):
        await _insert_message(db_path, i, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 10, "u1", "Alice", "c2", "random")
    q = StatsQuery(db_path)
    result = await q.top_channels(server_scope())
    assert result[0]["channel_name"] == "general"
    assert result[0]["count"] == 4


async def test_top_channels_user_scope(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u2", "Bob", "c1", "general")
    q = StatsQuery(db_path)
    result = await q.top_channels(user_scope("u1"))
    assert len(result) == 1
    assert result[0]["channel_name"] == "general"


# ── reaction_totals ───────────────────────────────────────────────────────────

async def test_reaction_totals_server(db_path):
    await _insert_reaction(db_path, "m1", "c1", "g1", "👍", 3, "u1")
    await _insert_reaction(db_path, "m2", "c1", "g1", "❤️", 2, "u1")
    q = StatsQuery(db_path)
    assert await q.reaction_totals(server_scope()) == 5


async def test_reaction_totals_user_scope(db_path):
    await _insert_reaction(db_path, "m1", "c1", "g1", "👍", 3, "u1")
    await _insert_reaction(db_path, "m2", "c1", "g1", "❤️", 2, "u2")
    q = StatsQuery(db_path)
    assert await q.reaction_totals(user_scope("u1")) == 3


async def test_reaction_totals_empty(db_path):
    q = StatsQuery(db_path)
    assert await q.reaction_totals(server_scope()) == 0


# ── daily_trend ───────────────────────────────────────────────────────────────

async def test_daily_trend_returns_dates(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general", ts=_ts(0))
    await _insert_message(db_path, 2, "u1", "Alice", "c1", "general", ts=_ts(1))
    q = StatsQuery(db_path)
    result = await q.daily_trend(server_scope(), days=30)
    assert len(result) == 2
    assert "date" in result[0]
    assert "count" in result[0]


async def test_daily_trend_excludes_old_messages(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general", ts=_ts(0))
    await _insert_message(db_path, 2, "u1", "Alice", "c1", "general", ts=_ts(40))
    q = StatsQuery(db_path)
    result = await q.daily_trend(server_scope(), days=30)
    assert len(result) == 1


# ── active_hours ──────────────────────────────────────────────────────────────

async def test_active_hours_returns_hour_weekday(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    q = StatsQuery(db_path)
    result = await q.active_hours(server_scope())
    assert len(result) >= 1
    assert "hour" in result[0]
    assert "weekday" in result[0]
    assert "count" in result[0]


# ── recent_member_events ──────────────────────────────────────────────────────

async def test_recent_member_events(db_path):
    await _insert_member(db_path, "u1", "Alice", "g1", "join")
    await _insert_member(db_path, "u2", "Bob", "g1", "leave")
    q = StatsQuery(db_path)
    result = await q.recent_member_events()
    assert len(result) == 2
    assert result[0]["user_name"] in ("Alice", "Bob")


async def test_recent_member_events_limit(db_path):
    for i in range(15):
        await _insert_member(db_path, f"u{i}", f"User{i}", "g1", "join", ts=_ts(i))
    q = StatsQuery(db_path)
    result = await q.recent_member_events(limit=5)
    assert len(result) == 5


# ── backfill_timestamps ───────────────────────────────────────────────────────

async def test_backfill_timestamps(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_backfill(db_path, "c1", "g1", newest_id=1)
    q = StatsQuery(db_path)
    result = await q.backfill_timestamps()
    assert len(result) == 1
    assert result[0]["channel_name"] == "general"


# ── all_channels / all_users ──────────────────────────────────────────────────

async def test_all_channels(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u1", "Alice", "c2", "random")
    q = StatsQuery(db_path)
    result = await q.all_channels()
    names = [r["channel_name"] for r in result]
    assert "general" in names
    assert "random" in names


async def test_all_users(db_path):
    await _insert_message(db_path, 1, "u1", "Alice", "c1", "general")
    await _insert_message(db_path, 2, "u2", "Bob", "c1", "general")
    q = StatsQuery(db_path)
    result = await q.all_users()
    names = [r["author_name"] for r in result]
    assert "Alice" in names
    assert "Bob" in names
