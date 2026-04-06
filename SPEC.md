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

---

## 4. Candidate Approaches

### Approach A: Backup Extraction + Database Conversion

```
iTunes backup → decrypt → extract ChatStorage.sqlite → parse
→ convert schema (iOS→Android) → generate msgstore.db
→ copy media files with path remapping
→ encrypt as .crypt15 (or root-place unencrypted)
→ WhatsApp restores on Android
```

**Pros:**
- Complete data — gets everything in the backup, not limited by sync depth
- Works offline — no WhatsApp account interaction needed during conversion
- Proven pattern — every commercial tool uses this approach
- User keeps control — data never leaves their machine

**Cons:**
- Schema-dependent — breaks when WhatsApp updates its database format
- Requires iTunes backup — user must create one (or have one)
- Encryption complexity — producing a valid `.crypt15` requires the encryption key (from root or wa-crypt-tools)
- Media path remapping is tedious (different directory structures, naming conventions)

**Restore options:**
1. **Root path:** Place unencrypted `msgstore.db` directly in `/data/data/com.whatsapp/databases/`, fix ownership with `chown`. Simplest but requires root.
2. **Encrypted backup path:** Re-encrypt `msgstore.db` → `msgstore.db.crypt15` using wa-crypt-tools, place in `Android/media/com.whatsapp/WhatsApp/Databases/`, reinstall WhatsApp, restore from local backup.
3. **ADB sideload:** Push files via ADB without full root (may work on debug builds).

### Approach B: WhatsApp Web Protocol (Baileys / whatsmeow)

```
User scans QR code → connect as WhatsApp Web client
→ receive history sync (proto.IWebMessageInfo protobuf)
→ request on-demand backfill for older messages
→ store in neutral format
→ convert to target platform schema
→ restore to Android
```

**Pros:**
- Platform-agnostic source — protobuf is neither iOS nor Android format
- No backup extraction needed — works even if user no longer has iPhone
- Clean data model — protobuf is the canonical WhatsApp message representation
- Media download supported via protocol

**Cons:**
- **Best-effort history** — WhatsApp controls sync depth; no guarantee of completeness
- Requires phone to be online during sync
- Protocol changes — WhatsApp can break Baileys/whatsmeow at any time
- Account risk — connecting unofficial clients may trigger WhatsApp security checks
- On-demand backfill is per-chat, slow (recommended 50 messages/request)

### Approach C: Hybrid

```
Approach A for bulk history from iTunes backup
+ Approach B to fill gaps, verify, handle edge cases
→ merge into single Android database
→ restore
```

**Pros:**
- Most complete coverage
- Fallback for each approach's weaknesses
- Can cross-validate data between sources

**Cons:**
- Most complex to implement
- Deduplication required (same message from two sources)
- Two dependency surfaces (iTunes backup format + WhatsApp Web protocol)

### Comparison Matrix

| Factor | A: Backup Convert | B: Web Protocol | C: Hybrid |
|--------|-------------------|-----------------|-----------|
| Data completeness | High (full backup) | Variable (best-effort) | Highest |
| Requires iPhone | Yes (for backup) | No (QR scan from any device) | Yes |
| Requires root/key | For restore only | For restore only | For restore only |
| Schema maintenance | High | Low (protobuf stable) | High |
| Implementation complexity | Medium | Medium | High |
| Account risk | None | Low-medium | Low-medium |
| Offline capable | Yes | No | Partial |

### Initial Leaning

**Approach A first.** It's the proven path, gives complete data, and doesn't risk the user's WhatsApp account. The schema maintenance burden is real but manageable with version detection. Approach B is a compelling future addition — especially for users who no longer have their iPhone — but the best-effort nature of history sync makes it unreliable as the sole data source.

**This leaning will be validated or revised by the experiments in Section 5.**

---

## 5. Experiments

> Each experiment must be completed and documented before choosing a final direction.
> Results will be recorded inline below.

### Experiment 1: Parse a Real ChatStorage.sqlite

**Hypothesis:** The iOS schema documented in our research (Section 3.1) accurately describes a current WhatsApp installation's database.

**Setup:**
- Obtain an unencrypted iTunes backup containing WhatsApp data (own device)
- Use `iphone_backup_decrypt` library or manual extraction to get `ChatStorage.sqlite`
- Alternatively: use the built-in manifest to locate the file by domain `AppDomainGroup-group.net.whatsapp.WhatsApp.shared`

**Procedure:**
1. Extract `ChatStorage.sqlite` from backup
2. Run `.schema` in sqlite3 to dump full schema
3. Compare table names, column names, and types against our documentation
4. Query `SELECT DISTINCT ZMESSAGETYPE FROM ZWAMESSAGE` to verify message type codes
5. Verify timestamp format: pick a known message, compute `ZMESSAGEDATE + 978307200`, confirm it matches the actual send time
6. Check `ZSORT` ordering vs `ZMESSAGEDATE` ordering — are they always consistent?
7. Inspect a `ZMEDIAKEY` blob — confirm protobuf structure with first 32 bytes as AES key

**Success criteria:**
- [ ] All documented tables exist
- [ ] Column names and types match
- [ ] Message type codes match documented values
- [ ] Timestamp conversion formula produces correct dates
- [ ] At least one media key blob parses as expected

**Results:** _TBD_

---

### Experiment 2: Parse a Real msgstore.db

**Hypothesis:** A current WhatsApp Android installation uses the modern normalized schema (singular `message` table + satellite tables).

**Setup:**
- Obtain a decrypted `msgstore.db` from an Android device (root extract or decrypt a `.crypt15` backup using wa-crypt-tools)

