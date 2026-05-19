import pytest
import discord
import aiosqlite
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from tracker.backfill import BackfillEngine, BackfillStatus
from tracker.db import ALL_TABLES


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_mock_author(user_id=1, name="Alice", bot=False):
    author = MagicMock()
    author.id = user_id
    author.display_name = name
    author.bot = bot
    return author


def make_mock_message(
    msg_id=101,
    author_id=1,
    author_name="Alice",
    content="Hello world",
    is_bot=False,
    reference=None,
    attachments=None,
    mentions=None,
    reactions=None,
):
    msg = MagicMock()
    msg.id = msg_id
    msg.author = make_mock_author(author_id, author_name, is_bot)
    msg.content = content
    msg.created_at = _now()
    msg.reference = reference
    msg.attachments = attachments or []
    msg.mentions = mentions or []
    msg.reactions = reactions or []
    return msg


def make_mock_channel(channel_id=1, name="general", guild_id=1, messages=None):
    guild = MagicMock()
    guild.id = guild_id

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.name = name
    channel.guild = guild

    msgs = list(messages or [])

    async def _history(**kwargs):
        after = kwargs.get("after")
        for m in msgs:
            if after and m.id <= after.id:
                continue
            yield m

    channel.history = _history
    return channel


def make_mock_guild(guild_id=1, name="TestServer", channels=None, members=None):
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.name = name
    guild.channels = channels or []
    guild.members = members or []
    guild.member_count = len(guild.members)

    async def _audit_logs(**kwargs):
        return
        yield  # empty async generator

    guild.audit_logs = _audit_logs
    return guild


def make_mock_member(user_id=1, name="Alice", joined_at=None, bot=False):
    member = MagicMock()
    member.id = user_id
    member.display_name = name
    member.bot = bot
    member.joined_at = joined_at or _now()
    return member


@pytest.fixture
async def engine(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as conn:
        for stmt in ALL_TABLES:
            await conn.execute(stmt)
        await conn.commit()
    status = BackfillStatus()
    return BackfillEngine(db_path=db_path, status=status), status, db_path


# ── backfill_channel ─────────────────────────────────────────────────────────

async def test_backfill_channel_inserts_messages(engine):
    eng, status, db_path = engine
    msgs = [make_mock_message(101), make_mock_message(102, content="Hi")]
    channel = make_mock_channel(messages=msgs)

    count = await eng.backfill_channel(channel)

    assert count == 2
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM messages")
        assert (await cursor.fetchone())[0] == 2


async def test_backfill_channel_skips_bots(engine):
    eng, status, db_path = engine
    msgs = [
        make_mock_message(101, is_bot=False),
        make_mock_message(102, is_bot=True),
    ]
    channel = make_mock_channel(messages=msgs)

    count = await eng.backfill_channel(channel)

    assert count == 1
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM messages")
        assert (await cursor.fetchone())[0] == 1


async def test_backfill_channel_upsert_no_duplicate(engine):
    """Second full backfill (backfill_state cleared) updates content without duplicating."""
    eng, status, db_path = engine
    msg = make_mock_message(101, content="original")
    channel = make_mock_channel(messages=[msg])

    await eng.backfill_channel(channel)

    # Clear backfill_state to simulate a forced full re-fetch
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM backfill_state")
        await db.commit()

    msg.content = "updated"
    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM messages")
        assert (await cursor.fetchone())[0] == 1
        cursor = await db.execute("SELECT content FROM messages WHERE message_id = '101'")
        row = await cursor.fetchone()
        assert row[0] == "updated"


async def test_reply_to_author_id_populated(engine):
    eng, status, db_path = engine

    ref_author = make_mock_author(user_id=2, name="Bob")
    resolved = MagicMock()
    resolved.author = ref_author

    reference = MagicMock()
    reference.resolved = resolved

    msg = make_mock_message(101, reference=reference)
    channel = make_mock_channel(messages=[msg])

    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT reply_to_author_id, is_reply FROM messages WHERE message_id = '101'"
        )
        row = await cursor.fetchone()
    assert row[0] == str(ref_author.id)
    assert row[1] == 1


async def test_reply_to_author_id_null_when_not_reply(engine):
    eng, status, db_path = engine
    msg = make_mock_message(101, reference=None)
    channel = make_mock_channel(messages=[msg])

    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT reply_to_author_id, is_reply FROM messages WHERE message_id = '101'"
        )
        row = await cursor.fetchone()
    assert row[0] is None
    assert row[1] == 0


async def test_reply_to_author_id_null_when_reference_unresolved(engine):
    eng, status, db_path = engine
    reference = MagicMock()
    reference.resolved = None

    msg = make_mock_message(101, reference=reference)
    channel = make_mock_channel(messages=[msg])

    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT reply_to_author_id FROM messages WHERE message_id = '101'"
        )
        row = await cursor.fetchone()
    assert row[0] is None


async def test_reactions_snapshotted(engine):
    eng, status, db_path = engine

    reaction = MagicMock()
    reaction.emoji = "👍"
    reaction.count = 5

    msg = make_mock_message(101, reactions=[reaction])
    channel = make_mock_channel(messages=[msg])

    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT emoji, count FROM reactions WHERE message_id = '101'"
        )
        row = await cursor.fetchone()
    assert row[0] == "👍"
    assert row[1] == 5


