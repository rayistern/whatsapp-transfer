"""Convert a neutral Corpus into a modern Android msgstore.db."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from wat.model import Corpus, Chat, Message, GroupMember
from wat.convert.android_schema import create_android_db
from wat.convert.mappings import (
    IOS_TO_ANDROID_MESSAGE_TYPE,
    android_status,
    ios_ts_to_android_ms,
)
from wat.convert.media import MediaRemapper


def _split_jid(raw: str) -> tuple[str, str]:
    """Split 'user@server' into (user, server).  Bare strings get server=''."""
    if "@" in raw:
        user, server = raw.split("@", 1)
        return user, server
    return raw, ""


class _JidCache:
    """Deduplicates JIDs and caches their row IDs from the Android ``jid`` table.

    Many messages and chats reference the same JID (e.g. every message in a
    1:1 chat shares the partner JID). Without deduplication we'd attempt
    thousands of redundant INSERT + SELECT round-trips. This cache ensures
    each unique JID string is inserted and looked up exactly once.

    Strategy:
    - On first encounter of a raw JID, split it into (user, server) and
      INSERT OR IGNORE into the jid table. The OR IGNORE handles the
      UNIQUE(user, server) constraint so we don't need to pre-check.
    - Immediately SELECT back the _id (which may have been auto-assigned
      on this insert, or may already exist from a prior run).
    - Cache the raw_jid -> _id mapping in a Python dict for O(1) lookups
      on subsequent hits.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._cache: dict[str, int] = {}  # raw jid -> row_id

    def get_or_insert(self, raw_jid: str) -> int:
        """Return the jid._id for *raw_jid*, inserting if needed.

        Returns 0 for empty/None JIDs (Android convention: row_id 0
        means "no JID" / "self").
        """
        if not raw_jid:
            return 0
        if raw_jid in self._cache:
            return self._cache[raw_jid]
        user, server = _split_jid(raw_jid)
        # INSERT OR IGNORE: the jid table has a UNIQUE(user, server) constraint.
        # Using OR IGNORE avoids raising on duplicates while remaining idempotent.
        # This is preferred over INSERT-or-SELECT-first because it's a single
        # statement and handles concurrent/re-run scenarios cleanly.
        self._conn.execute(
            "INSERT OR IGNORE INTO jid (user, server) VALUES (?, ?)",
            (user, server),
        )
        row = self._conn.execute(
            "SELECT _id FROM jid WHERE user = ? AND server = ?",
            (user, server),
        ).fetchone()
        row_id: int = row[0]
        self._cache[raw_jid] = row_id
        return row_id


def _insert_chats(
    conn: sqlite3.Connection,
    chats: list[Chat],
    jid_cache: _JidCache,
) -> dict[int, int]:
    """Insert chats into Android ``chat`` table, returning iOS pk -> Android _id map.

    JID normalization: each chat's partner_jid is split into (user, server)
    and upserted via _JidCache. The resulting jid row_id is stored as
    chat.jid_row_id, which is the Android schema's canonical way to
    reference a conversation partner. This normalisation means the same
    phone number appearing in multiple contexts (1:1 chat, group member)
    always resolves to a single jid row.

    For group chats, the subject (group name) is stored in chat.subject.
    For 1:1 chats, subject is NULL — Android infers the display name from
    the contacts database or push_name at render time.
    """
    pk_map: dict[int, int] = {}
    for chat in chats:
        jid_row_id = jid_cache.get_or_insert(chat.partner_jid)
        sort_ts = (
            ios_ts_to_android_ms(chat.last_message_ts_ios)
            if chat.last_message_ts_ios is not None
            else None
        )
        cur = conn.execute(
            "INSERT INTO chat (jid_row_id, subject, sort_timestamp) VALUES (?, ?, ?)",
            (jid_row_id, chat.partner_name if chat.is_group else None, sort_ts),
        )
        pk_map[chat.pk] = cur.lastrowid  # type: ignore[assignment]
    return pk_map


