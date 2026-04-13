"""End-to-end tests: iOS ChatStorage.sqlite -> Android msgstore.db pipeline."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wat.cli import app
from wat.extract import parse_ios_db
from wat.convert.writer import convert_corpus
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


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    assert IOS_DB.exists(), f"Test database not found at {IOS_DB}"
    return parse_ios_db(IOS_DB)


@pytest.fixture()
def android_db(corpus: Corpus, tmp_path: Path) -> Path:
    """Run the full pipeline and return the path to the output DB."""
    out = tmp_path / "msgstore.db"
    convert_corpus(corpus, out)
    return out


# ---------------------------------------------------------------------------
# Pipeline: parse -> convert -> verify
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_output_file_created(self, android_db: Path):
        assert android_db.exists()
        assert android_db.stat().st_size > 0

    def test_all_expected_tables_exist(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        conn.close()
        tables = {r[0] for r in rows}
        assert EXPECTED_TABLES.issubset(tables), f"Missing: {EXPECTED_TABLES - tables}"

    def test_message_count_85(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()
        assert count == 85

    def test_chat_count_3(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        conn.close()
        assert count == 3

    def test_hey_message_preserved(self, android_db: Path):
        """Verify a specific text message ('Hey') survives the full pipeline."""
        conn = sqlite3.connect(str(android_db))
        rows = conn.execute(
            "SELECT text_data FROM message WHERE text_data = 'Hey'"
        ).fetchall()
        conn.close()
        assert len(rows) >= 1, "Expected 'Hey' message not found in output"

    def test_timestamps_valid_unix_ms(self, android_db: Path):
        """All timestamps should be in valid Unix millisecond range."""
        conn = sqlite3.connect(str(android_db))
        rows = conn.execute("SELECT timestamp FROM message WHERE timestamp IS NOT NULL").fetchall()
        conn.close()
        assert len(rows) > 0
        for (ts,) in rows:
            assert ts > 1_500_000_000_000, f"Timestamp {ts} too small for Unix ms"
            assert ts < 2_000_000_000_000, f"Timestamp {ts} too large for Unix ms"

    def test_media_entries_exist(self, android_db: Path):
        """Messages with media should have entries in message_media."""
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM message_media").fetchone()[0]
        conn.close()
        assert count > 0, "No media entries found in message_media"

    def test_media_references_valid_messages(self, android_db: Path):
        """Every message_media row should reference an existing message."""
        conn = sqlite3.connect(str(android_db))
        orphans = conn.execute(
            """SELECT COUNT(*) FROM message_media mm
               LEFT JOIN message m ON mm.message_row_id = m._id
               WHERE m._id IS NULL"""
        ).fetchone()[0]
        conn.close()
        assert orphans == 0

    def test_group_participants_populated(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM group_participants").fetchone()[0]
        conn.close()
        assert count == 460

    def test_group_participants_reference_valid_jids(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        orphans = conn.execute(
            """SELECT COUNT(*) FROM group_participants gp
               LEFT JOIN jid j ON gp.jid_row_id = j._id
               WHERE j._id IS NULL"""
        ).fetchone()[0]
        conn.close()
        assert orphans == 0

    def test_jid_table_has_entries(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM jid").fetchone()[0]
        conn.close()
        assert count > 0


# ---------------------------------------------------------------------------
# CLI integration via CliRunner
# ---------------------------------------------------------------------------


class TestCLI:
    def test_convert_command_succeeds(self, tmp_path: Path):
        """The CLI convert command should run without error."""
        out = tmp_path / "cli_output.db"
        runner = CliRunner()
        result = runner.invoke(app, ["convert", "--ios", str(IOS_DB), "--out", str(out)])
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert out.exists()

    def test_convert_command_output_message(self, tmp_path: Path):
        """The CLI should print a summary with message and chat counts."""
        out = tmp_path / "cli_output2.db"
        runner = CliRunner()
        result = runner.invoke(app, ["convert", "--ios", str(IOS_DB), "--out", str(out)])
        assert "85 messages" in result.output
        assert "3 chats" in result.output

    def test_convert_command_produces_valid_db(self, tmp_path: Path):
        """The DB produced by the CLI should have all 85 messages."""
        out = tmp_path / "cli_output3.db"
        runner = CliRunner()
        runner.invoke(app, ["convert", "--ios", str(IOS_DB), "--out", str(out)])
        conn = sqlite3.connect(str(out))
        count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()
        assert count == 85

    def test_extract_invalid_backup(self):
        runner = CliRunner()
        result = runner.invoke(app, ["extract", "--backup", "/tmp", "--out", "/tmp/out"])
        assert result.exit_code == 1
        assert "not a valid iTunes backup" in result.output.lower() or "Error" in result.output

    def test_encrypt_command_succeeds(self, tmp_path: Path):
        """Encrypt command produces a crypt15 file from a valid DB and key."""
        import os
        import sqlite3

        db_file = tmp_path / "msgstore.db"
        key_file = tmp_path / "backup.key"
        out_file = tmp_path / "msgstore.db.crypt15"

        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()
        key_file.write_bytes(os.urandom(32))

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["encrypt", "--db", str(db_file), "--key", str(key_file), "--out", str(out_file)],
        )
        assert result.exit_code == 0
        assert out_file.exists()


# ---------------------------------------------------------------------------
# Selective chat transfer (--chats)
# ---------------------------------------------------------------------------


class TestSelectiveChatTransfer:
    """Tests for --chats filtering on the convert command."""

    def test_filter_by_pk(self, tmp_path: Path):
        """--chats 1 should only convert chat pk=1 (4 messages)."""
        out = tmp_path / "filtered.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out), "--chats", "1"],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        conn = sqlite3.connect(str(out))
        msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        chat_count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        conn.close()
        assert chat_count == 1
        assert msg_count == 4

    def test_filter_by_name(self, tmp_path: Path):
        """--chats 'Rayi' should match the private chat with partner_name='Rayi'."""
        out = tmp_path / "filtered.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out), "--chats", "Rayi"],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        conn = sqlite3.connect(str(out))
        msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        chat_count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        conn.close()
        assert chat_count == 1
        assert msg_count == 4  # 4 messages in the Rayi chat

    def test_filter_by_name_case_insensitive(self, tmp_path: Path):
        """--chats 'rayi' (lowercase) should still match."""
        out = tmp_path / "filtered.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out), "--chats", "rayi"],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        conn = sqlite3.connect(str(out))
        chat_count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        conn.close()
        assert chat_count == 1

    def test_filter_by_name_substring(self, tmp_path: Path):
        """--chats 'JLI' should match 'JLI Instructors' via substring."""
        out = tmp_path / "filtered.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out), "--chats", "JLI"],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        conn = sqlite3.connect(str(out))
        msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        chat_count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        conn.close()
        assert chat_count == 1
        assert msg_count == 80  # 80 messages in JLI Instructors

    def test_filter_multiple_pks(self, tmp_path: Path):
        """--chats '1,3' should include both chats."""
        out = tmp_path / "filtered.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out), "--chats", "1,3"],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        conn = sqlite3.connect(str(out))
        msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        chat_count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        conn.close()
        assert chat_count == 2
        assert msg_count == 5  # 4 + 1

    def test_filter_fewer_messages_than_total(self, tmp_path: Path):
        """Filtered output should have fewer messages than the full 85."""
        out = tmp_path / "filtered.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out), "--chats", "1"],
        )
        assert result.exit_code == 0
        conn = sqlite3.connect(str(out))
        msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()
        assert msg_count < 85

    def test_no_chats_option_includes_all(self, tmp_path: Path):
        """Without --chats, all 85 messages should be converted."""
        out = tmp_path / "all.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out)],
        )
        assert result.exit_code == 0
        conn = sqlite3.connect(str(out))
        msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()
        assert msg_count == 85

    def test_filter_nonexistent_chat_name_fails(self, tmp_path: Path):
        """--chats with a name that matches nothing should fail."""
        out = tmp_path / "bad.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out), "--chats", "NoSuchChat"],
        )
        assert result.exit_code == 1
        assert "Error" in result.output
        assert "No chats matched" in result.output

    def test_filter_nonexistent_pk_fails(self, tmp_path: Path):
        """--chats with a PK that does not exist should fail."""
        out = tmp_path / "bad.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out), "--chats", "999"],
        )
        assert result.exit_code == 1
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error output on bad inputs."""

    def test_convert_nonexistent_ios_db(self, tmp_path: Path):
        """Passing a non-existent file to --ios should fail with exit code != 0."""
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(tmp_path / "nope.sqlite"), "--out", str(tmp_path / "out.db")],
        )
        # Typer's exists=True check will catch this before our code
        assert result.exit_code != 0

    def test_convert_invalid_sqlite(self, tmp_path: Path):
        """Passing a non-SQLite file should produce a database error."""
        bad_db = tmp_path / "bad.sqlite"
        bad_db.write_text("this is not a database")
        out = tmp_path / "out.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(bad_db), "--out", str(out)],
        )
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_convert_summary_table_printed(self, tmp_path: Path):
        """The convert command should print a summary table."""
        out = tmp_path / "out.db"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", "--ios", str(IOS_DB), "--out", str(out)],
        )
        assert result.exit_code == 0
        assert "Conversion Summary" in result.output
        assert "text" in result.output.lower()
