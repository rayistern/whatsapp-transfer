"""Constants for iOS -> Android schema conversion.

Sources:
- SPEC.md sections 3.1, 3.3, 6.3
- research/02-db-schemas.md
- research/06-deep-dive-remaining-gaps.md
"""

from __future__ import annotations

# Seconds between Unix epoch (1970-01-01) and Core Data epoch (2001-01-01).
CORE_DATA_EPOCH_OFFSET = 978_307_200


def ios_ts_to_android_ms(z_message_date: float) -> int:
    """Convert ZMESSAGEDATE (REAL, seconds since 2001-01-01) to Android
    integer milliseconds since Unix epoch."""
    return int((z_message_date + CORE_DATA_EPOCH_OFFSET) * 1000)


# iOS ZMESSAGETYPE -> Android message.message_type
# Note audio/video are SWAPPED between platforms. Text/image/contact/location
# happen to align. Document and system differ.
IOS_TO_ANDROID_MESSAGE_TYPE: dict[int, int] = {
    0: 0,   # text
    1: 1,   # image
    2: 3,   # iOS video -> Android video
    3: 2,   # iOS audio/voice -> Android audio
    4: 4,   # contact
    5: 5,   # location
    6: 7,   # system -> Android system (message_system table)
    7: 0,   # url (rendered as text on Android)
    8: 9,   # document
    10: 0,  # missed call / group event -> text (rare, best-effort)
    14: 15, # deleted/revoked message -> Android deleted
}


# Android message.status codes (partial — sufficient for conversion).
# 0 = received, 5 = delivered/sent, 6 = system/info.
STATUS_RECEIVED = 0
STATUS_SENT_DELIVERED = 5
STATUS_SYSTEM = 6


def android_status(ios_type: int, from_me: bool) -> int:
    if ios_type == 6:
        return STATUS_SYSTEM
    return STATUS_SENT_DELIVERED if from_me else STATUS_RECEIVED
