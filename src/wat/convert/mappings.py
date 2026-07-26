"""Constants for iOS -> Android schema conversion.

Sources:
- SPEC.md sections 3.1, 3.3, 6.3
- research/02-db-schemas.md
- research/06-deep-dive-remaining-gaps.md
"""

from __future__ import annotations

# Seconds between Unix epoch (1970-01-01 00:00:00 UTC) and Apple Core Data
# epoch (2001-01-01 00:00:00 UTC).  This is exactly 31 years' worth of
# seconds (including leap years): 978_307_200.  iOS stores ZMESSAGEDATE
# as a float of seconds since 2001-01-01; Android stores timestamps as
# integer milliseconds since 1970-01-01.  Adding this offset converts
# Core Data seconds to Unix seconds before multiplying by 1000.
CORE_DATA_EPOCH_OFFSET = 978_307_200


def ios_ts_to_android_ms(z_message_date: float) -> int:
    """Convert ZMESSAGEDATE (REAL, seconds since 2001-01-01) to Android
    integer milliseconds since Unix epoch."""
    return int((z_message_date + CORE_DATA_EPOCH_OFFSET) * 1000)


# iOS ZMESSAGETYPE -> Android message.message_type
#
# Historical note (confirmed via research/02-db-schemas.md, April 2025):
# Audio (iOS 3) and video (iOS 2) type codes are SWAPPED between platforms.
# On iOS: 2 = video, 3 = audio.  On Android: 2 = audio, 3 = video.
# This is a deliberate divergence in WhatsApp's platform codebases, not a bug.
# Text (0), image (1), contact (4), and location (5) happen to align.
IOS_TO_ANDROID_MESSAGE_TYPE: dict[int, int] = {
    0: 0,   # text -> text
    1: 1,   # image -> image
    2: 3,   # iOS video (2) -> Android video (3) — platforms swapped these
    3: 2,   # iOS audio/voice (3) -> Android audio (2) — platforms swapped these
    4: 4,   # contact -> contact
    5: 5,   # location -> location
    6: 7,   # system -> Android system (also writes to message_system table)
    7: 0,   # url preview -> text (Android renders URLs inline in text messages)
    8: 9,   # document -> document
    # Type 10: missed call or group event on iOS. No direct Android equivalent;
    # mapped to 0 (text) as best-effort so the message is visible to the user.
    # The text content (e.g. "Missed voice call") is preserved in text_data.
    10: 0,
    # Type 14: deleted/revoked message on iOS. Android uses type 15 for its
    # "this message was deleted" marker. Mapping 14 -> 15 ensures the Android
    # client renders the standard deletion placeholder UI.
    14: 15,
}


# Android message.status codes (partial — sufficient for conversion).
# 0 = received, 5 = delivered/sent, 6 = system/info.
STATUS_RECEIVED = 0
STATUS_SENT_DELIVERED = 5
STATUS_SYSTEM = 6


def android_status(ios_type: int, from_me: bool) -> int:
    """Derive the Android ``message.status`` code from iOS message metadata.

    Android status semantics (subset used by the converter):
    - 0 (STATUS_RECEIVED): message was received from the other party.
    - 5 (STATUS_SENT_DELIVERED): message was sent by the device owner
      and delivered (we assume delivered since we're importing history).
    - 6 (STATUS_SYSTEM): system/info message (group events, encryption
      notices, etc.) — these are rendered differently by the Android UI.

    System messages (ios_type == 6) always get STATUS_SYSTEM regardless
    of direction, because Android keys its system-message rendering on
    the status column rather than the message_type column.
    """
    if ios_type == 6:
        return STATUS_SYSTEM
    return STATUS_SENT_DELIVERED if from_me else STATUS_RECEIVED
