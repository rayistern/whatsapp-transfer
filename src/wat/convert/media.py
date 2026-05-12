"""Media path remapping from iOS to Android conventions.

iOS stores media at paths like:
    Media/<group-jid>/e/9/<uuid>.jpg

Android expects:
    WhatsApp Images/IMG-YYYYMMDD-WA0001.jpg
    WhatsApp Video/VID-YYYYMMDD-WA0001.mp4
    WhatsApp Audio/AUD-YYYYMMDD-WA0001.opus
    WhatsApp Voice Notes/PTT-YYYYMMDD-WA0001.opus
    WhatsApp Documents/original_filename.pdf
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wat.model import Message

# Extension mapping for common MIME types when the original extension is missing
_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "audio/ogg": ".opus",
    "audio/mpeg": ".mp3",
    "audio/aac": ".aac",
    "audio/opus": ".opus",
    "application/pdf": ".pdf",
}

# Extension -> MIME type fallback when mime_type is None or unrecognised
_EXT_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".3gp": "video/3gpp",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".aac": "audio/aac",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class MediaRemapper:
    """Stateful remapper that tracks per-date sequence counters.

    Create one instance per conversion run so counters stay consistent.

    Android WhatsApp naming convention: media files are named with a prefix
    (IMG, VID, AUD, PTT), followed by a date stamp and a zero-padded
    sequence number (e.g. IMG-20250413-WA0001.jpg). The sequence counter
    is global across all media types within a single export, matching how
    WhatsApp Android itself assigns "WA" numbers. Using a per-run counter
    (rather than per-type or per-date) ensures no filename collisions.
    """

    def __init__(self, reference_date: date | None = None) -> None:
        self._date = reference_date or date.today()
        # Global counter across all media types — Android WhatsApp uses a single
        # monotonic "WA" sequence number, not per-type counters.
        self._seq: int = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def remap(self, ios_path: str | None, mime_type: str | None) -> str | None:
        """Convert an iOS media path to an Android-style path.

        Returns None if *ios_path* is None.
        """
        if ios_path is None:
            return None

        # Resolve effective MIME type
        effective_mime = _resolve_mime(ios_path, mime_type)
        date_str = self._date.strftime("%Y%m%d")
        seq = self._next_seq()

        if effective_mime is not None and effective_mime.startswith("audio/"):
            # Voice notes: WhatsApp iOS stores push-to-talk (voice note) files
            # with "ptt" in the path (e.g. ".../ptt/..." or filename containing
            # "ptt"). This is a WhatsApp convention across both platforms —
            # "PTT" stands for Push-To-Talk. Detecting it in the path is the
            # most reliable way to distinguish voice notes from regular audio
            # attachments, since both share the same MIME types.
            if "ptt" in ios_path.lower():
                return f"WhatsApp Voice Notes/PTT-{date_str}-WA{seq:04d}.opus"
            ext = _ext_for(ios_path, effective_mime)
            return f"WhatsApp Audio/AUD-{date_str}-WA{seq:04d}{ext}"

        if effective_mime is not None and effective_mime.startswith("image/"):
            ext = _ext_for(ios_path, effective_mime)
            return f"WhatsApp Images/IMG-{date_str}-WA{seq:04d}{ext}"

        if effective_mime is not None and effective_mime.startswith("video/"):
            ext = _ext_for(ios_path, effective_mime)
            return f"WhatsApp Video/VID-{date_str}-WA{seq:04d}{ext}"

        if effective_mime is not None and effective_mime.startswith("application/"):
            # Documents keep their original filename
            original_name = os.path.basename(ios_path)
            return f"WhatsApp Documents/{original_name}"

        # Fallback: try to infer from extension
        _, ext_raw = os.path.splitext(ios_path)
        ext_lower = ext_raw.lower()
        if ext_lower in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            return f"WhatsApp Images/IMG-{date_str}-WA{seq:04d}{ext_lower}"
        if ext_lower in (".mp4", ".3gp"):
            return f"WhatsApp Video/VID-{date_str}-WA{seq:04d}{ext_lower}"
        if ext_lower in (".ogg", ".opus", ".mp3", ".aac"):
            return f"WhatsApp Audio/AUD-{date_str}-WA{seq:04d}{ext_lower}"

        # Documents catch-all: keep original filename
        original_name = os.path.basename(ios_path)
        return f"WhatsApp Documents/{original_name}"


def _resolve_mime(ios_path: str, mime_type: str | None) -> str | None:
    """Return a usable MIME type, falling back to extension-based inference.

    Why the fallback: iOS stores the MIME type in ZVCARDSTRING (a misnamed
    column), but it can be NULL or contain non-MIME values for some message
    types. When the MIME type is missing or malformed (no "/" separator),
    we infer it from the file extension using _EXT_TO_MIME. This two-tier
    approach maximizes the chance of correct media categorization.
    """
    if mime_type and "/" in mime_type:
        return mime_type
    # Try to infer from extension
    _, ext = os.path.splitext(ios_path)
    return _EXT_TO_MIME.get(ext.lower())


def _ext_for(ios_path: str, mime_type: str) -> str:
    """Pick the best file extension for the output file."""
    # Prefer the original extension if it exists and looks reasonable
    _, ext_raw = os.path.splitext(ios_path)
    if ext_raw:
        return ext_raw.lower()
    # Fall back to MIME -> extension lookup
    return _MIME_TO_EXT.get(mime_type, "")


def copy_media_files(
    ios_media_dir: Path,
    android_media_dir: Path,
    remapper: MediaRemapper,
    messages: list["Message"],
) -> dict:
    """Copy iOS media files to Android directory structure.

    Parameters
    ----------
    ios_media_dir:
        The iOS extracted directory containing Message/Media/... (i.e. the parent
        of ``Message/``).  Source paths are resolved as ``ios_media_dir / local_path``.
    android_media_dir:
        Target root for the Android ``WhatsApp/Media/`` tree.
    remapper:
        A :class:`MediaRemapper` instance (should be the *same* one used during
        ``convert_corpus`` so paths match the DB).
    messages:
        List of :class:`Message` objects from the parsed corpus.

    Returns
    -------
    dict
        ``{copied: int, skipped: int, missing: int}``
    """
    import shutil

    copied = 0
    skipped = 0
    missing = 0

    for msg in messages:
        if msg.media is None or msg.media.local_path is None:
            continue

        android_path = remapper.remap(msg.media.local_path, msg.media.mime_type)
        if android_path is None:
            skipped += 1
            continue

        src = ios_media_dir / msg.media.local_path
        dest = android_media_dir / android_path

        if not src.exists():
            missing += 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        copied += 1

    return {"copied": copied, "skipped": skipped, "missing": missing}


def remap_media_path(ios_path: str | None, mime_type: str | None) -> str | None:
    """Convenience wrapper using a fresh single-use remapper.

    For batch conversions, prefer creating a MediaRemapper instance directly.
    """
    return MediaRemapper().remap(ios_path, mime_type)