def _insert_messages(
    conn: sqlite3.Connection,
    messages: list[Message],
    chat_pk_map: dict[int, int],
    chat_is_group: dict[int, bool],
    jid_cache: _JidCache,
    media_remapper: MediaRemapper | None = None,
) -> None:
    """Insert messages and their satellite rows (media, location, quoted).

    Direction logic (from_me / sender_jid_row_id):
    - from_me maps directly: 1 = sent by device owner, 0 = received.
    - sender_jid_row_id differs between 1:1 and group chats:
      * 1:1 chats: always 0, because Android infers the sender from the
        chat's jid_row_id + from_me flag.
      * Group chats (incoming only): set to the jid row_id of the actual
        sender (from_jid). This is how Android knows which group member
        sent each message. For outgoing group messages, it stays 0 (self).

    sort_id comes from iOS ZSORT column: a monotonically increasing integer
    that preserves message ordering even when timestamps collide (e.g.
    rapid-fire messages within the same second). Android uses sort_id for
    display ordering when timestamps are identical.
    """
    # Build a lookup from stanza_id -> text for quoted message resolution
    stanza_text_map: dict[str, str | None] = {}
    for m in messages:
        if m.stanza_id:
            stanza_text_map[m.stanza_id] = m.text

    remapper = media_remapper or MediaRemapper()
    for msg in messages:
        chat_row_id = chat_pk_map.get(msg.chat_pk, 0)
        android_type = IOS_TO_ANDROID_MESSAGE_TYPE.get(msg.ios_type, 0)
        status = android_status(msg.ios_type, msg.from_me)
        timestamp = ios_ts_to_android_ms(msg.ios_timestamp)

        # sender_jid_row_id: 0 for 1:1 incoming, sender jid for group
        sender_jid_row_id = 0
        is_group = chat_is_group.get(msg.chat_pk, False)
        if is_group and msg.from_jid and not msg.from_me:
            sender_jid_row_id = jid_cache.get_or_insert(msg.from_jid)

        cur = conn.execute(
            """INSERT INTO message
               (chat_row_id, from_me, key_id, sender_jid_row_id,
                text_data, timestamp, message_type, status, sort_id, starred)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chat_row_id,
                int(msg.from_me),
                msg.stanza_id,
                sender_jid_row_id,
                msg.text,
                timestamp,
                android_type,
                status,
                msg.sort,
                int(msg.starred),
            ),
        )
        msg_row_id: int = cur.lastrowid  # type: ignore[assignment]

        # Satellite tables
        if msg.media is not None:
            android_path = remapper.remap(
                msg.media.local_path, msg.media.mime_type
            )
            conn.execute(
                """INSERT INTO message_media
                   (message_row_id, file_path, mime_type, file_size,
                    width, height, duration)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg_row_id,
                    android_path,
                    msg.media.mime_type,
                    msg.media.file_size,
                    msg.media.width,
                    msg.media.height,
                    msg.media.duration,
                ),
            )
            # Location from media
            if msg.media.latitude is not None and msg.media.longitude is not None:
                if msg.ios_type == 5:  # location message
                    conn.execute(
                        """INSERT OR IGNORE INTO message_location
                           (message_row_id, latitude, longitude)
                           VALUES (?, ?, ?)""",
                        (msg_row_id, msg.media.latitude, msg.media.longitude),
                    )

        # Quoted message reference
        if msg.quoted_stanza_id is not None:
            quoted_text = stanza_text_map.get(msg.quoted_stanza_id)
            conn.execute(
                """INSERT INTO message_quoted (message_row_id, key_id, text_data)
                   VALUES (?, ?, ?)""",
                (msg_row_id, msg.quoted_stanza_id, quoted_text),
            )

        # System message
        if msg.ios_type == 6:
            conn.execute(
                """INSERT INTO message_system (message_row_id, action_type)
                   VALUES (?, ?)""",
                (msg_row_id, 0),
            )


def _insert_group_participants(
    conn: sqlite3.Connection,
    group_members: list[GroupMember],
    chat_pk_map: dict[int, int],
    jid_cache: _JidCache,
) -> None:
    """Populate the ``group_participants`` table linking group JIDs to member JIDs.

    The Android schema models group membership as:
      group_participants.gjid_row_id  -> jid._id (the group's JID, e.g. 123456@g.us)
      group_participants.jid_row_id   -> jid._id (the member's JID, e.g. 1415555@s.whatsapp.net)

    The linkage requires two lookups per member:
    1. Map iOS chat_pk -> Android chat._id via chat_pk_map.
    2. From chat._id, look up chat.jid_row_id to get the group's JID row.
       (We can't use chat._id directly because gjid_row_id references the
       jid table, not the chat table.)
    3. Insert the member's JID via _JidCache to get their jid row_id.
    """
    for gm in group_members:
        gjid_row_id = chat_pk_map.get(gm.chat_pk, 0)
        # In the Android schema, gjid_row_id refers to the jid row of the group,
        # not the chat row. But we need the group JID's jid row_id.
        # We'll look it up from the chat table.
        row = conn.execute(
            "SELECT jid_row_id FROM chat WHERE _id = ?", (gjid_row_id,)
        ).fetchone()
        group_jid_row_id = row[0] if row else 0
        member_jid_row_id = jid_cache.get_or_insert(gm.member_jid)
        conn.execute(
            "INSERT INTO group_participants (gjid_row_id, jid_row_id) VALUES (?, ?)",
            (group_jid_row_id, member_jid_row_id),
        )


def convert_corpus(corpus: Corpus, output_path: Path) -> None:
    """Convert a parsed iOS Corpus into an Android msgstore.db at *output_path*."""
    conn = create_android_db(output_path)
    try:
        jid_cache = _JidCache(conn)

        chat_pk_map = _insert_chats(conn, corpus.chats, jid_cache)
        chat_is_group = {c.pk: c.is_group for c in corpus.chats}

        _insert_messages(conn, corpus.messages, chat_pk_map, chat_is_group, jid_cache)
        _insert_group_participants(
            conn, corpus.group_members, chat_pk_map, jid_cache
        )

        conn.commit()
    finally:
        conn.close()
