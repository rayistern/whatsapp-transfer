"""Tests for the Android msgstore.db converter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wat.convert.android_schema import SCHEMA_DDL, create_android_db
from wat.convert.mappings import (
    IOS_TO_ANDROID_MESSAGE_TYPE,
    ios_ts_to_android_ms,
    android_status,
)
from wat.convert.writer import convert_corpus, _split_jid
from wat.extract import parse_ios_db
from wat.model import Corpus

IOS_DB = Path(__file__).resolve().parent.parent / "test-data" / "extracted" / "ChatStorage.sqlite"

EXPECTED_TABLES = {
    "jid",
    "chat",
    "message",
    "message_media",
    "message_location",
    "message_quoted",
    "message_vcard",
    "message_system",
    "group_participants",
}


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

class TestSchema:
    def test_all_tables_created(self, tmp_path: Path):
        db_path = tmp_path / "schema_test.db"
        conn = create_android_db(db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            tables = {r[0] for r in rows}
            assert EXPECTED_TABLES.issubset(tables), f"Missing: {EXPECTED_TABLES - tables}"
        finally:
            conn.close()

    def test_indexes_created(self, tmp_path: Path):
        db_path = tmp_path / "schema_idx.db"
        conn = create_android_db(db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
            assert len(rows) >= 5
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# JID normalization
# ---------------------------------------------------------------------------

class TestJidNormalization:
    def test_split_standard(self):
        user, server = _split_jid("14155551234@s.whatsapp.net")
        assert user == "14155551234"
        assert server == "s.whatsapp.net"

    def test_split_group(self):
        user, server = _split_jid("17189740857-1517518006@g.us")
        assert user == "17189740857-1517518006"
        assert server == "g.us"

    def test_split_bare(self):
        user, server = _split_jid("bare")
        assert user == "bare"
        assert server == ""

    def test_jid_dedup_in_db(self, tmp_path: Path):
        """Inserting the same JID twice should not create duplicate rows."""
        db_path = tmp_path / "dedup.db"
        conn = create_android_db(db_path)
        try:
            conn.execute("INSERT INTO jid (user, server) VALUES ('a', 'b')")
            conn.execute("INSERT OR IGNORE INTO jid (user, server) VALUES ('a', 'b')")
            count = conn.execute("SELECT COUNT(*) FROM jid").fetchone()[0]
            assert count == 1
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Full conversion against real test data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def corpus() -> Corpus:
    assert IOS_DB.exists(), f"Test database not found at {IOS_DB}"
    return parse_ios_db(IOS_DB)


@pytest.fixture()
def android_db(corpus: Corpus, tmp_path: Path) -> Path:
    """Convert the corpus and return the path to the output DB."""
    out = tmp_path / "msgstore.db"
    convert_corpus(corpus, out)
    return out


class TestFullConversion:
    def test_message_count(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()
        assert count == 85

    def test_chat_count(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        conn.close()
        assert count == 3

    def test_jid_table_populated(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM jid").fetchone()[0]
        conn.close()
        assert count > 0

    def test_group_participants_populated(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM group_participants").fetchone()[0]
        conn.close()
        assert count == 460


# ---------------------------------------------------------------------------
# Timestamp spot-check
# ---------------------------------------------------------------------------

class TestTimestamps:
    def test_known_message_timestamp(self, android_db: Path):
        """Message pk=2 has ios_timestamp=757010981 (seconds since 2001).
        Expected Android: (757010981 + 978307200) * 1000 = 1_735_318_181_000
        """
        expected_ms = (757010981 + 978_307_200) * 1000
        conn = sqlite3.connect(str(android_db))
        # pk=2 in iOS is the second message inserted, so _id=2 in Android
        row = conn.execute(
            "SELECT timestamp FROM message WHERE _id = 2"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == expected_ms

    def test_timestamp_conversion_formula(self):
        assert ios_ts_to_android_ms(0.0) == 978_307_200_000
        assert ios_ts_to_android_ms(757010981) == (757010981 + 978_307_200) * 1000


# ---------------------------------------------------------------------------
# Type swap: iOS video(2)->Android(3), iOS audio(3)->Android(2)
# ---------------------------------------------------------------------------

class TestTypeMapping:
    def test_video_swap(self):
        assert IOS_TO_ANDROID_MESSAGE_TYPE[2] == 3

    def test_audio_swap(self):
        assert IOS_TO_ANDROID_MESSAGE_TYPE[3] == 2

    def test_video_messages_in_db(self, android_db: Path):
        """iOS has 2 video messages (type 2). In Android they should be type 3."""
        conn = sqlite3.connect(str(android_db))
        count = conn.execute(
            "SELECT COUNT(*) FROM message WHERE message_type = 3"
        ).fetchone()[0]
        conn.close()
        assert count == 2  # the 2 iOS video messages

    def test_unmapped_types_default_to_zero(self):
        """iOS types 10 and 14 are not in the map; should default to 0."""
        assert IOS_TO_ANDROID_MESSAGE_TYPE.get(10, 0) == 0
        assert IOS_TO_ANDROID_MESSAGE_TYPE.get(14, 0) == 0


# ---------------------------------------------------------------------------
# Status codes
# ---------------------------------------------------------------------------

class TestStatusCodes:
    def test_outgoing_status(self):
        assert android_status(ios_type=0, from_me=True) == 5

    def test_incoming_status(self):
        assert android_status(ios_type=0, from_me=False) == 0

    def test_system_status(self):
        assert android_status(ios_type=6, from_me=False) == 6

    def test_all_incoming_status_zero(self, android_db: Path):
        """All 85 messages in test data are incoming (from_me=0), non-system
        should have status=0, system (type 6 -> android 7) should have status=6."""
        conn = sqlite3.connect(str(android_db))
        # Non-system incoming messages: status should be 0
        non_sys = conn.execute(
            "SELECT COUNT(*) FROM message WHERE from_me = 0 AND message_type != 7 AND status != 0"
        ).fetchone()[0]
        # System messages: status should be 6
        sys_wrong = conn.execute(
            "SELECT COUNT(*) FROM message WHERE message_type = 7 AND status != 6"
        ).fetchone()[0]
        conn.close()
        assert non_sys == 0, "Non-system incoming messages should have status=0"
        assert sys_wrong == 0, "System messages should have status=6"
