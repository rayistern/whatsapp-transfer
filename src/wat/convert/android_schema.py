"""DDL for modern Android msgstore.db (2022+ normalized schema).

Provides the schema as a single DDL string and a helper to create an empty
database file ready for population by the converter.

Why the modern (2022+) schema and not legacy:
    WhatsApp Android migrated from a denormalized single-table schema
    (pre-2022, with columns like key_remote_jid directly on messages)
    to a normalized schema with separate jid, chat, message, and
    satellite tables.  We target the modern schema because:
    1. All recent WhatsApp versions (2022+) use it, and older versions
       will auto-migrate on first launch anyway.
    2. The normalized schema is cleaner to generate from scratch — each
       entity has its own table, avoiding the wide-column mess of legacy.
    3. The crypt15 format (which we also target) is only used with the
       modern schema.
    Decision made during Phase 0 spec (April 2025), confirmed by
    research/02-db-schemas.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_DDL = """\
-- jid: canonical lookup table for all WhatsApp JID strings (contacts, groups,
-- broadcast lists). The UNIQUE(user, server) constraint ensures each JID is
-- stored exactly once; other tables reference jid._id via foreign keys.
CREATE TABLE jid (
    _id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user   TEXT    NOT NULL,
    server TEXT    NOT NULL,
    type   INTEGER DEFAULT 0,
    UNIQUE(user, server)
);

-- chat: one row per conversation (1:1, group, or broadcast). Links to jid
-- via jid_row_id. subject holds the group name (NULL for 1:1 chats).
CREATE TABLE chat (
    _id               INTEGER PRIMARY KEY AUTOINCREMENT,
    jid_row_id        INTEGER NOT NULL REFERENCES jid(_id),
    subject           TEXT,
    created_timestamp  INTEGER,
    sort_timestamp     INTEGER
);

-- message: core message table. Each row is one sent/received message.
-- Satellite data (media, location, quotes, system info) lives in separate
-- tables linked by message_row_id, keeping this table narrow.
CREATE TABLE message (
    _id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_row_id      INTEGER NOT NULL REFERENCES chat(_id),
    from_me          INTEGER NOT NULL DEFAULT 0,
    key_id           TEXT,
    sender_jid_row_id INTEGER DEFAULT 0,
    text_data        TEXT,
    timestamp        INTEGER,
    message_type     INTEGER DEFAULT 0,
    status           INTEGER DEFAULT 0,
    sort_id          INTEGER,
    starred          INTEGER DEFAULT 0
);

-- message_media: file attachment metadata (one row per media message).
CREATE TABLE message_media (
    _id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_row_id INTEGER NOT NULL REFERENCES message(_id),
    file_path      TEXT,
    mime_type      TEXT,
    file_size      INTEGER,
    width          INTEGER,
    height         INTEGER,
    duration       INTEGER
);

-- message_location: GPS coordinates for location-type messages.
CREATE TABLE message_location (
    message_row_id INTEGER PRIMARY KEY REFERENCES message(_id),
    latitude       REAL,
    longitude      REAL
);

-- message_quoted: stores the stanza_id and text of the message being
-- replied to, so Android can render the quote bubble.
CREATE TABLE message_quoted (
    message_row_id INTEGER PRIMARY KEY REFERENCES message(_id),
    key_id         TEXT,
    text_data      TEXT
);

-- message_vcard: stores shared contact vCards.
CREATE TABLE message_vcard (
    message_row_id INTEGER PRIMARY KEY REFERENCES message(_id),
    vcard          TEXT
);

-- message_system: metadata for system messages (group events, encryption
-- notices). action_type encodes the specific system event kind.
CREATE TABLE message_system (
    message_row_id INTEGER PRIMARY KEY REFERENCES message(_id),
    action_type    INTEGER DEFAULT 0
);

-- group_participants: links group JIDs to their member JIDs.
-- gjid_row_id -> jid._id of the group, jid_row_id -> jid._id of the member.
CREATE TABLE group_participants (
    _id          INTEGER PRIMARY KEY AUTOINCREMENT,
    gjid_row_id  INTEGER,
    jid_row_id   INTEGER
);

-- Indexes for query performance (WhatsApp Android uses these access patterns)
CREATE INDEX idx_chat_jid ON chat(jid_row_id);
CREATE INDEX idx_message_chat ON message(chat_row_id);
CREATE INDEX idx_message_timestamp ON message(timestamp);
CREATE INDEX idx_message_sort ON message(sort_id);
CREATE INDEX idx_message_media_msg ON message_media(message_row_id);
CREATE INDEX idx_group_participants_gjid ON group_participants(gjid_row_id);
CREATE INDEX idx_group_participants_jid ON group_participants(jid_row_id);

-- Additional empty tables that WhatsApp Android may check for existence on
-- startup. If these are missing, the app can crash or trigger a re-sync.
-- We create them empty so the schema passes WhatsApp's validation checks.
-- (Discovered via research/06-deep-dive-remaining-gaps.md, April 2025.)
CREATE TABLE IF NOT EXISTS message_add_on (_id INTEGER PRIMARY KEY AUTOINCREMENT, message_row_id INTEGER, type INTEGER);
CREATE TABLE IF NOT EXISTS message_forwarded (message_row_id INTEGER PRIMARY KEY, forward_score INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS receipt_device (_id INTEGER PRIMARY KEY AUTOINCREMENT, message_row_id INTEGER, receipt_device_jid_row_id INTEGER, receipt_device_timestamp INTEGER);
CREATE TABLE IF NOT EXISTS receipt_user (_id INTEGER PRIMARY KEY AUTOINCREMENT, message_row_id INTEGER, receipt_user_jid_row_id INTEGER, receipt_user_timestamp INTEGER);
CREATE TABLE IF NOT EXISTS props (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS message_thumbnail (message_row_id INTEGER PRIMARY KEY, thumbnail BLOB);
CREATE TABLE IF NOT EXISTS audio_data (message_row_id INTEGER PRIMARY KEY, waveform BLOB);
"""


def create_android_db(path: Path) -> sqlite3.Connection:
    """Create a new Android msgstore.db at *path* with the schema applied.

    Returns an open connection so the caller can immediately populate it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    # page_size=4096: matches the default WhatsApp Android uses. Using a
    # different page size would cause WhatsApp to rebuild the database on
    # first open, which risks data loss or corruption.
    conn.execute("PRAGMA page_size = 4096")
    # WAL (Write-Ahead Logging) journal mode: WhatsApp Android expects WAL
    # mode. If we leave the default (DELETE journal mode), WhatsApp converts
    # it on first open, which can be slow for large databases and may trigger
    # integrity check failures.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_DDL)
    conn.execute("INSERT INTO props (key, value) VALUES ('schema_version', '1')")
    return conn
