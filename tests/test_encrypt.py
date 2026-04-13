"""Tests for the crypt15 encryption module."""

from __future__ import annotations

import io
import os
import sqlite3
import zlib
from pathlib import Path

import pytest

from wa_crypt_tools.lib.db.dbfactory import DatabaseFactory
from wa_crypt_tools.lib.key.key15 import Key15

from wat.encrypt import encrypt_db


def _make_test_db(path: Path) -> None:
    """Create a small SQLite database for testing."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, msg TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello world')")
    conn.execute("INSERT INTO test VALUES (2, 'second message')")
    conn.commit()
    conn.close()


def _write_key(path: Path) -> bytes:
    """Write a random 32-byte key file and return the key bytes."""
    key_bytes = os.urandom(32)
    path.write_bytes(key_bytes)
    return key_bytes


class TestEncryptDb:
    """Unit tests for encrypt_db."""

    def test_round_trip(self, tmp_path: Path) -> None:
        """Encrypt then decrypt and verify the DB contents match."""
        db_path = tmp_path / "msgstore.db"
        key_path = tmp_path / "backup.key"
        out_path = tmp_path / "msgstore.db.crypt15"
        decrypted_path = tmp_path / "msgstore_decrypted.db"

        _make_test_db(db_path)
        key_bytes = _write_key(key_path)
        original_bytes = db_path.read_bytes()

        # Encrypt
        encrypt_db(db_path, key_path, out_path)

        assert out_path.exists()
        assert out_path.stat().st_size > 0

        # Decrypt using wa-crypt-tools directly
        key = Key15(key=key_bytes)
        with open(out_path, "rb") as f:
            db = DatabaseFactory.from_file(f)
            encrypted_data = f.read()
        decrypted_compressed = db.decrypt(key, encrypted_data)
        decrypted_bytes = zlib.decompress(decrypted_compressed)

        assert decrypted_bytes == original_bytes

        # Verify DB contents are intact
        decrypted_path.write_bytes(decrypted_bytes)
        conn = sqlite3.connect(str(decrypted_path))
        rows = conn.execute("SELECT id, msg FROM test ORDER BY id").fetchall()
        conn.close()
        assert rows == [(1, "hello world"), (2, "second message")]

    def test_output_directory_created(self, tmp_path: Path) -> None:
        """Output parent directories are created automatically."""
        db_path = tmp_path / "msgstore.db"
        key_path = tmp_path / "backup.key"
        out_path = tmp_path / "nested" / "dir" / "msgstore.db.crypt15"

        _make_test_db(db_path)
        _write_key(key_path)

        encrypt_db(db_path, key_path, out_path)
        assert out_path.exists()

    def test_missing_db_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError when the database does not exist."""
        key_path = tmp_path / "backup.key"
        _write_key(key_path)

        with pytest.raises(FileNotFoundError, match="Database not found"):
            encrypt_db(tmp_path / "nope.db", key_path, tmp_path / "out.crypt15")

    def test_missing_key_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError when the key file does not exist."""
        db_path = tmp_path / "msgstore.db"
        _make_test_db(db_path)

        with pytest.raises(FileNotFoundError, match="Key file not found"):
            encrypt_db(db_path, tmp_path / "nope.key", tmp_path / "out.crypt15")

    def test_bad_key_length_raises(self, tmp_path: Path) -> None:
        """ValueError when the key file is not 32 bytes."""
        db_path = tmp_path / "msgstore.db"
        key_path = tmp_path / "bad.key"
        _make_test_db(db_path)
        key_path.write_bytes(os.urandom(16))  # Wrong length

        with pytest.raises(ValueError, match="exactly 32 bytes"):
            encrypt_db(db_path, key_path, tmp_path / "out.crypt15")
