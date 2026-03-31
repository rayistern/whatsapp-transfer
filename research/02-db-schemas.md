# WhatsApp Database Schema Research

## 1. iOS ChatStorage.sqlite Schema

**Location:** `/private/var/mobile/Applications/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite`

The database uses Apple's **Core Data** framework, so all tables and columns follow the `Z` prefix convention. It contains approximately 18 tables.

### ZWAMESSAGE (Messages)

| Column | Type | Description |
|--------|------|-------------|
| `Z_PK` | INTEGER | Primary key |
| `Z_ENT` | INTEGER | Core Data entity type |
| `Z_OPT` | INTEGER | Core Data optimistic locking counter |
| `ZCHATSESSION` | INTEGER | FK to `ZWACHATSESSION.Z_PK` |
| `ZGROUPMEMBER` | INTEGER | FK to `ZWAGROUPMEMBER.Z_PK` |
| `ZMESSAGETYPE` | INTEGER | 0=text, 1=image, 2=video, 3=voice, 4=contact, 5=location, 6=group event, 7=URL, 8=document |
| `ZISFROMME` | INTEGER | 0=incoming, 1=outgoing |
| `ZMESSAGEDATE` | REAL | Timestamp (Apple Cocoa epoch: seconds since 2001-01-01) |
| `ZSENTDATE` | REAL | Sent timestamp (same epoch) |
| `ZTEXT` | TEXT | Message body (empty for media messages) |
| `ZFROMJID` | TEXT | Sender WhatsApp JID |
| `ZTOJID` | TEXT | Recipient WhatsApp JID |
| `ZMEDIASECTIONID` | TEXT | Media date section grouping |
| `ZPUSHNAME` | TEXT | Sender display name |
| `ZMEDIAITEM` | INTEGER | FK to `ZWAMEDIAITEM.Z_PK` |
| `ZMESSAGESTATUS` | INTEGER | Delivery/read status |
| `ZMESSAGEERRORSTATUS` | INTEGER | Error status |
| `ZSTARRED` | INTEGER | Starred flag |
| `ZSORT` | INTEGER | Order in conversation (gaps indicate deleted messages) |
| `ZFLAGS` | INTEGER | Message state flags |
| `ZGROUPEVENTTYPE` | INTEGER | Group event type |
| `ZDOCID` | INTEGER | FK to ChatSearchV3 FTS index |
| `ZSPOTLIGHTSTATUS` | INTEGER | Spotlight search indexing |
| `ZENCRETRYCOUNT` | INTEGER | Encryption retry counter |
| `ZDATAITEMVERSION` | INTEGER | Data version |
| `ZCHILDMESSAGESDELIVEREDCOUNT` | INTEGER | Delivered count for broadcast |
| `ZCHILDMESSAGESPLAYEDCOUNT` | INTEGER | Played count |
| `ZCHILDMESSAGESREADCOUNT` | INTEGER | Read count |
| `ZFILTEREDRECIPIENTCOUNT` | INTEGER | Filtered recipient count |
| `ZLASTSESSION` | INTEGER | Last session reference |
| `ZSTANZAID` | TEXT | Message stanza ID (unique key) |

### ZWAMEDIAITEM (Media Attachments)

| Column | Type | Description |
|--------|------|-------------|
| `Z_PK` | INTEGER | Primary key |
| `ZMESSAGE` | INTEGER | FK to `ZWAMESSAGE.Z_PK` |
| `ZMEDIALOCALPATH` | TEXT | Local file path (under `Message/Media/`) |
| `ZTHUMBNAILLOCALPATH` | TEXT | Thumbnail file path |
| `ZMEDIAURL` | TEXT | Download URL for encrypted media |
| `ZMEDIAKEY` | BLOB | Protobuf-encoded blob; first field (tag `0x0a`, 32 bytes) is the AES encryption key |
| `ZMEDIAURLDATE` | REAL | URL timestamp (Apple Cocoa epoch) |
| `ZFILESIZE` | INTEGER | File size in bytes |
| `ZMOVIEDURATION` | INTEGER | Duration in seconds (video/audio) |
| `ZVCARDSTRING` | TEXT | MIME type of attachment |
| `ZVCARDNAME` | TEXT | Media file IDs, contact names, or sender ID for deleted messages |
| `ZLATITUDE` | REAL | Latitude (or image width for photos) |
| `ZLONGITUDE` | REAL | Longitude (or image height for photos) |
| `ZTITLE` | TEXT | Media caption; for deleted messages contains an alphanumeric value |

