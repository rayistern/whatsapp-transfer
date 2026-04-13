"""Tests for iTunes backup extraction (unencrypted only)."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from wat.extract.backup import (
    WHATSAPP_DOMAIN,
    detect_backup_type,
    extract_backup,
    extract_from_unencrypted_backup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_id(domain: str, relative_path: str) -> str:
    """Compute the SHA-1 file ID that iTunes uses for on-disk storage."""
    return hashlib.sha1(f"{domain}-{relative_path}".encode("utf-8")).hexdigest()


def _create_manifest_db(db_path: Path, rows: list[tuple[str, str, str, int]]) -> None:
    """Create a minimal Manifest.db with the given file rows.

    Each row is (fileID, domain, relativePath, flags).
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE Files (
            fileID TEXT,
            domain TEXT,
            relativePath TEXT,
            flags INTEGER,
            file BLOB
        )
        """
    )
    conn.executemany(
        "INSERT INTO Files (fileID, domain, relativePath, flags, file) VALUES (?, ?, ?, ?, NULL)",
        rows,
    )
    conn.commit()
    conn.close()


def _create_hashed_file(backup_dir: Path, file_id: str, content: bytes = b"data") -> None:
    """Create a file in the iTunes hashed structure: <backup>/<first2>/<fileID>."""
    subdir = backup_dir / file_id[:2]
    subdir.mkdir(parents=True, exist_ok=True)
    (subdir / file_id).write_bytes(content)


def _build_synthetic_backup(
    backup_dir: Path,
    files: list[tuple[str, str]] | None = None,
    include_manifest_plist: bool = False,
    encrypted: bool = False,
) -> None:
    """Build a synthetic unencrypted iTunes backup.

    Args:
        backup_dir: Root of the synthetic backup.
        files: List of (domain, relativePath) tuples. Content auto-generated.
        include_manifest_plist: If True, create a Manifest.plist.
        encrypted: If True, set IsEncrypted in the plist.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)

    if files is None:
        files = []

    rows: list[tuple[str, str, str, int]] = []
    for domain, rel_path in files:
        fid = _file_id(domain, rel_path)
        rows.append((fid, domain, rel_path, 1))
        _create_hashed_file(backup_dir, fid, content=f"content-of-{rel_path}".encode())

    _create_manifest_db(backup_dir / "Manifest.db", rows)

    if include_manifest_plist:
        import plistlib

        plist_data = {"IsEncrypted": encrypted}
        with open(backup_dir / "Manifest.plist", "wb") as f:
            plistlib.dump(plist_data, f)


# ---------------------------------------------------------------------------
# detect_backup_type
# ---------------------------------------------------------------------------


class TestDetectBackupType:
    def test_no_manifest_db(self, tmp_path: Path) -> None:
        assert detect_backup_type(tmp_path) is None

    def test_unencrypted(self, tmp_path: Path) -> None:
        _build_synthetic_backup(tmp_path)
        assert detect_backup_type(tmp_path) == "unencrypted"

    def test_unencrypted_with_plist_not_encrypted(self, tmp_path: Path) -> None:
        _build_synthetic_backup(tmp_path, include_manifest_plist=True, encrypted=False)
        assert detect_backup_type(tmp_path) == "unencrypted"

    def test_encrypted(self, tmp_path: Path) -> None:
        _build_synthetic_backup(tmp_path, include_manifest_plist=True, encrypted=True)
        assert detect_backup_type(tmp_path) == "encrypted"


# ---------------------------------------------------------------------------
# extract_from_unencrypted_backup
# ---------------------------------------------------------------------------


