import pytest
import aiosqlite
from pathlib import Path
from datetime import datetime, timezone

from tracker.db import ALL_TABLES
from analysis.transcript import TranscriptBuilder


@pytest.fixture
async def setup(tmp_path):
    db_path = str(tmp_path / "test.db")
    transcripts_dir = tmp_path / "transcripts"
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        # Two messages in channel c1
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m1','u1','Alice','c1','general','g1','2024-03-10T14:32:00','Hello world',2,11)"
        )
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m2','u2','Bob','c1','general','g1','2024-03-10T15:00:00','Hey there',2,9)"
        )
        # One message in a different channel
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m3','u1','Alice','c2','random','g1','2024-03-10T16:00:00','Off topic',2,9)"
        )
        # One message outside date range
        await db.execute(
            "INSERT INTO messages (message_id,author_id,author_name,channel_id,channel_name,guild_id,timestamp,content,word_count,char_count) "
            "VALUES ('m4','u1','Alice','c1','general','g1','2024-03-05T10:00:00','Old message',2,11)"
        )
        await db.commit()
    builder = TranscriptBuilder(db_path, transcripts_dir)
    return builder, transcripts_dir, db_path


# ── build ─────────────────────────────────────────────────────────────────────

async def test_build_returns_path(setup):
    builder, transcripts_dir, _ = setup
    path = await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    assert isinstance(path, Path)
    assert path.exists()


async def test_build_creates_file_in_transcripts_dir(setup):
    builder, transcripts_dir, _ = setup
    path = await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    assert path.parent == transcripts_dir


async def test_build_filename_contains_channel_and_dates(setup):
    builder, _, _ = setup
    path = await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    assert "c1" in path.name
    assert "2024-03-10" in path.name


async def test_build_content_format(setup):
    builder, _, _ = setup
    path = await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    # Format: [YYYY-MM-DD HH:MM] username: content
    assert lines[0].startswith("[2024-03-10 14:32]")
    assert "Alice" in lines[0]
    assert "Hello world" in lines[0]


async def test_build_second_message_in_order(setup):
    builder, _, _ = setup
    path = await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "Bob" in lines[1]
    assert "Hey there" in lines[1]


async def test_build_filters_by_channel(setup):
    builder, _, _ = setup
    path = await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    content = path.read_text(encoding="utf-8")
    assert "Off topic" not in content


async def test_build_filters_by_date_range(setup):
    builder, _, _ = setup
    path = await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    content = path.read_text(encoding="utf-8")
    assert "Old message" not in content


async def test_build_empty_channel_creates_empty_file(setup):
    builder, _, _ = setup
    path = await builder.build("nonexistent", "g1", "2024-03-10", "2024-03-10")
    assert path.exists()
    assert path.read_text(encoding="utf-8") == ""


async def test_build_creates_transcripts_dir(tmp_path):
    db_path = str(tmp_path / "test.db")
    transcripts_dir = tmp_path / "new_transcripts_dir"
    async with aiosqlite.connect(db_path) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
    builder = TranscriptBuilder(db_path, transcripts_dir)
    await builder.build("c1", "g1", "2024-01-01", "2024-01-01")
    assert transcripts_dir.exists()


# ── list_transcripts ──────────────────────────────────────────────────────────

async def test_list_transcripts_empty_when_no_files(setup):
    builder, _, _ = setup
    assert builder.list_transcripts() == []


async def test_list_transcripts_returns_entry_after_build(setup):
    builder, _, _ = setup
    await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    items = builder.list_transcripts()
    assert len(items) == 1


async def test_list_transcripts_metadata(setup):
    builder, _, _ = setup
    await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    item = builder.list_transcripts()[0]
    assert item["channel_id"] == "c1"
    assert item["date_from"] == "2024-03-10"
    assert item["date_to"] == "2024-03-10"
    assert "filename" in item
    assert "size_kb" in item


async def test_list_transcripts_multiple_files(setup):
    builder, _, _ = setup
    await builder.build("c1", "g1", "2024-03-10", "2024-03-10")
    await builder.build("c2", "g1", "2024-03-11", "2024-03-12")
    items = builder.list_transcripts()
    assert len(items) == 2


async def test_list_transcripts_nonexistent_dir(tmp_path):
    db_path = str(tmp_path / "test.db")
    builder = TranscriptBuilder(db_path, tmp_path / "missing")
    assert builder.list_transcripts() == []
