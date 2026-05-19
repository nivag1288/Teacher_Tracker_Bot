import aiosqlite
from dataclasses import dataclass
from typing import Optional


@dataclass
class Scope:
    mode: str  # 'server' | 'channel' | 'user'
    channel_id: Optional[str] = None
    user_id: Optional[str] = None

    def msg_where(self) -> tuple[str, list]:
        """WHERE clause and params for the messages table."""
        if self.mode == "channel" and self.channel_id:
            return "WHERE channel_id = ?", [self.channel_id]
        if self.mode == "user" and self.user_id:
            return "WHERE author_id = ?", [self.user_id]
        return "", []

    def reaction_where(self) -> tuple[str, list]:
        """WHERE clause and params for the reactions table."""
        if self.mode == "channel" and self.channel_id:
            return "WHERE channel_id = ?", [self.channel_id]
        if self.mode == "user" and self.user_id:
            return "WHERE target_author_id = ?", [self.user_id]
        return "", []

    def _and(self, base_where: str, extra: str) -> str:
        return f"{base_where} AND {extra}" if base_where else f"WHERE {extra}"


class StatsQuery:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def messages_count(self, scope: Scope) -> int:
        where, params = scope.msg_where()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(f"SELECT COUNT(*) FROM messages {where}", params)
            return (await cur.fetchone())[0]

    async def unique_users(self, scope: Scope) -> int:
        if scope.mode == "user":
            return 1 if scope.user_id else 0
        where, params = scope.msg_where()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT COUNT(DISTINCT author_id) FROM messages {where}", params
            )
            return (await cur.fetchone())[0]

    async def channels_tracked(self, scope: Scope) -> int:
        if scope.mode == "channel":
            return 1 if scope.channel_id else 0
        where, params = scope.msg_where()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT COUNT(DISTINCT channel_id) FROM messages {where}", params
            )
            return (await cur.fetchone())[0]

    async def messages_today(self, scope: Scope) -> int:
        where, params = scope.msg_where()
        clause = scope._and(where, "date(timestamp) = date('now')")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(f"SELECT COUNT(*) FROM messages {clause}", params)
            return (await cur.fetchone())[0]

    async def messages_this_week(self, scope: Scope) -> int:
        where, params = scope.msg_where()
        clause = scope._and(where, "timestamp >= datetime('now', '-7 days')")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(f"SELECT COUNT(*) FROM messages {clause}", params)
            return (await cur.fetchone())[0]

    async def top_users(self, scope: Scope, limit: int = 5) -> list[dict]:
        where, params = scope.msg_where()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT author_id, author_name, COUNT(*) as cnt FROM messages {where} "
                f"GROUP BY author_id ORDER BY cnt DESC LIMIT ?",
                params + [limit],
            )
            rows = await cur.fetchall()
        return [{"author_id": r[0], "author_name": r[1], "count": r[2]} for r in rows]

    async def top_channels(self, scope: Scope, limit: int = 5) -> list[dict]:
        where, params = scope.msg_where()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT channel_id, channel_name, COUNT(*) as cnt FROM messages {where} "
                f"GROUP BY channel_id ORDER BY cnt DESC LIMIT ?",
                params + [limit],
            )
            rows = await cur.fetchall()
        return [{"channel_id": r[0], "channel_name": r[1], "count": r[2]} for r in rows]

    async def reaction_totals(self, scope: Scope) -> int:
        where, params = scope.reaction_where()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT COALESCE(SUM(count), 0) FROM reactions {where}", params
            )
            return (await cur.fetchone())[0]

    async def daily_trend(self, scope: Scope, days: int = 30) -> list[dict]:
        where, params = scope.msg_where()
        clause = scope._and(where, f"timestamp >= datetime('now', '-{days} days')")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT date(timestamp) as day, COUNT(*) as cnt FROM messages {clause} "
                f"GROUP BY day ORDER BY day",
                params,
            )
            rows = await cur.fetchall()
        return [{"date": r[0], "count": r[1]} for r in rows]

    async def active_hours(self, scope: Scope) -> list[dict]:
        where, params = scope.msg_where()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT CAST(strftime('%H', timestamp) AS INTEGER) as hour, "
                f"CAST(strftime('%w', timestamp) AS INTEGER) as weekday, "
                f"COUNT(*) as cnt FROM messages {where} GROUP BY hour, weekday",
                params,
            )
            rows = await cur.fetchall()
        return [{"hour": r[0], "weekday": r[1], "count": r[2]} for r in rows]

    async def recent_member_events(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT user_name, event_type, timestamp FROM members "
                "ORDER BY timestamp DESC LIMIT ?",
                [limit],
            )
            rows = await cur.fetchall()
        return [{"user_name": r[0], "event_type": r[1], "timestamp": r[2]} for r in rows]

    async def backfill_timestamps(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT b.channel_id, m.channel_name, b.last_backfill "
                "FROM backfill_state b "
                "LEFT JOIN (SELECT DISTINCT channel_id, channel_name FROM messages) m "
                "  ON b.channel_id = m.channel_id "
                "ORDER BY b.last_backfill DESC"
            )
            rows = await cur.fetchall()
        return [
            {"channel_id": r[0], "channel_name": r[1] or r[0], "last_backfill": r[2]}
            for r in rows
        ]

    async def all_channels(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT DISTINCT channel_id, channel_name FROM messages ORDER BY channel_name"
            )
            rows = await cur.fetchall()
        return [{"channel_id": r[0], "channel_name": r[1]} for r in rows]

    async def all_users(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT DISTINCT author_id, author_name FROM messages ORDER BY author_name"
            )
            rows = await cur.fetchall()
        return [{"author_id": r[0], "author_name": r[1]} for r in rows]
