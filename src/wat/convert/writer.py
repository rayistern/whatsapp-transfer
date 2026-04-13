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
    """Deduplicates JIDs and caches their row ids from the jid table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._cache: dict[str, int] = {}  # raw jid -> row_id

    def get_or_insert(self, raw_jid: str) -> int:
        """Return the jid._id for *raw_jid*, inserting if needed."""
        if not raw_jid:
            return 0
        if raw_jid in self._cache:
            return self._cache[raw_jid]
        user, server = _split_jid(raw_jid)
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
    """Insert chats and return a mapping of ios chat pk -> android chat _id."""
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
    """Insert messages and their satellite rows (media, location, quoted)."""
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
