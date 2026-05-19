import discord
import aiosqlite
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class BackfillStatus:
    running: bool = False
    channels_done: int = 0
    channels_total: int = 0
    messages_ingested: int = 0


class BackfillEngine:
    def __init__(self, db_path: str, status: BackfillStatus):
        self.db_path = db_path
        self.status = status

    async def _get_after_snowflake(self, channel_id: str) -> Optional[discord.Object]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT newest_message_id FROM backfill_state WHERE channel_id = ?",
                (channel_id,),
            )
            row = await cursor.fetchone()
        if row and row[0]:
            return discord.Object(id=int(row[0]))
        return None

    async def backfill_channel(self, channel: discord.TextChannel) -> int:
        """Fetch all messages from channel, upsert into DB. Returns count ingested."""
        after = await self._get_after_snowflake(str(channel.id))
        guild_id = str(channel.guild.id)
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        newest_id: Optional[str] = None

        history_kwargs: dict = {"limit": None, "oldest_first": True}
        if after:
            history_kwargs["after"] = after

        async with aiosqlite.connect(self.db_path) as db:
            async for msg in channel.history(**history_kwargs):
                if msg.author.bot:
                    continue

                reply_to_author_id = None
                if msg.reference and msg.reference.resolved:
                    ref = msg.reference.resolved
                    if hasattr(ref, "author") and ref.author:
                        reply_to_author_id = str(ref.author.id)

                words = msg.content.split() if msg.content else []
                await db.execute(
                    """INSERT INTO messages (
                        message_id, author_id, author_name, channel_id, channel_name,
                        guild_id, timestamp, content, word_count, char_count,
                        has_attachment, has_mention, is_reply, reply_to_author_id
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(message_id) DO UPDATE SET
                        content=excluded.content,
                        word_count=excluded.word_count,
                        char_count=excluded.char_count""",
                    (
                        str(msg.id),
                        str(msg.author.id),
                        msg.author.display_name,
                        str(channel.id),
                        channel.name,
                        guild_id,
                        msg.created_at.isoformat(),
                        msg.content,
                        len(words),
                        len(msg.content) if msg.content else 0,
                        int(bool(msg.attachments)),
                        int(bool(msg.mentions)),
                        int(msg.reference is not None),
                        reply_to_author_id,
                    ),
                )

                for reaction in msg.reactions:
                    await db.execute(
                        """INSERT INTO reactions (
                            message_id, channel_id, guild_id, emoji, count,
                            target_author_id, last_updated
                        ) VALUES (?,?,?,?,?,?,?)
                        ON CONFLICT(message_id, emoji) DO UPDATE SET
                            count=excluded.count,
                            last_updated=excluded.last_updated""",
                        (
                            str(msg.id),
                            str(channel.id),
                            guild_id,
                            str(reaction.emoji),
                            reaction.count,
                            str(msg.author.id),
                            now,
                        ),
                    )

                newest_id = str(msg.id)
                count += 1

            await db.execute(
                """INSERT INTO backfill_state (channel_id, guild_id, newest_message_id, last_backfill)
                VALUES (?,?,?,?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    newest_message_id=COALESCE(excluded.newest_message_id, backfill_state.newest_message_id),
                    last_backfill=excluded.last_backfill""",
                (str(channel.id), guild_id, newest_id, now),
            )
            await db.commit()

        self.status.messages_ingested += count
        return count

    async def backfill_members(self, guild: discord.Guild) -> int:
        """Store join events for current members using their joined_at timestamp.
        Also records kicks and bans from the audit log as leave events."""
        now = datetime.now(timezone.utc).isoformat()
        count = 0

        async with aiosqlite.connect(self.db_path) as db:
            for member in guild.members:
                if member.bot:
                    continue
                ts = member.joined_at.isoformat() if member.joined_at else now
                await db.execute(
                    """INSERT OR IGNORE INTO members
                        (user_id, user_name, guild_id, event_type, timestamp)
                    VALUES (?,?,?,?,?)""",
                    (str(member.id), member.display_name, str(guild.id), "join", ts),
                )
                count += 1

            leave_actions = {discord.AuditLogAction.kick, discord.AuditLogAction.ban}
            async for entry in guild.audit_logs(limit=None):
                if entry.action not in leave_actions:
                    continue
                target = entry.target
                if target is None or (hasattr(target, "bot") and target.bot):
                    continue
                ts = entry.created_at.isoformat() if entry.created_at else now
                await db.execute(
                    """INSERT OR IGNORE INTO members
                        (user_id, user_name, guild_id, event_type, timestamp)
                    VALUES (?,?,?,?,?)""",
                    (
                        str(target.id),
                        getattr(target, "display_name", str(target.id)),
                        str(guild.id),
                        "leave",
                        ts,
                    ),
                )

            await db.commit()

        return count

    async def run_all(self, guild: discord.Guild) -> None:
        """Backfill all readable text channels then member list."""
        self.status.running = True
        self.status.channels_done = 0
        self.status.messages_ingested = 0

        text_channels = [
            c for c in guild.channels if isinstance(c, discord.TextChannel)
        ]
        self.status.channels_total = len(text_channels)

        for channel in text_channels:
            try:
                await self.backfill_channel(channel)
            except discord.Forbidden:
                pass
            self.status.channels_done += 1

        await self.backfill_members(guild)
        self.status.running = False
