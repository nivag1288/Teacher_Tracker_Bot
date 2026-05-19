"""Targeted tests for lines not yet exercised by the main test files."""
import pytest
import aiosqlite
import discord
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from tracker.db import ALL_TABLES
from tracker.backfill import BackfillEngine, BackfillStatus
from tracker.queries import StatsQuery, Scope
from analysis.transcript import TranscriptBuilder
from analysis.semantic import _parse_response
from web.app import create_app
from httpx import AsyncClient, ASGITransport


# ── audit-log kick/ban branch (backfill.py 141-147) ──────────────────────────

@pytest.fixture
async def engine(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    return BackfillEngine(db_path=db_path, status=BackfillStatus()), db_path


def make_mock_guild_with_audit(entries):
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    guild.name = "TestGuild"
    guild.channels = []
    guild.members = []
    guild.member_count = 0

    async def _audit_logs(**kwargs):
        for e in entries:
            yield e

    guild.audit_logs = _audit_logs
    return guild


async def test_backfill_members_records_kick(engine):
    eng, db_path = engine

    target = MagicMock()
    target.id = 99
    target.display_name = "KickedUser"
    target.bot = False

    entry = MagicMock()
    entry.action = discord.AuditLogAction.kick
    entry.target = target
    entry.created_at = datetime(2024, 1, 5, 12, 0, 0, tzinfo=timezone.utc)

    guild = make_mock_guild_with_audit([entry])
    with patch.object(eng, "backfill_members", wraps=eng.backfill_members):
        await eng.backfill_members(guild)

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT user_name, event_type FROM members WHERE user_id = '99'"
        )
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == "KickedUser"
    assert row[1] == "leave"


async def test_backfill_members_skips_bot_kick(engine):
    eng, db_path = engine

    target = MagicMock()
    target.id = 88
    target.display_name = "BotTarget"
    target.bot = True

    entry = MagicMock()
    entry.action = discord.AuditLogAction.kick
    entry.target = target
    entry.created_at = datetime(2024, 1, 5, tzinfo=timezone.utc)

    guild = make_mock_guild_with_audit([entry])
    await eng.backfill_members(guild)

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM members WHERE user_id = '88'")
        assert (await cur.fetchone())[0] == 0


async def test_backfill_members_skips_non_leave_audit_action(engine):
    eng, db_path = engine

    entry = MagicMock()
    entry.action = discord.AuditLogAction.message_delete
    entry.target = MagicMock()

    guild = make_mock_guild_with_audit([entry])
    await eng.backfill_members(guild)

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM members")
        assert (await cur.fetchone())[0] == 0


async def test_backfill_members_handles_none_target(engine):
    eng, db_path = engine

    entry = MagicMock()
    entry.action = discord.AuditLogAction.kick
    entry.target = None
    entry.created_at = datetime(2024, 1, 5, tzinfo=timezone.utc)

    guild = make_mock_guild_with_audit([entry])
    await eng.backfill_members(guild)  # should not raise

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM members")
        assert (await cur.fetchone())[0] == 0


# ── transcript bad-timestamp branch (transcript.py 30-31) ────────────────────

async def test_transcript_handles_bad_timestamp(tmp_path):
    db_path = str(tmp_path / "test.db")
    transcripts_dir = tmp_path / "transcripts"
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        # Julian-day number: SQLite's date() returns '2024-01-06' (passes WHERE filter),
        # but Python's fromisoformat() raises ValueError — exercises lines 30-31.
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m1','u1','Alice','c1','general','g1','2460315.5','hello',1,5)"
        )
        await db.commit()
    builder = TranscriptBuilder(db_path, transcripts_dir)
    path = await builder.build("c1", "g1", "0001-01-01", "9999-12-31")
    content = path.read_text()
    assert "Alice" in content
    assert "hello" in content


# ── semantic parse: JSON found but invalid (semantic.py 43-44) ───────────────

def test_parse_response_invalid_json_inside_braces():
    raw = "Here: {not valid json at all: :::}"
    result = _parse_response(raw)
    # Falls through to degraded path
    assert result["sentiment"] == "neutral"
    assert result["topics"] == []


# ── leaderboard flat trend (queries.py 336) ───────────────────────────────────

async def test_leaderboard_flat_trend(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        # Insert 0 messages this week and 0 last week for a user (flat)
        # We need a row with this_week == last_week == 0, but total > 0
        # Insert an old message (>14 days ago)
        from datetime import timedelta
        old_ts = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m1','u1','Alice','c1','general','g1',?,'hi',1,2)", [old_ts]
        )
        await db.commit()
    q = StatsQuery(db_path)
    rows = await q.leaderboard(type="messages", limit=10)
    assert len(rows) == 1
    assert rows[0]["trend"] == "flat"
    assert rows[0]["this_week"] == 0
    assert rows[0]["last_week"] == 0


# ── most_reacted_messages server scope (queries.py 215) ──────────────────────

async def test_most_reacted_server_scope(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m1','u1','Alice','c1','general','g1',datetime('now'),'hi',1,2)"
        )
        await db.execute(
            "INSERT INTO reactions (message_id,channel_id,guild_id,emoji,count,target_author_id,last_updated) "
            "VALUES ('m1','c1','g1','👍',3,'u1',datetime('now'))"
        )
        await db.commit()
    q = StatsQuery(db_path)
    rows = await q.most_reacted_messages(Scope(mode="server"), limit=5)
    assert len(rows) == 1
    assert rows[0]["reactions"] == 3


# ── _safe_path traversal guard (transcripts.py 18) ───────────────────────────

def test_safe_path_rejects_traversal(tmp_path):
    from web.routes.transcripts import _safe_path
    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir()
    result = _safe_path(transcripts_dir, "../../etc/passwd")
    assert result is None


def test_safe_path_rejects_nonexistent_file(tmp_path):
    from web.routes.transcripts import _safe_path
    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir()
    result = _safe_path(transcripts_dir, "ghost.txt")
    assert result is None


def test_safe_path_accepts_valid_file(tmp_path):
    from web.routes.transcripts import _safe_path
    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir()
    f = transcripts_dir / "valid.txt"
    f.write_text("content")
    result = _safe_path(transcripts_dir, "valid.txt")
    assert result == f


# ── leaderboard down trend with non-zero counts (queries.py 336) ─────────────

async def test_leaderboard_down_trend(tmp_path):
    """Cover the elif this_week < last_week branch (both non-zero, last week busier)."""
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        # 1 message this week + 2 messages last week → this_week=1, last_week=2 → down
        this_week_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        last_week_ts1 = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
        last_week_ts2 = (datetime.now(timezone.utc) - timedelta(days=11)).isoformat()
        for mid, ts in [("m1", this_week_ts), ("m2", last_week_ts1), ("m3", last_week_ts2)]:
            await db.execute(
                "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                [mid, "u1", "Alice", "c1", "general", "g1", ts, "hi", 1, 2],
            )
        await db.commit()
    q = StatsQuery(db_path)
    rows = await q.leaderboard(type="messages", limit=10)
    assert len(rows) == 1
    assert rows[0]["trend"] == "down"
    assert rows[0]["this_week"] == 1
    assert rows[0]["last_week"] == 2


# ── /api/status with live provider (status.py 59) ────────────────────────────

async def test_api_status_ollama_online(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    provider = AsyncMock()
    provider.ping = AsyncMock(return_value=True)
    app = create_app(db_path=db_path, status=BackfillStatus(), llm_provider=provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/status")
    assert r.json()["ollama_ok"] is True
