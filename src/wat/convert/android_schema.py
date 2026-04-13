"""DDL for modern Android msgstore.db (2022+ normalized schema).

Provides the schema as a single DDL string and a helper to create an empty
database file ready for population by the converter.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_DDL = """\
CREATE TABLE jid (
    _id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user   TEXT    NOT NULL,
    server TEXT    NOT NULL,
    type   INTEGER DEFAULT 0,
    UNIQUE(user, server)
);

CREATE TABLE chat (
    _id               INTEGER PRIMARY KEY AUTOINCREMENT,
    jid_row_id        INTEGER NOT NULL REFERENCES jid(_id),
    subject           TEXT,
    created_timestamp  INTEGER,
    sort_timestamp     INTEGER
);

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

CREATE TABLE message_location (
    message_row_id INTEGER PRIMARY KEY REFERENCES message(_id),
    latitude       REAL,
    longitude      REAL
);

CREATE TABLE message_quoted (
    message_row_id INTEGER PRIMARY KEY REFERENCES message(_id),
    key_id         TEXT,
    text_data      TEXT
);

CREATE TABLE message_vcard (
    message_row_id INTEGER PRIMARY KEY REFERENCES message(_id),
    vcard          TEXT
);

CREATE TABLE message_system (
    message_row_id INTEGER PRIMARY KEY REFERENCES message(_id),
    action_type    INTEGER DEFAULT 0
);

CREATE TABLE group_participants (
    _id          INTEGER PRIMARY KEY AUTOINCREMENT,
    gjid_row_id  INTEGER,
    jid_row_id   INTEGER
);

-- Indexes
CREATE INDEX idx_chat_jid ON chat(jid_row_id);
CREATE INDEX idx_message_chat ON message(chat_row_id);
CREATE INDEX idx_message_timestamp ON message(timestamp);
CREATE INDEX idx_message_sort ON message(sort_id);
CREATE INDEX idx_message_media_msg ON message_media(message_row_id);
CREATE INDEX idx_group_participants_gjid ON group_participants(gjid_row_id);
CREATE INDEX idx_group_participants_jid ON group_participants(jid_row_id);

-- Additional tables WhatsApp Android may expect
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
    conn.execute("PRAGMA page_size = 4096")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_DDL)
    conn.execute("INSERT INTO props (key, value) VALUES ('schema_version', '1')")
    return conn
