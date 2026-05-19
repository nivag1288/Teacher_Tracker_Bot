from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Message:
    message_id: str
    author_id: str
    author_name: str
    channel_id: str
    channel_name: str
    guild_id: str
    timestamp: str
    content: Optional[str] = None
    word_count: int = 0
    char_count: int = 0
    has_attachment: bool = False
    has_mention: bool = False
    is_reply: bool = False
    reply_to_author_id: Optional[str] = None


@dataclass
class Reaction:
    message_id: str
    channel_id: str
    guild_id: str
    emoji: str
    count: int
    target_author_id: str
    last_updated: str


@dataclass
class Member:
    user_id: str
    user_name: str
    guild_id: str
    event_type: str  # 'join' | 'leave'
    timestamp: str


@dataclass
class BackfillState:
    channel_id: str
    guild_id: str
    last_backfill: str
    newest_message_id: Optional[str] = None


@dataclass
class AnalysisResult:
    channel_id: str
    guild_id: str
    date_from: str
    date_to: str
    created_at: str
    topics: Optional[str] = None   # JSON array string
    sentiment: Optional[str] = None
    summary: Optional[str] = None
    id: Optional[int] = None
