"""Tests for the full run pipeline and copy_media_files."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wat.cli import app
from wat.convert.media import MediaRemapper, copy_media_files
from wat.extract import parse_ios_db
from wat.model import Corpus

EXTRACTED_DIR = Path(__file__).resolve().parent.parent / "test-data" / "extracted"
IOS_DB = EXTRACTED_DIR / "ChatStorage.sqlite"
IOS_MEDIA_DIR = EXTRACTED_DIR / "Message"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    assert IOS_DB.exists(), f"Test database not found at {IOS_DB}"
    return parse_ios_db(IOS_DB)


# ---------------------------------------------------------------------------
# copy_media_files unit tests
# ---------------------------------------------------------------------------


class TestCopyMediaFiles:
    def test_copies_existing_files(self, corpus: Corpus, tmp_path: Path):
        """copy_media_files should copy files that exist on disk."""
        android_dir = tmp_path / "Media"
        remapper = MediaRemapper()
        stats = copy_media_files(IOS_MEDIA_DIR, android_dir, remapper, corpus.messages)

        assert stats["copied"] > 0
        assert stats["skipped"] == 0
        # Some messages have media with local_path but files may be missing
        # (e.g. thumbnails are not referenced via local_path)

    def test_copied_count_matches_real_files(self, corpus: Corpus, tmp_path: Path):
        """The number of copied files should equal the number of messages with
        media that have non-None local_path AND whose source file exists."""
        android_dir = tmp_path / "Media"
        remapper = MediaRemapper()
        stats = copy_media_files(IOS_MEDIA_DIR, android_dir, remapper, corpus.messages)

        # Count expected: messages with media.local_path that exist on disk
        expected = 0
        for msg in corpus.messages:
            if msg.media and msg.media.local_path:
                src = IOS_MEDIA_DIR / msg.media.local_path
                if src.exists():
                    expected += 1

        assert stats["copied"] == expected
        assert stats["copied"] == 8  # 8 real media files in test data

    def test_output_directory_structure(self, corpus: Corpus, tmp_path: Path):
        """Copied files should land in Android-style subdirectories."""
        android_dir = tmp_path / "Media"
        remapper = MediaRemapper()
        copy_media_files(IOS_MEDIA_DIR, android_dir, remapper, corpus.messages)

        # Check that at least one WhatsApp Images dir was created
        found_dirs = set()
        for p in android_dir.rglob("*"):
            if p.is_file():
                # The parent relative to android_dir is the media type dir
                found_dirs.add(p.parent.name)

        # We know the test data has images, videos, and a PDF
        assert "WhatsApp Images" in found_dirs or any(
            "IMG-" in f.name for f in android_dir.rglob("*") if f.is_file()
        )

    def test_missing_source_tracked(self, tmp_path: Path):
        """Messages whose source file does not exist should be counted as missing."""
        from wat.model import Media, Message

        fake_msg = Message(
            pk=1, chat_pk=1, stanza_id="test", from_me=False,
            ios_type=1, ios_timestamp=0.0, sort=1, text=None,
            from_jid=None, to_jid=None,
            media=Media(
                local_path="Media/nonexistent/file.jpg",
                mime_type="image/jpeg",
                media_key=None, file_size=100,
                width=None, height=None, duration=None,
                latitude=None, longitude=None, title=None,
            ),
        )
        android_dir = tmp_path / "Media"
        remapper = MediaRemapper()
        stats = copy_media_files(
            tmp_path / "fake_ios", android_dir, remapper, [fake_msg]
        )
        assert stats["missing"] == 1
        assert stats["copied"] == 0

    def test_no_media_messages_no_copies(self, tmp_path: Path):
        """Messages without media should result in zero copies."""
        from wat.model import Message

        msg = Message(
            pk=1, chat_pk=1, stanza_id="test", from_me=False,
            ios_type=0, ios_timestamp=0.0, sort=1, text="Hello",
            from_jid=None, to_jid=None,
        )
        android_dir = tmp_path / "Media"
        remapper = MediaRemapper()
        stats = copy_media_files(tmp_path, android_dir, remapper, [msg])
        assert stats == {"copied": 0, "skipped": 0, "missing": 0}


# ---------------------------------------------------------------------------
# CLI run command tests
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_run_with_ios_flag(self, tmp_path: Path):
        """wat run --ios <extracted_dir> --out <tmp> should succeed."""
        out = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out)],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Pipeline complete" in result.output

    def test_run_creates_msgstore_db(self, tmp_path: Path):
        """The run command should produce WhatsApp/Databases/msgstore.db."""
        out = tmp_path / "output"
        runner = CliRunner()
        runner.invoke(app, ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out)])

        db_path = out / "WhatsApp" / "Databases" / "msgstore.db"
        assert db_path.exists()
        assert db_path.stat().st_size > 0

    def test_run_creates_media_tree(self, tmp_path: Path):
        """The run command should copy media files into WhatsApp/Media/."""
        out = tmp_path / "output"
        runner = CliRunner()
        runner.invoke(app, ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out)])

        media_dir = out / "WhatsApp" / "Media"
        assert media_dir.exists()

        copied_files = list(media_dir.rglob("*"))
        file_count = sum(1 for f in copied_files if f.is_file())
        assert file_count > 0, "No media files were copied"

    def test_run_no_encryption_without_key(self, tmp_path: Path):
        """Without --key, no .crypt15 file should be produced."""
        out = tmp_path / "output"
        runner = CliRunner()
        runner.invoke(app, ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out)])

        crypt_path = out / "WhatsApp" / "Databases" / "msgstore.db.crypt15"
        assert not crypt_path.exists()

    def test_run_with_key_produces_crypt15(self, tmp_path: Path):
        """With --key, a .crypt15 file should be produced."""
        import os

        out = tmp_path / "output"
        key_file = tmp_path / "backup.key"
        key_file.write_bytes(os.urandom(32))

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out),
             "--key", str(key_file)],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"

        crypt_path = out / "WhatsApp" / "Databases" / "msgstore.db.crypt15"
        assert crypt_path.exists()
        assert crypt_path.stat().st_size > 0

    def test_run_msgstore_has_correct_message_count(self, tmp_path: Path):
        """The msgstore.db produced by run should have 85 messages."""
        out = tmp_path / "output"
        runner = CliRunner()
        runner.invoke(app, ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out)])

        db_path = out / "WhatsApp" / "Databases" / "msgstore.db"
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()
        assert count == 85

    def test_run_mutually_exclusive_flags(self, tmp_path: Path):
        """--ios and --backup together should fail."""
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--ios", str(EXTRACTED_DIR), "--backup", str(EXTRACTED_DIR),
             "--out", str(tmp_path / "out")],
        )
        assert result.exit_code != 0

    def test_run_requires_source(self, tmp_path: Path):
        """Neither --ios nor --backup should fail."""
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--out", str(tmp_path / "out")],
        )
        assert result.exit_code != 0

    def test_run_prints_media_stats(self, tmp_path: Path):
        """The run command should print media copy stats."""
        out = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out)],
        )
        assert "copied" in result.output.lower()

    def test_run_prints_summary_table(self, tmp_path: Path):
        """The run command should print a summary table with message stats."""
        out = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out)],
        )
        assert result.exit_code == 0
        assert "Conversion Summary" in result.output

    def test_run_with_chats_filter(self, tmp_path: Path):
        """wat run --ios ... --chats 1 should only convert chat pk=1."""
        out = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out), "--chats", "1"],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"

        db_path = out / "WhatsApp" / "Databases" / "msgstore.db"
        conn = sqlite3.connect(str(db_path))
        msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        chat_count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        conn.close()
        assert chat_count == 1
        assert msg_count == 4

    def test_run_with_chats_filter_by_name(self, tmp_path: Path):
        """wat run --ios ... --chats 'Rayi' should filter by chat name."""
        out = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out), "--chats", "Rayi"],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Filtered" in result.output

    def test_run_with_bad_chats_filter(self, tmp_path: Path):
        """wat run --ios ... --chats 'NoSuchChat' should fail."""
        out = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "--ios", str(EXTRACTED_DIR), "--out", str(out), "--chats", "NoSuchChat"],
        )
        assert result.exit_code == 1
        assert "Error" in result.output