**Procedure:**
1. Run `.tables` and `.schema` in sqlite3
2. Confirm `message` (not `messages`) table exists
3. Confirm satellite tables: `message_media`, `message_location`, `message_quoted`, `message_add_on`, `jid`, `chat`
4. Count total tables (expecting 100+)
5. Query message types, verify codes against documentation
6. Check for `message_add_on` entries (reactions, edits) if present
7. Inspect `jid` table structure — confirm `user`, `server`, `type` columns
8. Verify `sort_id` behavior vs `_id` vs `timestamp`

**Success criteria:**
- [ ] Modern normalized schema confirmed
- [ ] Table count in expected range
- [ ] Message type codes match documentation (especially audio=2, video=3)
- [ ] `jid` normalization works as documented

**Results:** _TBD_

---

### Experiment 3: Baileys History Sync

**Hypothesis:** Connecting via Baileys and performing history sync + on-demand backfill retrieves a meaningful portion of chat history (at least several months).

**Setup:**
- Install Baileys: `npm install @whiskeysockets/baileys`
- Write a minimal script that connects, listens for `messaging-history.set`, and logs message counts per chat
- Keep phone online throughout

**Procedure:**
1. Connect via QR code scan
2. Wait for initial history sync to complete (monitor `progress` and `isLatest` fields)
3. Log: total chats received, total messages, oldest message timestamp per chat
4. Attempt on-demand backfill for 3 chats (use `fetchMessageHistory` with count=50)
5. Log: how many additional messages arrived, how far back they go
6. Inspect one `proto.IWebMessageInfo` message — document the protobuf fields present
7. Check if media URLs are included and whether they're downloadable

**Success criteria:**
- [ ] Successfully connects and receives history sync
- [ ] Quantify: how many messages from initial sync vs on-demand
- [ ] Oldest message date across all chats
- [ ] At least one media message includes downloadable URL

**Results:** _TBD_

---

### Experiment 4: Android Restore — Hand-Crafted msgstore.db

**Hypothesis:** WhatsApp for Android will accept a hand-crafted `msgstore.db` placed in its data directory via root, and display the messages correctly.

**Setup:**
- Rooted Android device (or emulator with root)
- Create a minimal `msgstore.db` with:
  - 1 entry in `jid` table
  - 1 entry in `chat` table
  - 3 entries in `message` table (one text, one with media reference, one incoming)
  - Correct FKs, timestamps, sort_ids

**Procedure:**
1. Uninstall WhatsApp, reinstall, open once to initialize, then force-stop
2. Replace `/data/data/com.whatsapp/databases/msgstore.db` with hand-crafted version
3. Fix ownership: `chown u0_aXXX:u0_aXXX msgstore.db`
4. Open WhatsApp, verify phone number
5. Check: Do the 3 messages appear? Correct order? Correct timestamps? Correct direction (sent/received)?
6. If WhatsApp crashes or shows "corrupt database", inspect logcat for error details

**Success criteria:**
- [ ] WhatsApp opens without crashing
- [ ] All 3 messages display correctly
- [ ] Timestamps show correct dates
- [ ] Message direction (sent vs received) is correct
- [ ] Chat appears in chat list with correct contact name

**Results:** _TBD_

---

### Experiment 5: wa-crypt-tools Re-Encryption

**Hypothesis:** We can take a modified `msgstore.db`, encrypt it with wa-crypt-tools into a valid `.crypt15` file, and WhatsApp will restore from it on a non-rooted device.

**Setup:**
- `pip install wa-crypt-tools`
- Obtain the encryption key file from a rooted device (`/data/data/com.whatsapp/files/key` or `encrypted_backup.key`)
- Use the hand-crafted `msgstore.db` from Experiment 4

**Procedure:**
1. Encrypt: `wa-crypt-tools encrypt --key key_file msgstore.db msgstore.db.crypt15`
2. Place `msgstore.db.crypt15` in `Android/media/com.whatsapp/WhatsApp/Databases/`
3. Uninstall WhatsApp, reinstall
4. On first launch, WhatsApp should detect local backup and offer restore
5. Tap restore, verify messages appear

**Success criteria:**
- [ ] wa-crypt-tools produces a `.crypt15` file without errors
- [ ] WhatsApp detects and offers to restore the backup
- [ ] Messages appear correctly after restore
- [ ] This works on a non-rooted device

**Results:** _TBD_

---

### Experiment 6: End-to-End Smoke Test

**Hypothesis:** A message extracted from a real iOS `ChatStorage.sqlite` can be converted to Android format and displayed correctly in WhatsApp on Android.

**Setup:**
- Real `ChatStorage.sqlite` from Experiment 1
- Target Android device (rooted or with key for Experiment 5 path)
- Conversion script implementing the paracycle gist mappings, updated for modern schema

**Procedure:**
1. Extract one chat (5-10 messages, mix of text and media) from iOS database
2. Convert using updated schema mapping:
   - Timestamp: `(ZMESSAGEDATE + 978307200) * 1000`
   - Message types: swap video (2→3) and audio (3→2)
   - Direction: `CASE WHEN ZISFROMME=1 THEN ZTOJID ELSE ZFROMJID END`
   - Create `jid` entries for all JIDs
   - Create `chat` entry
   - Create `message_media` entries for media messages
3. Insert into a fresh `msgstore.db` (cloned from a real one with messages cleared)
4. Restore to Android (via root or re-encryption)
5. Open WhatsApp, navigate to the chat
6. Verify: message text, order, timestamps, direction, media thumbnails

**Success criteria:**
- [ ] All text messages display with correct content
- [ ] Messages are in correct chronological order
- [ ] Timestamps display correct dates
- [ ] Sent vs received messages appear on correct side
- [ ] Media messages show thumbnails (even if media files aren't transferred yet)
- [ ] Chat appears with correct contact name in chat list

**Results:** _TBD_