### ZWACHATSESSION (Chat Sessions)

| Column | Type | Description |
|--------|------|-------------|
| `Z_PK` | INTEGER | Primary key |
| `ZSESSIONTYPE` | INTEGER | 0=private, 1=group, 2=broadcast, 3=status |
| `ZCONTACTJID` | TEXT | JID: `@s.whatsapp.net` (contacts), `@g.us` (groups), `@status` |
| `ZPARTNERNAME` | TEXT | Contact or group name |
| `ZMESSAGECOUNTER` | INTEGER | Total message count |
| `ZUNREADCOUNT` | INTEGER | Unread message count |
| `ZLASTMESSAGEDATE` | REAL | Last message timestamp |
| `ZLASTMESSAGE` | INTEGER | FK to last ZWAMESSAGE |

### ZWAGROUPMEMBER (Group Members)

| Column | Type | Description |
|--------|------|-------------|
| `Z_PK` | INTEGER | Primary key |
| `Z_ENT` | INTEGER | Entity type |
| `Z_OPT` | INTEGER | Optimistic locking |
| `ZMEMBERJID` | TEXT | Member's WhatsApp JID |
| `ZCHATSESSION` | INTEGER | FK to ZWACHATSESSION |
| `ZCONTACTNAME` | TEXT | Display name |

### Other Tables
- **ZWAPROFILEPUSHNAME** -- Maps JIDs to display names
- **ZWAPROFILEPICTUREITEM** -- Profile pictures
- **Z_PRIMARYKEY** -- Database metadata (entity counts)
- **ZWAMESSAGEINFO** -- Message delivery/read receipt info

---

## 2. Android msgstore.db Schema

**Location:** `/data/data/com.whatsapp/databases/msgstore.db`

### message (Messages -- newer schema)

```sql
CREATE TABLE message (
  _id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_row_id INTEGER NOT NULL,       -- FK to chat._id
  from_me INTEGER NOT NULL,            -- 0=incoming, 1=outgoing
  key_id TEXT NOT NULL,                -- unique message key
  sender_jid_row_id INTEGER,           -- FK to jid._id
  status INTEGER,                      -- 0=unsent,1=uploading,2=uploaded,3=sent,4=received_server,5=received_target,6=never_send
  broadcast INTEGER,
  recipient_count INTEGER,
  participant_hash TEXT,
  origination_flags INTEGER,
  origin INTEGER,
  timestamp INTEGER,                   -- Unix epoch in milliseconds
  received_timestamp INTEGER,
  receipt_server_timestamp INTEGER,
  message_type INTEGER,                -- 0=text,1=image,2=audio,3=video,4=contact,5=location,...
  text_data TEXT,
  starred INTEGER,
  lookup_tables INTEGER,
  sort_id INTEGER NOT NULL DEFAULT 0
);
```

### chat (Conversations)

```sql
CREATE TABLE chat (
  _id INTEGER PRIMARY KEY AUTOINCREMENT,
  jid_row_id INTEGER UNIQUE,           -- FK to jid._id
  hidden INTEGER,
  subject TEXT,
  created_timestamp INTEGER,
  display_message_row_id INTEGER,
  last_message_row_id INTEGER,
  last_read_message_row_id INTEGER,
  archived INTEGER,
  sort_timestamp INTEGER,
  mod_tag INTEGER,
  unseen_message_count INTEGER,
  ephemeral_expiration INTEGER,
  ephemeral_setting_timestamp INTEGER,
  -- ... additional columns for read receipts, spam detection, etc.
);
```

### jid (WhatsApp Identifiers)

```sql
CREATE TABLE jid (
  _id INTEGER PRIMARY KEY AUTOINCREMENT,
  user TEXT NOT NULL,                   -- phone number
  server TEXT NOT NULL,                 -- "s.whatsapp.net" or "g.us"
  agent INTEGER,
  device INTEGER,
  type INTEGER,
  raw_string TEXT
);
```

### message_media (Media Metadata)

