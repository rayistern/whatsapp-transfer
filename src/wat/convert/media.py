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
    """

    def __init__(self, reference_date: date | None = None) -> None:
        self._date = reference_date or date.today()
        self._seq: int = 0  # global counter across all media types

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
            # Voice notes: check for "ptt" in the original path
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
    """Return a usable MIME type, falling back to extension-based inference."""
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


def remap_media_path(ios_path: str | None, mime_type: str | None) -> str | None:
    """Convenience wrapper using a fresh single-use remapper.

    For batch conversions, prefer creating a MediaRemapper instance directly.
    """
    return MediaRemapper().remap(ios_path, mime_type)