async def test_reaction_upsert_updates_count(engine):
    eng, status, db_path = engine

    reaction = MagicMock()
    reaction.emoji = "👍"
    reaction.count = 3

    msg = make_mock_message(101, reactions=[reaction])
    channel = make_mock_channel(messages=[msg])
    await eng.backfill_channel(channel)

    # Clear backfill_state to force re-fetch, then update count
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM backfill_state")
        await db.commit()

    reaction.count = 7
    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT count FROM reactions WHERE message_id = '101'")
        row = await cursor.fetchone()
    assert row[0] == 7


async def test_incremental_uses_after_param(engine):
    eng, status, db_path = engine

    msg1 = make_mock_message(100)
    msg2 = make_mock_message(200)
    channel = make_mock_channel(messages=[msg1, msg2])

    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT newest_message_id FROM backfill_state WHERE channel_id = '1'"
        )
        row = await cursor.fetchone()
    assert row[0] == "200"

    # Add a third message — only it should be ingested on second run
    msg3 = make_mock_message(300)
    channel2 = make_mock_channel(messages=[msg1, msg2, msg3])
    count = await eng.backfill_channel(channel2)

    assert count == 1
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM messages")
        assert (await cursor.fetchone())[0] == 3


async def test_backfill_state_updated(engine):
    eng, status, db_path = engine
    msgs = [make_mock_message(101), make_mock_message(102)]
    channel = make_mock_channel(messages=msgs)

    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT newest_message_id FROM backfill_state WHERE channel_id = '1'"
        )
        row = await cursor.fetchone()
    assert row[0] == "102"


async def test_status_messages_ingested(engine):
    eng, status, db_path = engine
    msgs = [make_mock_message(101), make_mock_message(102), make_mock_message(103)]
    channel = make_mock_channel(messages=msgs)

    await eng.backfill_channel(channel)
    assert status.messages_ingested == 3


async def test_word_and_char_counts(engine):
    eng, status, db_path = engine
    msg = make_mock_message(101, content="hello world foo")
    channel = make_mock_channel(messages=[msg])

    await eng.backfill_channel(channel)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT word_count, char_count FROM messages WHERE message_id = '101'"
        )
        row = await cursor.fetchone()
    assert row[0] == 3
    assert row[1] == 15


async def test_empty_channel_creates_backfill_state(engine):
    eng, status, db_path = engine
    channel = make_mock_channel(messages=[])

    count = await eng.backfill_channel(channel)

    assert count == 0
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT newest_message_id FROM backfill_state WHERE channel_id = '1'")
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] is None  # no messages → newest_message_id stays NULL


# ── backfill_members ─────────────────────────────────────────────────────────

async def test_backfill_members_inserts_joins(engine):
    eng, status, db_path = engine
    members = [make_mock_member(1, "Alice"), make_mock_member(2, "Bob")]
    guild = make_mock_guild(members=members)

    count = await eng.backfill_members(guild)

    assert count == 2
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM members WHERE event_type='join'")
        assert (await cursor.fetchone())[0] == 2


async def test_backfill_members_skips_bots(engine):
    eng, status, db_path = engine
    members = [
        make_mock_member(1, "Alice", bot=False),
        make_mock_member(2, "BotUser", bot=True),
    ]
    guild = make_mock_guild(members=members)

    count = await eng.backfill_members(guild)

    assert count == 1


async def test_backfill_members_idempotent(engine):
    eng, status, db_path = engine
    joined = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    members = [make_mock_member(1, "Alice", joined_at=joined)]
    guild = make_mock_guild(members=members)

    await eng.backfill_members(guild)
    await eng.backfill_members(guild)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM members")
        assert (await cursor.fetchone())[0] == 1


async def test_backfill_members_uses_joined_at(engine):
    eng, status, db_path = engine
    joined = datetime(2023, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    members = [make_mock_member(1, "Alice", joined_at=joined)]
    guild = make_mock_guild(members=members)

    await eng.backfill_members(guild)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT timestamp FROM members WHERE user_id = '1'")
        row = await cursor.fetchone()
    assert "2023-06-15" in row[0]


# ── run_all ──────────────────────────────────────────────────────────────────

async def test_run_all_sets_running_false_after_completion(engine):
    eng, status, db_path = engine
    guild = make_mock_guild(channels=[], members=[])

    await eng.run_all(guild)

    assert status.running is False


async def test_run_all_updates_channels_done(engine):
    eng, status, db_path = engine

    c1 = make_mock_channel(1, "general", messages=[])
    c2 = make_mock_channel(2, "random", messages=[])
    guild = make_mock_guild(channels=[c1, c2], members=[])

    with patch.object(eng, "backfill_channel", new=AsyncMock(return_value=1)), \
         patch.object(eng, "backfill_members", new=AsyncMock(return_value=0)):
        await eng.run_all(guild)

    assert status.channels_done == 2
    assert status.channels_total == 2


async def test_run_all_skips_forbidden_channels(engine):
    eng, status, db_path = engine

    async def _raise(*args, **kwargs):
        raise discord.Forbidden(MagicMock(), "no perms")

    c1 = make_mock_channel(1, messages=[])
    guild = make_mock_guild(channels=[c1], members=[])

    with patch.object(eng, "backfill_channel", side_effect=_raise), \
         patch.object(eng, "backfill_members", new=AsyncMock(return_value=0)):
        await eng.run_all(guild)

    assert status.channels_done == 1


# ── BackfillStatus ────────────────────────────────────────────────────────────

def test_backfill_status_defaults():
    s = BackfillStatus()
    assert s.running is False
    assert s.channels_done == 0
    assert s.channels_total == 0
    assert s.messages_ingested == 0
