"""Neutral domain model sitting between iOS parsing and Android emission.

Populated in Phase 1 (from ZWAMESSAGE etc.) and consumed in Phase 3+ to write
into the modern Android msgstore schema. Kept intentionally flat — no ORM,
no validation framework — so the converter stays inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Jid:
    """A parsed WhatsApp JID (Jabber ID), split into user and server parts.

    Populated during Phase 1 (iOS extraction) when reading any JID column
    from ChatStorage.sqlite (e.g. ZCONTACTJID, ZFROMJID, ZMEMBERJID).

    Design decisions (decided during Phase 0 spec, April 2025):
    - We keep the raw string alongside the split parts so that downstream
      code can use whichever form is convenient without re-joining.
    - The server component disambiguates contact type: "s.whatsapp.net"
      for 1:1 chats, "g.us" for groups, "broadcast" for broadcast lists,
      "status" for Status updates. This avoids a separate enum.
    """
    raw: str              # e.g. "14155551234@s.whatsapp.net"
    user: str             # "14155551234"
    server: str           # "s.whatsapp.net" | "g.us" | "broadcast" | "status"


@dataclass
class Chat:
    """A single WhatsApp chat session (1:1 or group).

    Populated during Phase 1 (iOS extraction) from ZWACHATSESSION rows.
    Consumed during Phase 2+ (Android conversion) to create rows in the
    Android ``chat`` table and to resolve message -> chat associations.

    Design decisions (decided during Phase 0 spec, April 2025):
    - pk stores the iOS Z_PK directly. This serves as a stable join key
      between Chat and Message during conversion, avoiding a separate ID
      mapping until we actually write to Android.
    - is_group is derived from the presence of ZGROUPINFO (not NULL means
      group). This is more reliable than checking the JID server suffix
      because some edge-case JIDs can be misleading.
    - last_message_ts_ios is kept in Core Data epoch (seconds since
      2001-01-01) to stay lossless; conversion to Android millis-since-
      1970 happens in convert/mappings.py at write time.
    """
    pk: int               # iOS Z_PK, used as stable id during conversion
    partner_jid: str
    partner_name: str | None
    is_group: bool
    last_message_ts_ios: float | None  # Core Data seconds


@dataclass
class Media:
    """Metadata for a media attachment (image, video, audio, document, etc.).

    Populated during Phase 1 (iOS extraction) from ZWAMEDIAITEM rows,
    linked to Message via the ZMEDIAITEM foreign key on ZWAMESSAGE.
    Consumed during Phase 2+ (Android conversion) to populate the
    ``message_media`` and ``message_location`` satellite tables.

    Design decisions (decided during Phase 0 spec, April 2025):
    - mime_type comes from the iOS column ZVCARDSTRING, which is confusingly
      named — Apple reused a vCard column to store the MIME type. This is
      documented in research/02-db-schemas.md.
    - latitude/longitude are overloaded in the iOS schema: for location
      messages (type 5) they hold actual GPS coordinates; for images they
      may hold pixel dimensions. We store them as-is and let the converter
      decide how to interpret them based on ios_type.
    - width/height are None because the iOS schema version we target does
      not expose these directly; they could be derived from latitude/longitude
      for image messages, but we leave that to the converter.
    - media_key is the E2E encryption key blob from iOS; kept for potential
      future re-encryption but not used in the current pipeline.
    """
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
    """A single WhatsApp message in platform-neutral form.

    Populated during Phase 1 (iOS extraction) from ZWAMESSAGE rows.
    Consumed during Phase 2+ (Android conversion) to write into the
    modern msgstore.db ``message`` table plus satellite tables
    (message_media, message_location, message_quoted, message_system).

    Design decisions (decided during Phase 0 spec, April 2025):
    - ios_type and ios_timestamp are kept in iOS-native format here;
      conversion to Android format happens in convert/mappings.py.
      This keeps the domain model lossless — we can always re-derive.
    - media is optional (None for text-only messages). When present,
      it's populated from ZWAMEDIAITEM via the ZMEDIAITEM foreign key
      on ZWAMESSAGE (not by message PK — see extract/__init__.py).
    - quoted_stanza_id stores the stanza_id of the replied-to message
      (if any). The actual quoted text is resolved during conversion
      by looking up the stanza_id in the message corpus.
    - sort comes from iOS ZSORT column and is mapped directly to
      Android sort_id. This preserves the original ordering even when
      timestamps collide (e.g. rapid-fire messages in the same second).
    - from_jid / to_jid are raw JID strings. In group chats from_jid
      identifies the sender; in 1:1 chats it may be None for outgoing.
    """
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
    """A participant in a WhatsApp group chat.

    Populated during Phase 1 (iOS extraction) from ZWAGROUPMEMBER rows.
    Consumed during Phase 2+ (Android conversion) to populate the
    ``group_participants`` table, linking each member's JID to their
    group chat's JID.

    Design decisions (decided during Phase 0 spec, April 2025):
    - chat_pk references the iOS Z_PK of the group's ZWACHATSESSION,
      allowing us to look up the group's JID via the Chat -> Jid mapping
      at conversion time.
    - display_name comes from ZCONTACTNAME on iOS; it may be None if
      the contact is not in the address book.
    """
    chat_pk: int
    member_jid: str
    display_name: str | None


@dataclass
class Corpus:
    """Everything parsed out of ChatStorage.sqlite in one container.

    Populated during Phase 1 (iOS extraction) by parse_ios_db() in
    extract/__init__.py. Consumed during Phase 2+ (Android conversion)
    by convert_corpus() in convert/writer.py.

    Design decisions (decided during Phase 0 spec, April 2025):
    - Kept intentionally flat — four parallel lists/dicts rather than
      a nested object graph. This makes the converter simpler: it can
      iterate each list independently and build Android rows with plain
      dict lookups, avoiding ORM complexity or recursive traversal.
    - No ORM or validation framework on purpose: the intermediate model
      is a plain data shuttle between two SQLite schemas. Keeping it as
      raw dataclasses means the converter stays inspectable and testable
      without mocking an ORM session.
    - push_names (jid -> display name) is stored separately from Chats
      because push names come from ZWAPROFILEPUSHNAME, a separate iOS
      table that maps JIDs to user-chosen display names. These can be
      used as fallback display names during Android import.
    """
    chats: list[Chat] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    group_members: list[GroupMember] = field(default_factory=list)
    push_names: dict[str, str] = field(default_factory=dict)  # jid -> display name
