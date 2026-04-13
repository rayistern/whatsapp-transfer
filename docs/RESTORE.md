# Restoring the converted backup to Android

## Output tree produced by `wat run`

```
out/
  WhatsApp/
    Databases/
      msgstore.db
      msgstore.db.crypt15   # only if --key was provided
    Media/
      WhatsApp Images/
      WhatsApp Video/
      WhatsApp Voice Notes/
      WhatsApp Audio/
      WhatsApp Documents/
```

---

## Option 1: Encrypted backup restore (non-rooted)

Use this method on any stock Android device. It uses the `.crypt15` file so
WhatsApp's built-in restore flow handles the import.

### Prerequisites

- The `wat run` or `wat encrypt` command was run with `--key` to produce a
  `.crypt15` file.
- The target Android device has the same phone number as the source iPhone.

### Steps

1. **Uninstall WhatsApp** on the Android device (or use a device where WhatsApp
   has not been set up yet).

2. **Copy the output tree** to the device. Place the `WhatsApp/` directory at:
   ```
   Android/media/com.whatsapp/WhatsApp/
   ```
   You can use USB/MTP file transfer or ADB:
   ```bash
   adb push out/WhatsApp/ /storage/emulated/0/Android/media/com.whatsapp/WhatsApp/
   ```
   Make sure both `Databases/msgstore.db.crypt15` and the `Media/` subdirectories
   are in place.

3. **Install WhatsApp** from the Google Play Store.

4. **Open WhatsApp** and verify using the same phone number that was registered
   on the source iPhone. Number mismatch will prevent restore.

5. **Tap "Restore"** when prompted with "Local backup found" or "Restore from
   backup."

6. **Validate** after restore completes:
   - Chat list appears with correct names
   - Message order is preserved (sort_id)
   - Sent/received sides are correct
   - Timestamps match the originals
   - Media thumbnails load and media plays back
   - Group membership is intact
   - Quoted replies reference the correct messages

---

## Option 2: Rooted device restore (direct DB push)

Use this method during development or on a rooted Android device/emulator. It
bypasses encryption entirely and pushes the unencrypted `msgstore.db` directly
into WhatsApp's private data directory.

### Steps

1. **Find the WhatsApp UID** on the device:
   ```bash
   adb shell stat -c '%U' /data/data/com.whatsapp
   ```
   This returns something like `u0_a123`.

2. **Force-stop WhatsApp** to release database locks:
   ```bash
   adb root
   adb shell am force-stop com.whatsapp
   ```

3. **Push the database** to WhatsApp's data directory:
   ```bash
   adb push out/WhatsApp/Databases/msgstore.db \
       /data/data/com.whatsapp/databases/msgstore.db
   ```

4. **Fix ownership** so WhatsApp can read the file (replace `u0_a123` with the
   actual UID from step 1):
   ```bash
   adb shell chown u0_a123:u0_a123 /data/data/com.whatsapp/databases/msgstore.db
   adb shell chmod 660 /data/data/com.whatsapp/databases/msgstore.db
   ```

5. **Copy media files** (optional but needed for media playback):
   ```bash
   adb push out/WhatsApp/Media/ \
       /storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Media/
   ```

6. **Restart WhatsApp**:
   ```bash
   adb shell am start -n com.whatsapp/.Main
   ```

7. **Validate** that chats, messages, and media appear correctly.

---

## Troubleshooting

### "No backup found" during WhatsApp setup

- Verify the `.crypt15` file is at exactly
  `Android/media/com.whatsapp/WhatsApp/Databases/msgstore.db.crypt15`.
  On some Android versions, WhatsApp may also check the legacy path at
  `WhatsApp/Databases/` on the root of internal storage.
- Ensure the file is named `msgstore.db.crypt15` (not a variant like
  `msgstore-2024-01-01.db.crypt15`).
- Check that the phone number matches the one used on the source iPhone.

### WhatsApp crashes or shows empty chats after restore

- The database schema may be incompatible with the installed WhatsApp version.
  This tool targets the 2022+ normalized schema. Make sure you are running a
  recent version of WhatsApp from the Play Store.
- On rooted restore, double-check file ownership and permissions (`chown` and
  `chmod` in Option 2).

### Media shows "download failed" or missing thumbnails

- Verify media files were copied to the correct subdirectories under
  `WhatsApp/Media/` (e.g., `WhatsApp Images/`, `WhatsApp Video/`).
- WhatsApp rebuilds its thumbnail cache and full-text search index on first
  launch after restore. This may take a few seconds.

### "ADB push" permission denied

- Use `adb root` before pushing to `/data/data/com.whatsapp/`. This requires
  a rooted device or a rooted AVD emulator image.
- For non-rooted devices, use Option 1 (encrypted backup restore) instead.

### Key file issues

- The key file must be exactly 32 bytes of raw binary data. If your key file is
  a hex string or base64, convert it first:
  ```bash
  xxd -r -p hex_key.txt key.bin        # from hex
  base64 -d b64_key.txt > key.bin      # from base64
  ```
- The key must correspond to the WhatsApp account on the target device.

---

## Known Limitations (MVP)

- Reactions, edits, polls, disappearing messages, and channels are not transferred.
  See `SPEC.md` for details.
- Full-text search index is rebuilt by WhatsApp on first open; search may be
  temporarily unavailable.
- The tool cannot merge into an existing Android WhatsApp database. It always
  creates a fresh `msgstore.db`.
