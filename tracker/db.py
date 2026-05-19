import os
import aiosqlite

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE NOT NULL,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    content TEXT,
    word_count INTEGER DEFAULT 0,
    char_count INTEGER DEFAULT 0,
    has_attachment BOOLEAN DEFAULT 0,
    has_mention BOOLEAN DEFAULT 0,
    is_reply BOOLEAN DEFAULT 0,
    reply_to_author_id TEXT
)
"""

CREATE_REACTIONS = """
CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    emoji TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    target_author_id TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    UNIQUE(message_id, emoji)
)
"""

CREATE_MEMBERS = """
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    UNIQUE(user_id, guild_id, event_type, timestamp)
)
"""

CREATE_BACKFILL_STATE = """
CREATE TABLE IF NOT EXISTS backfill_state (
    channel_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    newest_message_id TEXT,
    last_backfill TEXT NOT NULL
)
"""

CREATE_ANALYSIS_RESULTS = """
CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    topics TEXT,
    sentiment TEXT,
    summary TEXT,
    created_at TEXT NOT NULL
)
"""

ALL_TABLES = [
    CREATE_MESSAGES,
    CREATE_REACTIONS,
    CREATE_MEMBERS,
    CREATE_BACKFILL_STATE,
    CREATE_ANALYSIS_RESULTS,
]


async def create_tables(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()


def connect(db_path: str) -> aiosqlite.Connection:
    """Return an aiosqlite connection context manager for the given DB path."""
    return aiosqlite.connect(db_path)
