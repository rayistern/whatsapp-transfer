"""Neutral domain model sitting between iOS parsing and Android emission.

Populated in Phase 1 (from ZWAMESSAGE etc.) and consumed in Phase 3+ to write
into the modern Android msgstore schema. Kept intentionally flat — no ORM,
no validation framework — so the converter stays inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Jid:
    raw: str              # e.g. "14155551234@s.whatsapp.net"
    user: str             # "14155551234"
    server: str           # "s.whatsapp.net" | "g.us" | "broadcast" | "status"


@dataclass
class Chat:
    pk: int               # iOS Z_PK, used as stable id during conversion
    partner_jid: str
    partner_name: str | None
    is_group: bool
    last_message_ts_ios: float | None  # Core Data seconds


@dataclass
class Media:
    local_path: str | None        # iOS relative path (Message/Media/...)
    mime_type: str | None         # from ZVCARDSTRING (misnamed on iOS)
    media_key: bytes | None
    file_size: int | None
    width: int | None
    height: int | None
    duration: int | None
    latitude: float | None
    longitude: float | None
    title: str | None


@dataclass
class Message:
    pk: int
    chat_pk: int
    stanza_id: str | None
    from_me: bool
    ios_type: int
    ios_timestamp: float           # seconds since 2001-01-01
    sort: int | None
    text: str | None
    from_jid: str | None
    to_jid: str | None
    starred: bool = False
    media: Media | None = None
    quoted_stanza_id: str | None = None


@dataclass
class GroupMember:
    chat_pk: int
    member_jid: str
    display_name: str | None


@dataclass
class Corpus:
    """Everything parsed out of ChatStorage.sqlite in one container."""
    chats: list[Chat] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    group_members: list[GroupMember] = field(default_factory=list)
    push_names: dict[str, str] = field(default_factory=dict)  # jid -> display name
