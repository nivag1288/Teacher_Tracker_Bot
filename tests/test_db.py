import os
import pytest
import aiosqlite
from tracker.db import create_tables, connect, ALL_TABLES
from tracker.models import Message, Reaction, Member, BackfillState, AnalysisResult
from tests.conftest import make_message, make_reaction, make_member


# ── Schema ──────────────────────────────────────────────────────────────────

async def test_all_tables_created(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    names = {r[0] for r in rows} - {"sqlite_sequence"}
    assert names == {"messages", "reactions", "members", "backfill_state", "analysis_results"}


async def test_messages_columns(db):
    cursor = await db.execute("PRAGMA table_info(messages)")
    cols = {row[1] for row in await cursor.fetchall()}
    expected = {
        "id", "message_id", "author_id", "author_name", "channel_id",
        "channel_name", "guild_id", "timestamp", "content", "word_count",
        "char_count", "has_attachment", "has_mention", "is_reply", "reply_to_author_id",
    }
    assert expected.issubset(cols)


async def test_reactions_columns(db):
    cursor = await db.execute("PRAGMA table_info(reactions)")
    cols = {row[1] for row in await cursor.fetchall()}
    expected = {"id", "message_id", "channel_id", "guild_id", "emoji", "count", "target_author_id", "last_updated"}
    assert expected.issubset(cols)


async def test_members_columns(db):
    cursor = await db.execute("PRAGMA table_info(members)")
    cols = {row[1] for row in await cursor.fetchall()}
    expected = {"id", "user_id", "user_name", "guild_id", "event_type", "timestamp"}
    assert expected.issubset(cols)


async def test_backfill_state_columns(db):
    cursor = await db.execute("PRAGMA table_info(backfill_state)")
    cols = {row[1] for row in await cursor.fetchall()}
    expected = {"channel_id", "guild_id", "newest_message_id", "last_backfill"}
    assert expected.issubset(cols)


async def test_analysis_results_columns(db):
    cursor = await db.execute("PRAGMA table_info(analysis_results)")
    cols = {row[1] for row in await cursor.fetchall()}
    expected = {"id", "channel_id", "guild_id", "date_from", "date_to", "topics", "sentiment", "summary", "created_at"}
    assert expected.issubset(cols)


async def test_message_id_unique_constraint(db):
    msg = make_message()
    await db.execute(
        "INSERT INTO messages (message_id, author_id, author_name, channel_id, channel_name, guild_id, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (msg.message_id, msg.author_id, msg.author_name, msg.channel_id, msg.channel_name, msg.guild_id, msg.timestamp),
    )
    await db.commit()
    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute(
            "INSERT INTO messages (message_id, author_id, author_name, channel_id, channel_name, guild_id, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg.message_id, "other", "Bob", "chan_2", "random", "guild_1", "2024-01-16T10:00:00"),
        )
        await db.commit()


async def test_reaction_unique_per_message_emoji(db):
    r = make_reaction()
    await db.execute(
        "INSERT INTO reactions (message_id, channel_id, guild_id, emoji, count, target_author_id, last_updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (r.message_id, r.channel_id, r.guild_id, r.emoji, r.count, r.target_author_id, r.last_updated),
    )
    await db.commit()
    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute(
            "INSERT INTO reactions (message_id, channel_id, guild_id, emoji, count, target_author_id, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (r.message_id, r.channel_id, r.guild_id, r.emoji, 5, r.target_author_id, r.last_updated),
        )
        await db.commit()


async def test_create_tables_on_disk(tmp_path):
    db_path = str(tmp_path / "test.db")
    await create_tables(db_path)
    assert os.path.exists(db_path)
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {r[0] for r in await cursor.fetchall()} - {"sqlite_sequence"}
    assert len(names) == 5


async def test_create_tables_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    await create_tables(db_path)
    await create_tables(db_path)  # should not raise


async def test_connect_returns_context_manager(tmp_path):
    db_path = str(tmp_path / "test.db")
    await create_tables(db_path)
    async with connect(db_path) as conn:
        cursor = await conn.execute("SELECT 1")
        row = await cursor.fetchone()
    assert row[0] == 1


# ── Models ───────────────────────────────────────────────────────────────────

def test_message_defaults():
    m = Message(
        message_id="x", author_id="u1", author_name="A",
        channel_id="c1", channel_name="gen", guild_id="g1", timestamp="2024-01-01T00:00:00",
    )
    assert m.word_count == 0
    assert m.is_reply is False
    assert m.reply_to_author_id is None


def test_message_with_reply():
    m = make_message(is_reply=True, reply_to_author_id="user_2")
    assert m.is_reply is True
    assert m.reply_to_author_id == "user_2"


def test_reaction_fields():
    r = make_reaction(emoji="❤️", count=10)
    assert r.emoji == "❤️"
    assert r.count == 10


def test_member_join_leave():
    join = make_member(event_type="join")
    leave = make_member(event_type="leave")
    assert join.event_type == "join"
    assert leave.event_type == "leave"


def test_backfill_state_defaults():
    bs = BackfillState(
        channel_id="c1", guild_id="g1", last_backfill="2024-01-01T00:00:00"
    )
    assert bs.newest_message_id is None


def test_analysis_result_fields():
    ar = AnalysisResult(
        channel_id="c1", guild_id="g1",
        date_from="2024-01-01", date_to="2024-01-07",
        created_at="2024-01-07T12:00:00",
        topics='["strategy", "bugs"]',
        sentiment="positive",
        summary="Active week with positive discussion.",
    )
    assert ar.id is None
    assert ar.sentiment == "positive"


# ── Config ───────────────────────────────────────────────────────────────────

def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok123")
    monkeypatch.setenv("DISCORD_GUILD_ID", "987654321")
    monkeypatch.setenv("OLLAMA_HOST", "myhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "mistral")
    monkeypatch.setenv("DB_PATH", "data/mydb.db")
    monkeypatch.setenv("WEB_PORT", "9090")

    import importlib
    import bot.config as cfg
    importlib.reload(cfg)

    assert cfg.DISCORD_TOKEN == "tok123"
    assert cfg.DISCORD_GUILD_ID == 987654321
    assert cfg.OLLAMA_HOST == "myhost:11434"
    assert cfg.OLLAMA_MODEL == "mistral"
    assert cfg.DB_PATH == "data/mydb.db"
    assert cfg.WEB_PORT == 9090


def test_config_defaults(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_GUILD_ID", "123")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("WEB_PORT", raising=False)

    import importlib
    import bot.config as cfg
    importlib.reload(cfg)

    assert cfg.OLLAMA_HOST == "localhost:11434"
    assert cfg.OLLAMA_MODEL == "llama3.2"
    assert cfg.DB_PATH == "data/stats.db"
    assert cfg.WEB_PORT == 8080


def test_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_GUILD_ID", "123")
    from bot.config import ConfigError
    import importlib
    import bot.config as cfg
    with pytest.raises((ConfigError, SystemExit, Exception)):
        importlib.reload(cfg)