```sql
CREATE TABLE message_media (
  message_row_id INTEGER PRIMARY KEY,  -- FK to message._id
  chat_row_id INTEGER,
  file_path TEXT,                       -- relative path to media file
  file_size INTEGER,
  mime_type TEXT,
  media_key BLOB,                      -- AES decryption key
  media_key_timestamp INTEGER,
  width INTEGER,
  height INTEGER,
  message_url TEXT,                     -- download URL for encrypted media
  media_name TEXT,
  file_hash TEXT,                       -- SHA-256 of decrypted file
  enc_file_hash TEXT,                   -- SHA-256 of encrypted file
  media_duration INTEGER,
  page_count INTEGER,
  direct_path TEXT,
  file_length INTEGER,
  transferred INTEGER,
  transcoded INTEGER,
  gif_attribution INTEGER,
  is_animated_sticker INTEGER,
  original_file_hash TEXT,
  thumbnail_height_width_ratio REAL,
  has_streaming_sidecar INTEGER,
  first_scan_sidecar BLOB,
  first_scan_length INTEGER,
  suspicious_content INTEGER,
  trim_from INTEGER,
  trim_to INTEGER,
  face_x INTEGER,
  face_y INTEGER,
  mute_video INTEGER DEFAULT 0
);
```

### message_location

```sql
CREATE TABLE message_location (
  message_row_id INTEGER PRIMARY KEY,
  chat_row_id INTEGER,
  latitude REAL,
  longitude REAL,
  place_name TEXT,
  place_address TEXT,
  url TEXT,
  live_location_share_duration INTEGER,
  live_location_sequence_number INTEGER,
  live_location_final_latitude REAL,
  live_location_final_longitude REAL,
  live_location_final_timestamp INTEGER,
  map_download_status INTEGER
);
```

### message_quoted (Replies)

```sql
CREATE TABLE message_quoted (
  message_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_row_id INTEGER NOT NULL,
  parent_message_chat_row_id INTEGER NOT NULL,
  from_me INTEGER NOT NULL,
  sender_jid_row_id INTEGER,
  key_id TEXT NOT NULL,
  timestamp INTEGER,
  message_type INTEGER,
  origin INTEGER,
  text_data TEXT,
  lookup_tables INTEGER
);
```

### Other Tables
- **message_thumbnail** -- `message_row_id` (PK), `thumbnail` (BLOB)
- **media_hash_thumbnail** -- `media_hash` (PK), `thumbnail` (BLOB)
- **group_participants** -- `gjid`, `jid`, `admin`, `pending`, `sent_sender_key`
- **message_vcard** -- Contact card attachments
- **message_system** -- System messages (group changes, etc.)
- **message_ephemeral** -- Disappearing message tracking
- **call_log** -- Call history
- **labels** -- Custom labels

### Legacy Schema (older WhatsApp)
Older versions used a single **`messages`** table (plural) with all media columns inline: `key_remote_jid`, `key_from_me`, `key_id`, `data`, `timestamp`, `media_url`, `media_mime_type`, `media_wa_type`, `media_size`, `media_name`, `media_caption`, `media_hash`, `media_duration`, `latitude`, `longitude`, `thumb_image`, `remote_resource`, `received_timestamp`, `send_timestamp`, `raw_data`, `starred`, `quoted_row_id`, `mentioned_jids`, etc.

---

## 3. Key Differences Between iOS and Android Schemas

### Timestamp Storage

| Platform | Epoch | Unit | Conversion to Unix |
|----------|-------|------|-------------------|
| **iOS** | Apple Cocoa (2001-01-01 00:00:00 UTC) | Seconds (float) | `unix_ts = cocoa_ts + 978307200` |
| **Android** | Unix (1970-01-01 00:00:00 UTC) | Milliseconds (integer) | Already Unix; divide by 1000 for seconds |

### Column Name Mappings

