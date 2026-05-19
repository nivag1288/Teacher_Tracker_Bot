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

    async def user_summary(self, user_id: str) -> Optional[dict]:
        """First/last seen timestamps and display name for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT author_name, MIN(timestamp), MAX(timestamp) "
                "FROM messages WHERE author_id = ? GROUP BY author_id",
                [user_id],
            )
            row = await cur.fetchone()
        if not row:
            return None
        return {"author_name": row[0], "first_seen": row[1], "last_seen": row[2]}

    async def user_list(self) -> list[dict]:
        """All users with message count, reactions received, first/last seen."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT m.author_id, m.author_name, COUNT(m.id) as msg_count, "
                "  MIN(m.timestamp) as first_seen, MAX(m.timestamp) as last_seen, "
                "  COALESCE(SUM(r.count), 0) as reactions "
                "FROM messages m "
                "LEFT JOIN reactions r ON r.target_author_id = m.author_id "
                "GROUP BY m.author_id ORDER BY msg_count DESC"
            )
            rows = await cur.fetchall()
        return [
            {
                "author_id": r[0],
                "author_name": r[1],
                "msg_count": r[2],
                "first_seen": r[3],
                "last_seen": r[4],
                "reactions": r[5],
            }
            for r in rows
        ]

    async def most_reacted_messages(self, scope: Scope, limit: int = 5) -> list[dict]:
        """Messages with the most reactions, optionally scoped."""
        if scope.mode == "channel" and scope.channel_id:
            where, params = "WHERE m.channel_id = ?", [scope.channel_id]
        elif scope.mode == "user" and scope.user_id:
            where, params = "WHERE m.author_id = ?", [scope.user_id]
        else:
            where, params = "", []
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT m.message_id, m.author_name, m.channel_name, m.content, "
                f"COALESCE(SUM(r.count), 0) as total_reactions "
                f"FROM messages m LEFT JOIN reactions r ON r.message_id = m.message_id "
                f"{where} "
                f"GROUP BY m.message_id ORDER BY total_reactions DESC LIMIT ?",
                params + [limit],
            )
            rows = await cur.fetchall()
        return [
            {
                "message_id": r[0],
                "author_name": r[1],
                "channel_name": r[2],
                "content": r[3],
                "reactions": r[4],
            }
            for r in rows
        ]

    async def channel_summary(self, channel_id: str) -> Optional[dict]:
        """Name and unique author count for a channel."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT channel_name, COUNT(DISTINCT author_id) "
                "FROM messages WHERE channel_id = ? GROUP BY channel_id",
                [channel_id],
            )
            row = await cur.fetchone()
        if not row:
            return None
        return {"channel_name": row[0], "unique_authors": row[1]}

    async def channel_list(self) -> list[dict]:
        """All channels with message count and unique author count."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT channel_id, channel_name, COUNT(*) as msg_count, "
                "COUNT(DISTINCT author_id) as unique_authors "
                "FROM messages GROUP BY channel_id ORDER BY msg_count DESC"
            )
            rows = await cur.fetchall()
        return [
            {
                "channel_id": r[0],
                "channel_name": r[1],
                "msg_count": r[2],
                "unique_authors": r[3],
            }
            for r in rows
        ]

    async def leaderboard(self, type: str = "messages", limit: int = 25) -> list[dict]:
        """Ranked leaderboard with this-week vs last-week trend."""
        async with aiosqlite.connect(self.db_path) as db:
            if type == "messages":
                sql = """
                    SELECT author_id, author_name,
                        COUNT(*) as total,
                        SUM(CASE WHEN timestamp >= datetime('now','-7 days') THEN 1 ELSE 0 END) as this_week,
                        SUM(CASE WHEN timestamp >= datetime('now','-14 days')
                                  AND timestamp < datetime('now','-7 days') THEN 1 ELSE 0 END) as last_week
                    FROM messages
                    GROUP BY author_id ORDER BY total DESC LIMIT ?
                """
                params = [limit]
            elif type == "reactions":
                sql = """
                    SELECT r.target_author_id as author_id,
                        COALESCE(m.author_name, r.target_author_id) as author_name,
                        SUM(r.count) as total,
                        0 as this_week, 0 as last_week
                    FROM reactions r
                    LEFT JOIN (SELECT DISTINCT author_id, author_name FROM messages) m
                        ON m.author_id = r.target_author_id
                    GROUP BY r.target_author_id ORDER BY total DESC LIMIT ?
                """
                params = [limit]
            elif type == "replies_sent":
                sql = """
                    SELECT author_id, author_name,
                        COUNT(*) as total,
                        SUM(CASE WHEN timestamp >= datetime('now','-7 days') THEN 1 ELSE 0 END) as this_week,
                        SUM(CASE WHEN timestamp >= datetime('now','-14 days')
                                  AND timestamp < datetime('now','-7 days') THEN 1 ELSE 0 END) as last_week
                    FROM messages WHERE is_reply = 1
                    GROUP BY author_id ORDER BY total DESC LIMIT ?
                """
                params = [limit]
            elif type == "replies_received":
                sql = """
                    SELECT reply_to_author_id as author_id,
                        MAX(author_name) as author_name,
                        COUNT(*) as total,
                        SUM(CASE WHEN timestamp >= datetime('now','-7 days') THEN 1 ELSE 0 END) as this_week,
                        SUM(CASE WHEN timestamp >= datetime('now','-14 days')
                                  AND timestamp < datetime('now','-7 days') THEN 1 ELSE 0 END) as last_week
                    FROM messages
                    WHERE reply_to_author_id IS NOT NULL
                    GROUP BY reply_to_author_id ORDER BY total DESC LIMIT ?
                """
                params = [limit]
            else:
                return []

            cur = await db.execute(sql, params)
            rows = await cur.fetchall()

        result = []
        for i, r in enumerate(rows, 1):
            this_week = r[3]
            last_week = r[4]
            if last_week == 0 and this_week > 0:
                trend = "up"
            elif this_week == 0 and last_week > 0:
                trend = "down"
            elif this_week > last_week:
                trend = "up"
            elif this_week < last_week:
                trend = "down"
            else:
                trend = "flat"
            result.append({
                "rank": i,
                "author_id": r[0],
                "author_name": r[1],
                "total": r[2],
                "this_week": this_week,
                "last_week": last_week,
                "trend": trend,
            })
        return result
