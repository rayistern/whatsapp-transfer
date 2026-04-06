# WhatsApp iPhone → Android Transfer Tool — Technical Specification

> **Status:** Pre-experiment draft. Sections 5 (Experiments) and 6 (Technical Design) will be
> updated with results before implementation begins.
>
> **Research corpus:** See `research/01` through `research/06` for full backing data.

---

## 1. Problem Statement

### What users need

When switching from iPhone to Android, users want to bring their full WhatsApp history — messages, media, group chats, starred messages — to their new device. They want it to look exactly like it did before: same order, same dates, same media playable.

### Why it's hard

WhatsApp stores data in completely different formats on each platform:

- **iOS:** `ChatStorage.sqlite` — Apple Core Data conventions, `Z`-prefixed tables, timestamps as float seconds since 2001-01-01
- **Android:** `msgstore.db` — normalized schema with 100+ tables, timestamps as integer milliseconds since 1970-01-01
- **Cloud backups are platform-locked:** iCloud backups cannot be read on Android; Google Drive backups cannot be read on iOS
- **No shared intermediate format:** WhatsApp has never published a portable export format that preserves full fidelity

The two schemas disagree on fundamentals: audio and video message type codes are swapped, sender IDs are stored inline on iOS but normalized into a separate table on Android, and the `sort` field that controls message ordering has no direct equivalent across platforms.

### Why the market is thin

- **Schema maintenance burden:** WhatsApp changes its database schema frequently. The Android schema underwent a major normalization in 2022 (singular `message` table + satellite tables replacing the old monolithic `messages` table). Any tool must continuously reverse-engineer and adapt.
- **Legal gray zone:** WhatsApp's ToS prohibit "unauthorized third-party apps." Tools like Mobitrix that install custom APKs directly violate this. The DMCA interoperability exemption (17 U.S.C. § 1201(f)) provides a defense but it's untested for this specific use case.
- **One-time purchase economics:** Each user needs the tool once. Hard to build a sustainable business.

Despite this, an estimated 10-20 million people switch between iPhone and Android annually worldwide, and WhatsApp has 2B+ users. The demand is real.

### What the official transfer gets wrong

WhatsApp's official cable transfer (available since 2021 via Samsung Smart Switch / Android 12 setup) has critical limitations:

1. **Factory reset required** — target device must be in initial setup
2. **Cannot merge** — overwrites any existing Android WhatsApp chats
3. **Sort order breaks** — WhatsApp uses a `sort` field (not timestamps) for message ordering; this gets mangled during transfer, causing messages to appear out of chronological order
4. **Media issues** — EXIF data stripped, photos appear under transfer date in gallery, some media shows as "download failed"
5. **Data loss** — call history, display names for unsaved contacts, starred messages, and payment messages are not transferred

---

## 2. Prior Art

### Commercial Tools

| Tool | Company | Approach | Key Feature | Key Weakness |
|------|---------|----------|-------------|--------------|
| **MobileTrans** | Wondershare (Shenzhen) | Desktop app, extract→convert→restore | Claims merge capability + Google Drive→iPhone | Mixed reviews (56.9/100 safety), $40/yr |
| **iCareFone** | Tenorshare (Shenzhen) | Desktop + companion app | Fast (~30 min) | Sneaky auto-renewal, occasional failures |
| **Mobitrix** | China | Custom WhatsApp APK on target | No uninstall needed | ToS violation, ban risk, archived open-source |
| **WazzapMigrator** | Indie (Italy) | iTunes extract + Android app converts | No internet permission, privacy-first | iPhone→Android only, requires technical skill |
| **Mutsapper** | Wondershare | Mobile-only, phone-to-phone | No computer needed | $30/yr, limited reviews |
| **Backuptrans** | — | Desktop, selective chat transfer | Merge + selective transfer | Direction-limited depending on version |

**Important:** Almost all "review" articles comparing these tools are written by competitor companies. Independent benchmarks are nearly nonexistent.

### Open-Source Tools