| Concept | iOS (ChatStorage.sqlite) | Android (msgstore.db) |
|---------|--------------------------|----------------------|
| Primary key | `Z_PK` | `_id` |
| Message text | `ZWAMESSAGE.ZTEXT` | `message.text_data` |
| Message direction | `ZISFROMME` | `from_me` |
| Message type | `ZMESSAGETYPE` | `message_type` |
| Message timestamp | `ZMESSAGEDATE` | `timestamp` |
| Chat FK | `ZCHATSESSION` (FK to `ZWACHATSESSION.Z_PK`) | `chat_row_id` (FK to `chat._id`) |
| Sender ID | `ZFROMJID` (inline text) | `sender_jid_row_id` (FK to `jid._id`) |
| Message unique key | `ZSTANZAID` | `key_id` |
| Starred | `ZSTARRED` | `starred` |
| Media local path | `ZWAMEDIAITEM.ZMEDIALOCALPATH` | `message_media.file_path` |
| Media URL | `ZWAMEDIAITEM.ZMEDIAURL` | `message_media.message_url` |
| Media key | `ZWAMEDIAITEM.ZMEDIAKEY` | `message_media.media_key` |
| MIME type | `ZWAMEDIAITEM.ZVCARDSTRING` | `message_media.mime_type` |
| File size | `ZWAMEDIAITEM.ZFILESIZE` | `message_media.file_size` |
| Duration | `ZWAMEDIAITEM.ZMOVIEDURATION` | `message_media.media_duration` |
| File hash | N/A (in ZMEDIAKEY blob) | `message_media.file_hash` |
| Media caption | `ZWAMEDIAITEM.ZTITLE` | (in `text_data` or legacy `media_caption`) |

### Message Type Encoding

| Type | iOS `ZMESSAGETYPE` | Android `message_type` |
|------|-------------------|----------------------|
| Text | 0 | 0 |
| Image | 1 | 1 |
| Video | 2 | 3 |
| Voice/Audio | 3 | 2 |
| Contact | 4 | 4 |
| Location | 5 | 5 |
| Group event | 6 | (system table) |
| URL/link | 7 | (varies) |
| Document | 8 | (varies) |

Note: **Audio and Video codes are swapped** between iOS and Android.

### Structural Differences
- **iOS** stores everything in a single `ChatStorage.sqlite` using Core Data conventions (Z-prefixed columns)
- **Android** uses a normalized schema with separate tables (`message`, `message_media`, `message_location`, `message_quoted`, `message_vcard`, `message_thumbnail`)
- **iOS** stores sender JID as inline text; **Android** normalizes JIDs into a separate `jid` table referenced by row ID
- **iOS** uses a single `ZWAMEDIAITEM` table for all media metadata; **Android** splits across `message_media`, `message_location`, `message_vcard`

---

## 4. Media File Storage

### Android File Paths

**Modern (Android 11+):** `/storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Media/`
**Older:** `/sdcard/WhatsApp/Media/`

Subfolder structure:
```
WhatsApp/
  Media/
    WhatsApp Images/         # Photos (received)
    WhatsApp Images/Sent/    # Photos (sent)
    WhatsApp Video/          # Videos
    WhatsApp Video/Sent/
    WhatsApp Voice Notes/    # Voice notes, organized by date folders
    WhatsApp Audio/          # Audio files
    WhatsApp Documents/      # Documents
    .Statuses/               # Viewed statuses (24h TTL)
  Databases/                 # Encrypted backups (.cryptNN)
```

**Naming convention:** `{PREFIX}-{YYYYMMDD}-WA{NNNN}.{ext}`
- `IMG-20230704-WA0027.jpg` -- image received July 4, 2023
- `VID-20230704-WA0001.mp4` -- video
- `AUD-20230704-WA0001.opus` -- audio
- `PTT-20230704-WA0001.opus` -- voice note (push-to-talk)

Counter increments per day; gaps in sequence indicate deleted and re-sent files.

### iOS File Paths

**Internal:** `/private/var/mobile/Applications/group.net.whatsapp.WhatsApp.shared/Message/Media/`

Media is stored within the app sandbox and is not accessible via the iOS Files app. Media referenced by `ZWAMEDIAITEM.ZMEDIALOCALPATH` is relative to the app's data directory. Users can optionally save to the Photos library ("Save to Camera Roll" setting).

---

## 5. WhatsApp Protobuf Usage

