"""Encrypt a plaintext msgstore.db into a WhatsApp crypt15 file.

Uses wa-crypt-tools internally for key handling and the crypt15 wire format.
"""

from __future__ import annotations

import zlib
from pathlib import Path

from wa_crypt_tools.lib.key.key15 import Key15
from wa_crypt_tools.lib.db.db15 import Database15
from wa_crypt_tools.lib.props import Props


def encrypt_db(db_path: Path, key_path: Path, output_path: Path) -> None:
    """Encrypt *db_path* with the 32-byte key in *key_path*, writing crypt15 to *output_path*.

    Parameters
    ----------
    db_path:
        Path to an unencrypted SQLite ``msgstore.db``.
    key_path:
        Path to a raw 32-byte key file (the WhatsApp root key material).
    output_path:
        Destination for the encrypted ``.crypt15`` file.

    Raises
    ------
    FileNotFoundError
        If *db_path* or *key_path* does not exist.
    ValueError
        If the key file is not exactly 32 bytes.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    if not key_path.exists():
        raise FileNotFoundError(f"Key file not found: {key_path}")

    # Read the raw 32-byte root key
    key_bytes = key_path.read_bytes()
    if len(key_bytes) != 32:
        raise ValueError(
            f"Key file must be exactly 32 bytes, got {len(key_bytes)}"
        )

    key = Key15(key=key_bytes)

    # Read and compress the plaintext database
    plaintext = db_path.read_bytes()
    compressed = zlib.compress(plaintext, 1)

    # Build a Database15 object (generates a random IV) and encrypt
    db = Database15(key=key)
    props = Props()
    encrypted = db.encrypt(key, props, compressed)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encrypted)
