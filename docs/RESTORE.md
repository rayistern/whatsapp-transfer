# Restoring the converted backup to Android

> This document describes the **target** restore flow. The actual encryptor
> lands in Phase 7. For now it's the reference doc we build against.

## Output tree produced by `wat run`

```
out/
└── WhatsApp/
    ├── Databases/
    │   └── msgstore.db.crypt15
    └── Media/
        ├── WhatsApp Images/
        ├── WhatsApp Video/
        ├── WhatsApp Voice Notes/
        ├── WhatsApp Audio/
        └── WhatsApp Documents/
```

## Restore procedure (non-rooted, crypt15 path)

1. Uninstall WhatsApp on the target Android device (or ensure it's freshly
   installed and not yet set up).
2. Copy the `out/WhatsApp/` tree to the device at
   `Android/media/com.whatsapp/WhatsApp/` via USB / MTP / `adb push`.
3. Install WhatsApp from the Play Store.
4. Open WhatsApp, verify the same phone number that the **source** iPhone was
   registered to. (Number mismatch will prevent restore.)
5. When prompted with "Restore local backup?" tap **Restore**.
6. Validate: chat list, message order (sort_id preserved), sent/received
   sides, timestamps, media thumbnails + playback, group membership, quoted
   replies.

## Restore procedure (rooted, faster iteration loop during development)

1. On rooted device:
   ```sh
   adb root
   adb shell am force-stop com.whatsapp
   adb push msgstore.db /data/data/com.whatsapp/databases/msgstore.db
   adb shell chown u0_aXXX:u0_aXXX /data/data/com.whatsapp/databases/msgstore.db
   adb shell am start -n com.whatsapp/.Main
   ```
2. Find the correct `u0_aXXX` via `adb shell stat /data/data/com.whatsapp`.

## Known limitations (MVP)

- Reactions, edits, polls, disappearing messages, channels — see `SPEC.md §8`.
- Full-text search index is rebuilt by WhatsApp on first open; may be empty
  for a few seconds.