WhatsApp uses **Protocol Buffers (proto2 syntax)** extensively. The `.proto` definitions have been reverse-engineered from WhatsApp Web and are available in the [wa-proto](https://github.com/wppconnect-team/wa-proto) repository.

### Core Message Structure

The top-level `Message` type uses a oneof-like pattern:

| Field # | Field Name | Type |
|---------|-----------|------|
| 1 | `conversation` | string (plain text) |
| 3 | `imageMessage` | ImageMessage |
| 4 | `contactMessage` | ContactMessage |
| 5 | `locationMessage` | LocationMessage |
| 7 | `documentMessage` | DocumentMessage |
| 8 | `audioMessage` | AudioMessage |
| 9 | `videoMessage` | VideoMessage |
| 17 | `contextInfo` | ContextInfo |
| 26 | `stickerMessage` | StickerMessage |

### Media Message Common Fields

All media types share a similar structure:

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | CDN download URL |
| `mimetype` | string | MIME type |
| `fileSha256` | bytes | SHA-256 of decrypted file |
| `fileLength` | uint64 | File size |
| `mediaKey` | bytes | 32-byte AES-256 encryption key |
| `directPath` | string | CDN direct path |
| `jpegThumbnail` | bytes | Inline JPEG thumbnail |

**ImageMessage** adds: `caption`, `height`, `width`, `viewOnce`, `imageSourceType`
**VideoMessage** adds: `seconds`, `videoHeight`, `videoWidth`, `gifPlayback`
**AudioMessage** adds: `seconds`, `ptt` (push-to-talk flag), `waveform`
**DocumentMessage** adds: `title`, `fileName`, `pageCount`, `caption`

### Media Key in iOS ZMEDIAKEY

The `ZMEDIAKEY` BLOB in iOS is itself a protobuf-encoded message. The first field (tag `0x0a`, length `0x20`=32 bytes) contains the actual AES decryption key.

---

## 6. Encryption Layer

### iOS Local Database
- `ChatStorage.sqlite` is **not encrypted with SQLCipher** when accessed from an iTunes/Finder backup. It is a plain SQLite file within the backup data.
- The iOS sandbox protects it at the OS level. When extracted from an encrypted iOS backup, you first need the backup password to decrypt the backup itself (PBKDF2 with SHA256 then SHA1, using DPSL/DPIC and ITER/SALT parameters).

### Android Local Database
- `msgstore.db` in `/data/data/com.whatsapp/databases/` is accessible only to the WhatsApp app (Android sandbox). On a rooted device it is a plain SQLite file.
- **Backup encryption** uses `.cryptNN` format (crypt12, crypt14, crypt15). The encryption key is stored at `/data/data/com.whatsapp/files/key` (crypt14) or `/data/data/com.whatsapp/files/encrypted_backup.key` (crypt15/E2EE backups).
- Historically, WhatsApp used a static key across all installations, later switching to a derived key. Current versions use AES-256-GCM.

### Android Backup Key Derivation
- **crypt12/crypt14**: Key file contains the raw encryption key. The key must be extracted from the app's sandbox (requires root or ADB backup exploit).
- **crypt15 (E2EE)**: Uses the OPAQUE protocol (Password-Authenticated Key Exchange). The user's password derives `OPAQUE_K`, which decrypts the stored backup key, which then decrypts the backup.

### WhatsApp Desktop
- Uses SQLCipher for its local database. On Windows with UEFI, the decryption values may be stored in UEFI variables rather than the filesystem.

### Media Encryption
- Media files on WhatsApp CDN are encrypted with AES-256-CBC. The `media_key` (32 bytes) from the database is used with HKDF to derive the actual AES key and IV. The `fileSha256` field enables integrity verification after decryption.

---

## Key Tools and References

- [wa-crypt-tools](https://github.com/ElDavoo/wa-crypt-tools) -- Decrypt `.crypt12/.crypt14/.crypt15` Android backups
- [whatsapp-media-decrypt](https://github.com/ddz/whatsapp-media-decrypt) -- Decrypt media files using `media_key`
- [whatsapp-viewer](https://github.com/andreas-mausch/whatsapp-viewer) -- View Android `msgstore.db` (includes schema SQL)
- [wa-proto](https://github.com/wppconnect-team/wa-proto) -- Extracted WhatsApp protobuf definitions
- [whatsapp-key-database-extractor](https://github.com/nfaurass/whatsapp-key-database-extractor) -- Extract keys from non-rooted Android
- [iPhone-to-Android conversion gist](https://gist.github.com/paracycle/6107205) -- Schema mapping with timestamp conversion formula
