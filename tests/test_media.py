"""Tests for media path remapping and media insertion in Android DB."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from wat.convert.media import MediaRemapper, remap_media_path
from wat.convert.writer import convert_corpus
from wat.extract import parse_ios_db
from wat.model import Corpus

IOS_DB = Path(__file__).resolve().parent.parent / "test-data" / "extracted" / "ChatStorage.sqlite"
FIXED_DATE = date(2025, 3, 15)


# ---------------------------------------------------------------------------
# Unit tests for MediaRemapper
# ---------------------------------------------------------------------------


class TestRemapImages:
    def test_jpeg_image(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/a/b/photo.jpg", "image/jpeg")
        assert result == "WhatsApp Images/IMG-20250315-WA0001.jpg"

    def test_png_image(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/a/b/photo.png", "image/png")
        assert result == "WhatsApp Images/IMG-20250315-WA0001.png"

    def test_sequence_increments(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        r1 = r.remap("Media/a.jpg", "image/jpeg")
        r2 = r.remap("Media/b.jpg", "image/jpeg")
        assert r1 == "WhatsApp Images/IMG-20250315-WA0001.jpg"
        assert r2 == "WhatsApp Images/IMG-20250315-WA0002.jpg"


class TestRemapVideo:
    def test_mp4_video(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/vid.mp4", "video/mp4")
        assert result == "WhatsApp Video/VID-20250315-WA0001.mp4"


class TestRemapAudio:
    def test_regular_audio(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/audio.ogg", "audio/ogg")
        assert result == "WhatsApp Audio/AUD-20250315-WA0001.ogg"

    def test_voice_note_ptt(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/ptt/voice.ogg", "audio/ogg")
        assert result == "WhatsApp Voice Notes/PTT-20250315-WA0001.opus"

    def test_ptt_case_insensitive(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/PTT/voice.ogg", "audio/ogg")
        assert result == "WhatsApp Voice Notes/PTT-20250315-WA0001.opus"


class TestRemapDocuments:
    def test_pdf_document(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/3/b/report.pdf", "application/pdf")
        assert result == "WhatsApp Documents/report.pdf"

    def test_document_preserves_filename(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap(
            "Media/group@g.us/x/y/My Document (2).docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert result == "WhatsApp Documents/My Document (2).docx"


class TestNoneHandling:
    def test_none_path_returns_none(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        assert r.remap(None, "image/jpeg") is None

    def test_none_path_none_mime(self):
        assert remap_media_path(None, None) is None


class TestUnknownMime:
    def test_unknown_mime_infers_from_extension_jpg(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/a/b/photo.jpg", None)
        assert result == "WhatsApp Images/IMG-20250315-WA0001.jpg"

    def test_unknown_mime_infers_from_extension_mp4(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/a/b/clip.mp4", None)
        assert result == "WhatsApp Video/VID-20250315-WA0001.mp4"

    def test_invalid_mime_not_slash(self):
        """A MIME-type without '/' (like a JID stored in ZVCARDSTRING) should
        be treated as unknown and fall back to extension inference."""
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/a/b/photo.jpg", "13479949770@s.whatsapp.net")
        assert result == "WhatsApp Images/IMG-20250315-WA0001.jpg"

    def test_completely_unknown_falls_to_document(self):
        r = MediaRemapper(reference_date=FIXED_DATE)
        result = r.remap("Media/group@g.us/a/b/mystery.xyz", None)
        assert result == "WhatsApp Documents/mystery.xyz"


class TestConvenienceFunction:
    def test_remap_media_path_works(self):
        result = remap_media_path("Media/photo.jpg", "image/jpeg")
        assert result is not None
        assert "WhatsApp Images/IMG-" in result
        assert result.endswith(".jpg")


# ---------------------------------------------------------------------------
# Integration: full conversion with media
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    assert IOS_DB.exists(), f"Test database not found at {IOS_DB}"
    return parse_ios_db(IOS_DB)


@pytest.fixture()
def android_db(corpus: Corpus, tmp_path: Path) -> Path:
    out = tmp_path / "msgstore.db"
    convert_corpus(corpus, out)
    return out


class TestFullConversionMedia:
    def test_message_media_row_count(self, android_db: Path):
        """There should be 76 message_media rows matching the 76 media items."""
        conn = sqlite3.connect(str(android_db))
        count = conn.execute("SELECT COUNT(*) FROM message_media").fetchone()[0]
        conn.close()
        assert count == 76

    def test_media_rows_have_message_row_id(self, android_db: Path):
        """Every message_media row should reference an existing message."""
        conn = sqlite3.connect(str(android_db))
        orphans = conn.execute(
            """SELECT COUNT(*) FROM message_media mm
               LEFT JOIN message m ON mm.message_row_id = m._id
               WHERE m._id IS NULL"""
        ).fetchone()[0]
        conn.close()
        assert orphans == 0

    def test_image_paths_remapped(self, android_db: Path):
        """Image media should have Android-style paths."""
        conn = sqlite3.connect(str(android_db))
        rows = conn.execute(
            "SELECT file_path FROM message_media WHERE mime_type = 'image/jpeg'"
        ).fetchall()
        conn.close()
        assert len(rows) > 0
        for (path,) in rows:
            assert path is not None
            assert path.startswith("WhatsApp Images/IMG-")
            assert path.endswith(".jpg")

    def test_video_paths_remapped(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        rows = conn.execute(
            "SELECT file_path FROM message_media WHERE mime_type = 'video/mp4'"
        ).fetchall()
        conn.close()
        assert len(rows) > 0
        for (path,) in rows:
            assert path is not None
            assert path.startswith("WhatsApp Video/VID-")
            assert path.endswith(".mp4")

    def test_document_paths_remapped(self, android_db: Path):
        conn = sqlite3.connect(str(android_db))
        rows = conn.execute(
            "SELECT file_path FROM message_media WHERE mime_type = 'application/pdf'"
        ).fetchall()
        conn.close()
        assert len(rows) > 0
        for (path,) in rows:
            assert path is not None
            assert path.startswith("WhatsApp Documents/")
            assert path.endswith(".pdf")

    def test_null_path_media_stays_null(self, android_db: Path):
        """Media items with NULL local_path should have NULL file_path."""
        conn = sqlite3.connect(str(android_db))
        null_count = conn.execute(
            "SELECT COUNT(*) FROM message_media WHERE file_path IS NULL"
        ).fetchone()[0]
        conn.close()
        # 68 media items have NULL local_path in the test data
        assert null_count == 68
