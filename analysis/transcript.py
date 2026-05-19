import aiosqlite
from pathlib import Path
from datetime import datetime


class TranscriptBuilder:
    def __init__(self, db_path: str, transcripts_dir: Path):
        self.db_path = db_path
        self.transcripts_dir = Path(transcripts_dir)

    async def build(
        self, channel_id: str, guild_id: str, date_from: str, date_to: str
    ) -> Path:
        """Query messages in date range, write formatted transcript, return path."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT timestamp, author_name, content FROM messages "
                "WHERE channel_id = ? AND guild_id = ? "
                "  AND date(timestamp) >= ? AND date(timestamp) <= ? "
                "ORDER BY timestamp ASC",
                [channel_id, guild_id, date_from, date_to],
            )
            rows = await cur.fetchall()

        lines = []
        for ts, author, content in rows:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                label = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                label = ts[:16] if ts else "unknown"
            lines.append(f"[{label}] {author}: {content or ''}")

        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{guild_id}_{channel_id}_{date_from}_{date_to}.txt"
        path = self.transcripts_dir / filename
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def list_transcripts(self) -> list[dict]:
        """Return metadata for all saved transcript files."""
        if not self.transcripts_dir.exists():
            return []
        result = []
        for f in sorted(self.transcripts_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
            parts = f.stem.split("_", 3)
            result.append({
                "filename": f.name,
                "guild_id": parts[0] if len(parts) > 0 else "",
                "channel_id": parts[1] if len(parts) > 1 else "",
                "date_from": parts[2] if len(parts) > 2 else "",
                "date_to": parts[3] if len(parts) > 3 else "",
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        return result
