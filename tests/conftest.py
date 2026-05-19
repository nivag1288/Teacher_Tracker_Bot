import pytest
import aiosqlite
from tracker.db import ALL_TABLES
from tracker.models import Message, Reaction, Member, BackfillState, AnalysisResult


@pytest.fixture
async def db():
    """In-memory SQLite database with all tables created."""
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        for stmt in ALL_TABLES:
            await conn.execute(stmt)
        await conn.commit()
        yield conn


def make_message(**kwargs) -> Message:
    defaults = dict(
        message_id="msg_001",
        author_id="user_1",
        author_name="Alice",
        channel_id="chan_1",
        channel_name="general",
        guild_id="guild_1",
        timestamp="2024-01-15T14:32:00",
        content="Hello world",
        word_count=2,
        char_count=11,
        has_attachment=False,
        has_mention=False,
        is_reply=False,
        reply_to_author_id=None,
    )
    defaults.update(kwargs)
    return Message(**defaults)


def make_reaction(**kwargs) -> Reaction:
    defaults = dict(
        message_id="msg_001",
        channel_id="chan_1",
        guild_id="guild_1",
        emoji="👍",
        count=3,
        target_author_id="user_1",
        last_updated="2024-01-15T15:00:00",
    )
    defaults.update(kwargs)
    return Reaction(**defaults)


def make_member(**kwargs) -> Member:
    defaults = dict(
        user_id="user_1",
        user_name="Alice",
        guild_id="guild_1",
        event_type="join",
        timestamp="2024-01-01T00:00:00",
    )
    defaults.update(kwargs)
    return Member(**defaults)
