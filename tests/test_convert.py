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

    def test_missed_call_maps_to_text(self):
        """iOS type 10 (missed call / group event) -> Android type 0 (text)."""
        assert IOS_TO_ANDROID_MESSAGE_TYPE[10] == 0

    def test_deleted_message_maps_to_15(self):
        """iOS type 14 (deleted/revoked) -> Android type 15."""
        assert IOS_TO_ANDROID_MESSAGE_TYPE[14] == 15

    def test_unmapped_types_default_to_zero(self):
        """Unknown iOS types not in the map should default to 0."""
        assert IOS_TO_ANDROID_MESSAGE_TYPE.get(99, 0) == 0
        assert IOS_TO_ANDROID_MESSAGE_TYPE.get(255, 0) == 0


# ---------------------------------------------------------------------------
# Status codes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Satellite tables: message_system, message_location, group_participants
# ---------------------------------------------------------------------------

class TestSystemMessages:
    def test_system_message_count(self, android_db: Path):
        """iOS type 6 messages (3 total) should each create a message_system row."""
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM message_system").fetchone()[0]
        conn.close()
        assert count == 3

    def test_system_message_action_type(self, android_db: Path):
        """All system messages should have action_type = 0 (generic)."""
        conn = sqlite3.connect(str(android_db))
        non_zero = conn.execute(
            "SELECT COUNT(*) FROM message_system WHERE action_type != 0"
        ).fetchone()[0]
        conn.close()
        assert non_zero == 0

    def test_system_messages_reference_valid_messages(self, android_db: Path):
        """Every message_system row should reference an existing message."""
        conn = sqlite3.connect(str(android_db))
        orphans = conn.execute(
            """SELECT COUNT(*) FROM message_system ms
               LEFT JOIN message m ON ms.message_row_id = m._id
               WHERE m._id IS NULL"""
        ).fetchone()[0]
        conn.close()
        assert orphans == 0

    def test_system_messages_have_type_7(self, android_db: Path):
        """Messages with message_system rows should have message_type = 7."""
        conn = sqlite3.connect(str(android_db))
        rows = conn.execute(
            """SELECT m.message_type FROM message_system ms
               JOIN message m ON ms.message_row_id = m._id"""
        ).fetchall()
        conn.close()
        assert len(rows) == 3
        for (mt,) in rows:
            assert mt == 7


class TestLocationMessages:
    def test_location_rows_reference_valid_messages(self, android_db: Path):
        """Every message_location row should reference an existing message."""
        conn = sqlite3.connect(str(android_db))
        orphans = conn.execute(
            """SELECT COUNT(*) FROM message_location ml
               LEFT JOIN message m ON ml.message_row_id = m._id
               WHERE m._id IS NULL"""
        ).fetchone()[0]
        conn.close()
        assert orphans == 0

    def test_location_rows_have_valid_coordinates(self, android_db: Path):
        """Location rows should have non-null latitude and longitude."""
        conn = sqlite3.connect(str(android_db))
        rows = conn.execute(
            "SELECT latitude, longitude FROM message_location"
        ).fetchall()
        conn.close()
        for lat, lon in rows:
            assert lat is not None
            assert lon is not None


class TestGroupParticipantsIntegration:
    def test_group_participants_count(self, android_db: Path):
        """460 group members across 2 groups."""
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM group_participants").fetchone()[0]
        conn.close()
        assert count == 460

    def test_group_participants_reference_valid_jids(self, android_db: Path):
        """Every group_participant jid_row_id should reference an existing jid."""
        conn = sqlite3.connect(str(android_db))
        orphans = conn.execute(
            """SELECT COUNT(*) FROM group_participants gp
               LEFT JOIN jid j ON gp.jid_row_id = j._id
               WHERE j._id IS NULL"""
        ).fetchone()[0]
        conn.close()
        assert orphans == 0

    def test_group_participants_have_gjid(self, android_db: Path):
        """Every group_participant should have a non-zero gjid_row_id."""
        conn = sqlite3.connect(str(android_db))
        zero_gjid = conn.execute(
            "SELECT COUNT(*) FROM group_participants WHERE gjid_row_id = 0"
        ).fetchone()[0]
        conn.close()
        assert zero_gjid == 0


# ---------------------------------------------------------------------------
# All messages convert without errors
# ---------------------------------------------------------------------------

class TestCompleteConversion:
    def test_all_85_messages_convert(self, android_db: Path):
        """All 85 messages from the test data should be in the Android DB."""
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()
        assert count == 85

    def test_deleted_messages_have_type_15(self, android_db: Path):
        """iOS type 14 (1 message) should map to Android type 15."""
        conn = sqlite3.connect(str(android_db))
        count = conn.execute(
            "SELECT COUNT(*) FROM message WHERE message_type = 15"
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_missed_call_messages_have_type_0(self, android_db: Path):
        """iOS type 10 (4 messages) should map to Android type 0 (text)."""
        # These are mixed with real text messages (type 0), so we just verify
        # total type-0 count includes the originals + the 4 from type 10
        conn = sqlite3.connect(str(android_db))
        count = conn.execute(
            "SELECT COUNT(*) FROM message WHERE message_type = 0"
        ).fetchone()[0]
        conn.close()
        # 66 text + 3 url(type 7->0) + 4 missed call(type 10->0) = 73
        assert count == 73


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
