# Deep Dive: Remaining Research Gaps

## 1. Android Restore Mechanism (CRITICAL)

### Two restore paths exist:

#### Path A: Local Backup Restore (no root)
1. WhatsApp looks for encrypted backup at: `Internal Storage/Android/media/com.whatsapp/WhatsApp/Databases/msgstore.db.crypt15` (or `.crypt14`, `.crypt12`)
2. File MUST be encrypted — WhatsApp **will not restore an unencrypted `msgstore.db`** via this path
3. WhatsApp must be freshly installed (uninstall → reinstall)
4. On launch, WhatsApp detects the backup file, prompts "Restore", and decrypts using key from WhatsApp servers
5. To restore an older backup: rename `msgstore-YYYY-MM-DD.1.db.crypt14` → `msgstore.db.crypt14` (remove the date)
6. **The crypt extension number must match** — don't change it

**Implication for our tool:** To use this path, we'd need to produce a properly encrypted `.crypt15` file. This requires the encryption key, which is tied to the user's WhatsApp account and stored on WhatsApp's servers + at `/data/data/com.whatsapp/files/key` (root needed to read). The [wa-crypt-tools](https://github.com/ElDavoo/wa-crypt-tools) library can both decrypt AND encrypt, so re-encryption is feasible if we have the key.