| Project | Direction | Language | Stars | Media? | Status |
|---------|-----------|----------|-------|--------|--------|
| [WhatsAppIphoneToAndroid](https://github.com/Kethen/WhatsAppIphoneToAndroid) | iOS→Android | Java | — | Yes | Archived 2021 |
| [watoi](https://github.com/residentsummer/watoi) | Android→iOS | Obj-C | 449 | No (since 2017!) | Stale |
| [mwatoi](https://github.com/mukulkadel/mwatoi) | Android→iOS | Python | 39 | No | Semi-active |
| [WhatsApp-Chat-Exporter](https://github.com/KnugiHK/WhatsApp-Chat-Exporter) | Both (export) | Python | 996 | Yes | Active |
| [wa-crypt-tools](https://github.com/ElDavoo/wa-crypt-tools) | Decrypt/encrypt | Python | 1012 | — | Active |
| [whatsmeow](https://github.com/tulir/whatsmeow) | WA Web protocol | Go | 5666 | — | Active |
| [Baileys](https://github.com/WhiskeySockets/Baileys) | WA Web protocol | TypeScript | — | — | Active |
| [wacli](https://github.com/steipete/wacli) | CLI (whatsmeow) | Go | — | Yes | Active |
| [paracycle gist](https://gist.github.com/paracycle/6107205) | iOS→Android | SQL | — | No | Outdated schema |

**Key observation:** iOS→Android has almost no open-source tooling. The only dedicated project (Kethen) is archived since 2021 and targets the legacy Android schema. The paracycle gist provides the SQL column mapping but also targets the legacy schema.

### WhatsApp Web Protocol Tools

Baileys (TypeScript) and whatsmeow (Go) implement WhatsApp's multi-device Web protocol. They receive **history sync** data when connecting as a new device:

- Data arrives as `proto.IWebMessageInfo` protobuf — platform-agnostic
- On-demand backfill can request older messages per-chat
- **Best-effort:** WhatsApp controls how much history it sends
- wacli provides a ready-made CLI with sync, backfill, search, and media download

---

## 3. Data Formats

### 3.1 iOS — ChatStorage.sqlite

**Location in iTunes backup:** `AppDomainGroup-group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite`

**Key tables:**

| Table | Purpose |
|-------|---------|
| `ZWAMESSAGE` | Messages (text, type, timestamps, sender/recipient JIDs) |
| `ZWAMEDIAITEM` | Media metadata (local path, URL, media key, dimensions, duration) |
| `ZWACHATSESSION` | Chat sessions (type: private/group/broadcast/status, JID, name) |
| `ZWAGROUPMEMBER` | Group member JIDs and display names |
| `ZWAPROFILEPUSHNAME` | JID→display name mapping |

**Critical columns in ZWAMESSAGE:**

| Column | Type | Notes |
|--------|------|-------|
| `ZMESSAGEDATE` | REAL | Seconds since 2001-01-01 (Core Data epoch) |
| `ZISFROMME` | INTEGER | 0=incoming, 1=outgoing |
| `ZMESSAGETYPE` | INTEGER | 0=text, 1=image, **2=video**, **3=voice**, 4=contact, 5=location, 6=system, 7=URL, 8=document |
| `ZTEXT` | TEXT | Message body |
| `ZFROMJID` / `ZTOJID` | TEXT | Sender/recipient JIDs (inline text) |
| `ZSTANZAID` | TEXT | Unique message ID |
| `ZSORT` | INTEGER | Display order (NOT timestamp-based) |
| `ZCHATSESSION` | INTEGER | FK → ZWACHATSESSION |
| `ZMEDIAITEM` | INTEGER | FK → ZWAMEDIAITEM |

**Media in ZWAMEDIAITEM:**
- `ZMEDIALOCALPATH` — relative path under `Message/Media/`
- `ZMEDIAKEY` — protobuf-encoded blob; first 32 bytes at tag `0x0a` = AES key
- `ZVCARDSTRING` — actually stores MIME type (confusing name)
- `ZTITLE` — media caption
- `ZLATITUDE`/`ZLONGITUDE` — location OR image dimensions (overloaded!)

### 3.2 Android — msgstore.db (Modern Schema, 2022+)

**Location:** `/data/data/com.whatsapp/databases/msgstore.db`
**Backup location:** `Android/media/com.whatsapp/WhatsApp/Databases/msgstore.db.crypt15`

**Key tables (modern normalized schema):**

| Table | Purpose |
|-------|---------|
| `message` | Core messages (text, type, timestamp, status) |
| `message_media` | Media metadata (path, MIME, dimensions, hash, key) |
| `message_location` | Geolocation data |
| `message_quoted` | Quoted/replied messages |
| `message_vcard` | Contact card attachments |
| `message_system` | System messages (group events) |
| `message_add_on` | Reactions (type 56), edits (type 74), keep-flags (type 68) |
| `chat` | Conversations |
| `jid` | Normalized JID table (phone + server + type) |
| `group_participants` | Group membership |

**Critical columns in `message`:**

| Column | Type | Notes |
|--------|------|-------|
| `timestamp` | INTEGER | Milliseconds since 1970-01-01 (Unix epoch) |
| `from_me` | INTEGER | 0=incoming, 1=outgoing |
| `message_type` | INTEGER | 0=text, 1=image, **2=audio**, **3=video**, 4=contact, 5=location, 9=document, 15=deleted |
| `text_data` | TEXT | Message body |
| `sender_jid_row_id` | INTEGER | FK → `jid._id` (normalized, not inline) |
| `key_id` | TEXT | Unique message ID |
| `chat_row_id` | INTEGER | FK → `chat._id` |
| `sort_id` | INTEGER | Display order |
| `starred` | INTEGER | Starred flag |

**Legacy schema detection:** If table `messages` (plural) exists instead of `message` (singular), you're on the pre-2022 monolithic schema.

### 3.3 Critical Differences

**Timestamp conversion:**
```
android_ts = (ios_ts + 978307200) * 1000
```
Where `978307200` = seconds between 1970-01-01 and 2001-01-01.

**Message type codes (SWAPPED for audio/video):**

| Type | iOS `ZMESSAGETYPE` | Android `message_type` |
|------|-------------------|----------------------|
| Text | 0 | 0 |
| Image | 1 | 1 |
| **Video** | **2** | **3** |
| **Audio/Voice** | **3** | **2** |
| Contact | 4 | 4 |
| Location | 5 | 5 |
| Document | 8 | 9 |

**JID storage:**
- iOS: inline text in `ZFROMJID`/`ZTOJID` columns
- Android: normalized `jid` table, referenced by `sender_jid_row_id` FK

**Message direction → remote JID:**
```sql
-- iOS stores both sides; Android needs the "other party"
CASE WHEN ZISFROMME=1 THEN ZTOJID ELSE ZFROMJID END → key_remote_jid
```

**Media paths:**
- iOS: `Message/Media/` relative to app sandbox
- Android: `Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/` (etc.)
- Naming: Android uses `IMG-YYYYMMDD-WA####.jpg` convention

**Sort order:**
- iOS: `ZSORT` field (integer, gaps = deleted messages)
- Android: `sort_id` field + `_id` autoincrement
- The `sort` field is what WhatsApp uses for display order, NOT the timestamp. This is why naive timestamp-based ordering fails.