class TestUnencryptedExtraction:
    def test_basic_extraction(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backup"
        out_dir = tmp_path / "output"

        wa_files = [
            (WHATSAPP_DOMAIN, "ChatStorage.sqlite"),
            (WHATSAPP_DOMAIN, "Message/Media/group/IMG_001.jpg"),
            (WHATSAPP_DOMAIN, "Message/Media/group/VID_002.mp4"),
        ]
        _build_synthetic_backup(backup_dir, files=wa_files)

        stats = extract_from_unencrypted_backup(backup_dir, out_dir)

        assert stats["files_extracted"] == 3
        assert stats["chat_storage_found"] is True

        # Verify files exist at correct relative paths
        assert (out_dir / "ChatStorage.sqlite").exists()
        assert (out_dir / "Message" / "Media" / "group" / "IMG_001.jpg").exists()
        assert (out_dir / "Message" / "Media" / "group" / "VID_002.mp4").exists()

        # Verify content
        content = (out_dir / "ChatStorage.sqlite").read_text()
        assert content == "content-of-ChatStorage.sqlite"

    def test_no_whatsapp_data(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backup"
        out_dir = tmp_path / "output"

        # Some other app's files
        other_files = [
            ("AppDomain-com.other.app", "Documents/file.txt"),
        ]
        _build_synthetic_backup(backup_dir, files=other_files)

        stats = extract_from_unencrypted_backup(backup_dir, out_dir)
        assert stats["files_extracted"] == 0
        assert stats["chat_storage_found"] is False

    def test_missing_manifest_db(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Manifest.db"):
            extract_from_unencrypted_backup(tmp_path, tmp_path / "output")

    def test_skips_directories(self, tmp_path: Path) -> None:
        """Files with flags != 1 (directories) should be skipped."""
        backup_dir = tmp_path / "backup"
        out_dir = tmp_path / "output"
        backup_dir.mkdir(parents=True)

        fid = _file_id(WHATSAPP_DOMAIN, "Message/Media")
        rows = [(fid, WHATSAPP_DOMAIN, "Message/Media", 2)]  # flags=2 => directory
        _create_manifest_db(backup_dir / "Manifest.db", rows)

        stats = extract_from_unencrypted_backup(backup_dir, out_dir)
        assert stats["files_extracted"] == 0

    def test_missing_source_file_skipped(self, tmp_path: Path) -> None:
        """If the hashed file is missing on disk, skip it gracefully."""
        backup_dir = tmp_path / "backup"
        out_dir = tmp_path / "output"
        backup_dir.mkdir(parents=True)

        fid = _file_id(WHATSAPP_DOMAIN, "ChatStorage.sqlite")
        rows = [(fid, WHATSAPP_DOMAIN, "ChatStorage.sqlite", 1)]
        _create_manifest_db(backup_dir / "Manifest.db", rows)
        # Do NOT create the actual hashed file

        stats = extract_from_unencrypted_backup(backup_dir, out_dir)
        assert stats["files_extracted"] == 0
        assert stats["chat_storage_found"] is False

    def test_without_chat_storage(self, tmp_path: Path) -> None:
        """Backup with WhatsApp media but no ChatStorage.sqlite."""
        backup_dir = tmp_path / "backup"
        out_dir = tmp_path / "output"

        wa_files = [
            (WHATSAPP_DOMAIN, "Message/Media/group/IMG.jpg"),
        ]
        _build_synthetic_backup(backup_dir, files=wa_files)

        stats = extract_from_unencrypted_backup(backup_dir, out_dir)
        assert stats["files_extracted"] == 1
        assert stats["chat_storage_found"] is False


# ---------------------------------------------------------------------------
# extract_backup (unified entry point)
# ---------------------------------------------------------------------------


class TestExtractBackup:
    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            extract_backup(tmp_path / "nope", tmp_path / "out")

    def test_not_a_backup(self, tmp_path: Path) -> None:
        """Directory exists but has no Manifest.db."""
        with pytest.raises(FileNotFoundError, match="(?i)not a valid iTunes backup"):
            extract_backup(tmp_path, tmp_path / "out")

    def test_encrypted_without_password(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backup"
        _build_synthetic_backup(
            backup_dir, include_manifest_plist=True, encrypted=True
        )
        with pytest.raises(ValueError, match="encrypted"):
            extract_backup(backup_dir, tmp_path / "out")

    def test_unencrypted_via_unified(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backup"
        out_dir = tmp_path / "output"

        wa_files = [
            (WHATSAPP_DOMAIN, "ChatStorage.sqlite"),
            (WHATSAPP_DOMAIN, "Message/Media/group/photo.jpg"),
        ]
        _build_synthetic_backup(backup_dir, files=wa_files)

        stats = extract_backup(backup_dir, out_dir)
        assert stats["files_extracted"] == 2
        assert stats["chat_storage_found"] is True
        assert (out_dir / "ChatStorage.sqlite").exists()