#### Path B: Direct Database Replacement (root required)
1. Uninstall WhatsApp, reinstall, open once then exit
2. Copy unencrypted `msgstore.db` directly to `/data/data/com.whatsapp/databases/`
3. Fix ownership: `chown -R u0_axxx:u0_axxx /data/data/com.whatsapp/databases/msgstore.db` (where `u0_axxx` is WhatsApp's user ID, found via `ls -l`)
4. Open WhatsApp, enter phone number — messages appear

**Implication:** This is the simplest path for our tool but requires root. No encryption wrapper needed. Just produce a valid `msgstore.db` SQLite file with the correct schema.

#### Path C: WazzapMigrator's Approach
WazzapMigrator converts iOS data to Android format, then instructs the user to:
1. Place converted files where WhatsApp expects local backup
2. Reinstall WhatsApp
3. WhatsApp detects "local backup" and restores

This implies WazzapMigrator produces an encrypted backup file (or mimics the format closely enough). The exact mechanism is proprietary but the Android app handles the conversion on-device, which means it likely has access to create properly formatted backup files.

### Key Gotcha: Dual Backup Conflict
When both local AND Google Drive backups exist, "WhatsApp will claim to restore your Google Drive backup...but it only restores the media files from Google Drive but at no occasion the msgstore.db." The local `msgstore.db.crypt15` file is what actually gets restored for messages. This is important — it means the local file takes precedence for chat data.

---

## 2. The Paracycle Gist (iOS→Android SQL Mapping)

The [gist](https://gist.github.com/paracycle/6107205) provides the actual SQL for converting iOS messages to Android format. Key mappings:

### Timestamp Conversion
```sql
CAST((978307200 + m.ZMESSAGEDATE) * 1000 AS INTEGER) as timestamp
```
`978307200` = seconds between Unix epoch (1970-01-01) and Core Data epoch (2001-01-01). Multiply by 1000 for milliseconds.

### Message Direction
```sql
(CASE WHEN m.ZISFROMME=1 THEN m.ZTOJID ELSE m.ZFROMJID END) as key_remote_jid
```
iOS stores both `ZFROMJID` and `ZTOJID`; Android uses `key_remote_jid` (the other party).

### Status Mapping
```sql
CASE WHEN m.ZMESSAGETYPE=6 THEN 6 
  ELSE (CASE WHEN m.ZISFROMME=1 THEN 5 ELSE 0 END) 
END as status
```
- Type 6 (group event) → status 6
- Outgoing → status 5 (delivered)
- Incoming → status 0

### Media Mapping
```sql
mi.ZMEDIAURL as media_url,
mi.ZFILESIZE as media_size,
mi.ZMEDIALOCALPATH as media_name,
mi.ZLATITUDE as latitude,
mi.ZLONGITUDE as longitude,
mi.ZTHUMBNAILLOCALPATH as thumb_image,
mi.ZMOVIEDURATION as media_duration
```

### Group Member (Sender in Groups)
```sql
gm.ZMEMBERJID as remote_resource
```

### Chat List
```sql
INSERT INTO chat_list (key_remote_jid, message_table_id)
SELECT cur.key_remote_jid, cur._id FROM messages AS cur
WHERE NOT EXISTS (
  SELECT * FROM messages AS high
  WHERE high.key_remote_jid = cur.key_remote_jid AND high._id > cur._id
)
```
Takes the highest message ID per chat as the chat list entry.

### CRITICAL: This gist targets the OLD Android schema
The gist uses the **legacy `messages` table** (singular, all columns inline). Modern WhatsApp (2022+) uses a **normalized schema** with separate tables:
- `message` (not `messages`)
- `message_media`
- `message_location`
- `message_quoted`
- `message_vcard`
- `jid` (normalized JID table)
- `chat` (not `chat_list`)

**The column mapping logic is still valid, but the target schema needs complete rewriting for modern WhatsApp.**

---

## 3. Media CDN Expiry

- WhatsApp media URLs expire after **approximately 30 days**
- If the thumbnail is still visible in the chat, the file is likely still on servers
- After expiry, media shows "Download failed" and cannot be re-downloaded
- The `media_key` (32 bytes, AES-256) and `file_hash` (SHA-256) in the database are used for decryption/verification, not for re-requesting from CDN
- `direct_path` in the database is the CDN path, but it also expires

**Implication:** Media re-download from CDN is NOT a viable strategy for transfers of older chats. Media files must be extracted from the source backup/device directly.

---

## 4. Baileys History Sync — What You Actually Get

### Event: `messaging-history.set`
Payload contains:
- `chats` — chat metadata (reverse chronological)
- `contacts` — contact info
- `messages` — actual messages (reverse chronological), as `proto.IWebMessageInfo` protobuf
- `isLatest` — boolean
- `progress` — sync progress indicator
- `syncType` — type of sync (initial vs on-demand)

### Message format
Each message is `proto.IWebMessageInfo` which wraps `proto.IMessage` — the same protobuf structure used internally by WhatsApp Web. This is the **most complete representation** of a message, including all metadata.

### On-demand backfill
- Can request older messages per-chat using `fetchMessageHistory`
- Uses oldest locally stored message as anchor
- Recommended batch: 50 messages per request
- Phone must be online
- **Best-effort** — WhatsApp may not return full history
- `syncType` === `proto.HistorySync.HistorySyncType.ON_DEMAND` identifies these

### How much history?
Not precisely documented. Community reports suggest:
- Initial sync: recent messages (last few days to weeks)
- On-demand backfill: can go deeper but inconsistent
- WhatsApp controls the depth; no guarantee of completeness

### Key advantage
The protobuf format is **platform-agnostic** — it's neither iOS nor Android format. It's the canonical WhatsApp message representation. Converting from protobuf to either platform's SQLite schema is a clean, well-defined transformation.

---

## 5. Modern Message Types

### Reactions (message_add_on table, Android)
- `message_add_on_type`: 56 = emoji reaction, 68 = "keep disappearing" flag, 74 = edited message
- `message_add_on_reaction` table stores the actual emoji and sender
- `message.message_add_on_flag` changes from 0→1 when a reaction is added
- Multiple reactions on same message = multiple rows in `message_add_on`

### Message Edits
- Stored via `message_add_on_type` = 74
- `edit_version` field in message table tracks edit count
- Original text may or may not be preserved depending on version

### Polls
- Not well-documented in public forensics literature yet
- Likely stored as a special `message_type` with poll options in a related table or protobuf blob

### Communities & Channels
- Communities use a `@newsletter` JID type
- Channel messages likely stored in the same `message` table with a different JID type
- Schema may have additional tables not yet publicly documented

### Disappearing Messages
- `message_ephemeral` table tracks disappearing message settings
- `ephemeral_expiration` and `ephemeral_setting_timestamp` in `chat` table
- Messages still exist in database until explicitly cleaned up

### View-Once Media
- Special `message_type` value
- Media deleted after viewing
- Thumbnail may persist in `message_thumbnail`

### iOS equivalents
Less publicly documented. Core Data schema has equivalent fields but naming follows Z-prefix convention. The mapping for modern features (reactions, edits, polls) between platforms is the least-documented area.

---

## 6. Schema Versioning

### No single version marker
There is no clean "schema_version" field. Instead, you detect the schema by checking which tables/columns exist:

| Indicator | Old Schema | New Schema (2022+) |
|-----------|-----------|-------------------|
| Messages table | `messages` (plural) | `message` (singular) |
| Media columns | Inline in messages | Separate `message_media` table |
| JID storage | Inline `key_remote_jid` text | Normalized `jid` table + FKs |
| Chat table | `chat_list` | `chat` |
| Reactions | N/A | `message_add_on` table |
| Edit tracking | N/A | `edit_version` column |

### Detection strategy
```sql
-- Check if using modern schema
SELECT name FROM sqlite_master WHERE type='table' AND name='message';
-- If exists → modern schema (normalized)
-- If not → check for 'messages' table (legacy)
```

### WhatsApp version correlation
- The schema split (singular `message` + satellite tables) happened around WhatsApp v2.22.x (2022)
- Exact version-to-schema mapping is not publicly documented
- Both schemas may coexist in the wild — users who haven't updated, or older backups

---

## 7. Android Schema: 100+ Tables

The full `msgstore.db` contains **100+ tables** including:
- Core: `message`, `chat`, `jid`, `message_media`, `message_location`, `message_quoted`, `message_system`, `message_vcard`, `message_mentions`
- Receipts: `receipt_user`, `receipt_device`
- Add-ons: `message_add_on`, `message_add_on_reaction`
- FTS: Full-text search indexes (`wa_fts_message_table`, etc.)
- Other: templates, payments, invoices, call logs, labels, group participants, ephemeral settings, sticker tables, etc.

**For a minimum viable transfer, we likely only need to populate ~10-15 of these tables.** WhatsApp should handle missing optional tables gracefully (they'd just be empty features).

Sources:
- [XDA: Root restore of unencrypted msgstore.db](https://xdaforums.com/t/root-restore-un-encrypted-msgstore-db-in-whatsapp-2020.4114193/)
- [XDA: Manual restore with root](https://xdaforums.com/t/guide-whatsapp-manually-restore-messages-with-just-data-data-com-whatsapp-root.4066597/)
- [XDA: Local backup restore (April 2022)](https://xdaforums.com/t/whatsapp-restore-from-local-backup-working-method-april-2022.4426309/)
- [WhatsApp backup/restore process gist](https://gist.github.com/xnumad/96a4b15d63a3dad5cce2b2663f5fcd08)
- [paracycle iOS→Android SQL conversion gist](https://gist.github.com/paracycle/6107205)
- [Baileys History Sync docs](https://baileys.wiki/docs/socket/history-sync/)
- [Baileys messaging-history.set issue](https://github.com/WhiskeySockets/Baileys/issues/1934)
- [whatsapp-viewer schema SQL](https://github.com/andreas-mausch/whatsapp-viewer/blob/master/data/msgstore.db.schema.sql)
- [Belkasoft Android WhatsApp Forensics](https://belkasoft.com/android-whatsapp-forensics-analysis)
- [The Binary Hick: Updated msgstore schema](https://thebinaryhick.blog/2022/06/09/new-msgstore-who-dis-a-look-at-an-updated-whatsapp-on-android/)
- [wa-crypt-tools](https://github.com/ElDavoo/wa-crypt-tools)
