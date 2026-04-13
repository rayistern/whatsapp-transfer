"""Extract WhatsApp data from iTunes backups (encrypted and unencrypted)."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import Any

# WhatsApp shared domain used in iTunes backups
WHATSAPP_DOMAIN = "AppDomainGroup-group.net.whatsapp.WhatsApp.shared"
WHATSAPP_DOMAIN_LIKE = "%net.whatsapp.%"

# Key file we look for to confirm WhatsApp data is present
CHAT_STORAGE_RELATIVE = "ChatStorage.sqlite"


def detect_backup_type(backup_dir: Path) -> str | None:
    """Detect whether the backup directory is encrypted, unencrypted, or invalid.

    Returns:
        "encrypted" if Manifest.db exists alongside Manifest.plist with encryption flag,
        "unencrypted" if Manifest.db exists without encryption,
        None if not a recognizable iTunes backup.
    """
    manifest_db = backup_dir / "Manifest.db"
    manifest_plist = backup_dir / "Manifest.plist"

    if not manifest_db.exists():
        return None

    # If Manifest.plist exists, check for encryption markers
    if manifest_plist.exists():
        try:
            import plistlib

            with open(manifest_plist, "rb") as f:
                plist = plistlib.load(f)
            if plist.get("IsEncrypted", False):
                return "encrypted"
        except Exception:
            pass

    # Manifest.db exists but no encryption flag => unencrypted
    return "unencrypted"


def _compute_file_id(domain: str, relative_path: str) -> str:
    """Compute the SHA-1 hash used as file ID in iTunes backups.

    iTunes uses sha1(domain + '-' + relativePath) as the on-disk filename.
    """
    raw = f"{domain}-{relative_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def extract_from_unencrypted_backup(
    backup_dir: Path, output_dir: Path
) -> dict[str, Any]:
    """Extract WhatsApp files from an unencrypted iTunes backup.

    Parses Manifest.db to find WhatsApp files, then copies them from the
    hashed storage structure to the output directory preserving relative paths.

    Returns:
        Dict with extraction stats: files_extracted, chat_storage_found.
    """
    manifest_db = backup_dir / "Manifest.db"
    if not manifest_db.exists():
        raise FileNotFoundError(f"Manifest.db not found in {backup_dir}")

    conn = sqlite3.connect(str(manifest_db))
    try:
        # Query for all WhatsApp files (flags=1 means regular file)
        rows = conn.execute(
            """
            SELECT fileID, domain, relativePath
            FROM Files
            WHERE domain LIKE ?
            AND flags = 1
            ORDER BY relativePath
            """,
            (WHATSAPP_DOMAIN_LIKE,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"files_extracted": 0, "chat_storage_found": False}

    output_dir.mkdir(parents=True, exist_ok=True)

    files_extracted = 0
    chat_storage_found = False

    for file_id, domain, relative_path in rows:
        # Source file in hashed storage: <backup>/<first2chars>/<fileID>
        src = backup_dir / file_id[:2] / file_id

        if not src.exists():
            continue

        # Destination preserving relative path
        dest = output_dir / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        files_extracted += 1

        if relative_path == CHAT_STORAGE_RELATIVE:
            chat_storage_found = True

    return {
        "files_extracted": files_extracted,
        "chat_storage_found": chat_storage_found,
    }


def extract_from_encrypted_backup(
    backup_dir: Path, output_dir: Path, passphrase: str
) -> dict[str, Any]:
    """Extract WhatsApp files from an encrypted iTunes backup.

    Uses iphone_backup_decrypt to decrypt and extract files.

    Returns:
        Dict with extraction stats: files_extracted, chat_storage_found.
    """
    from iphone_backup_decrypt import EncryptedBackup, DomainLike, RelativePath

    backup = EncryptedBackup(
        backup_directory=str(backup_dir), passphrase=passphrase
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract ChatStorage.sqlite
    chat_storage_found = False
    try:
        chat_db_bytes = backup.extract_file_as_bytes(
            RelativePath.WHATSAPP_MESSAGES,
            domain_like=DomainLike.WHATSAPP,
        )
        chat_storage_dest = output_dir / CHAT_STORAGE_RELATIVE
        chat_storage_dest.write_bytes(chat_db_bytes)
        chat_storage_found = True
    except FileNotFoundError:
        pass

    # Extract all WhatsApp media/attachments
    media_dir = output_dir / "Message" / "Media"
    media_dir.mkdir(parents=True, exist_ok=True)

    n_media = backup.extract_files(
        relative_paths_like="Message/Media/%.%",
        domain_like=DomainLike.WHATSAPP,
        output_folder=str(media_dir),
        preserve_folders=True,
    )

    files_extracted = n_media + (1 if chat_storage_found else 0)

    return {
        "files_extracted": files_extracted,
        "chat_storage_found": chat_storage_found,
    }


def extract_backup(
    backup_dir: Path,
    output_dir: Path,
    password: str | None = None,
) -> dict[str, Any]:
    """Unified entry point: detect backup type and extract WhatsApp data.

    Args:
        backup_dir: Path to the iTunes backup directory.
        output_dir: Where to write extracted files.
        password: Backup encryption passphrase (required for encrypted backups).

    Returns:
        Dict with extraction stats: files_extracted, chat_storage_found.

    Raises:
        FileNotFoundError: If backup_dir does not exist or is not a valid backup.
        ValueError: If backup is encrypted but no password provided.
    """
    if not backup_dir.exists():
        raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

    backup_type = detect_backup_type(backup_dir)

    if backup_type is None:
        raise FileNotFoundError(
            f"Not a valid iTunes backup (no Manifest.db): {backup_dir}"
        )

    if backup_type == "encrypted":
        if not password:
            raise ValueError(
                "Backup is encrypted. Provide a password with --password."
            )
        return extract_from_encrypted_backup(backup_dir, output_dir, password)

    return extract_from_unencrypted_backup(backup_dir, output_dir)
