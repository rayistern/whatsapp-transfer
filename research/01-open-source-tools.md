# WhatsApp Backup Parsing & Cross-Platform Transfer: Open-Source Tools and Technical Resources

## 1. iOS Backup Parsing (ChatStorage.sqlite)

**[KnugiHK/WhatsApp-Chat-Exporter](https://github.com/KnugiHK/WhatsApp-Chat-Exporter)** -- 996 stars, Python
- The most full-featured cross-platform parser. Parses both iOS (`ChatStorage.sqlite`) and Android (`msgstore.db`) databases. Outputs to HTML, JSON, or text. Handles iOS encrypted iTunes backups, and on Android supports crypt12, crypt14, and crypt15 decryption. Supports WhatsApp Business, media extraction, contact enrichment from vCards, incremental merging, and per-chat filtering.

**[jammastergirish/WhatsAppSQL](https://github.com/jammastergirish/WhatsAppSQL)** -- 2 stars
- SQL queries for searching through WhatsApp messages in `ChatStorage.sqlite` directly. Useful as a reference for the iOS schema.

**[Forensic-Wace/AI-ForensicWace](https://github.com/Forensic-Wace/AI-ForensicWace)** -- 3 stars
- AI-powered forensic analysis platform for WhatsApp databases from both iOS and Android.

**iOS ChatStorage.sqlite Schema (key tables):**
- `ZWAMESSAGE` -- messages; key columns: `ZCHATSESSION` (FK to chat), `ZISFROMME` (0=incoming, 1=outgoing), `ZMESSAGETYPE` (0=text, 1=image, 2=video, 3=voice, etc.), `ZTEXT`, `ZMESSAGEDATE`
- `ZWAMEDIAITEM` -- media metadata; columns: `ZMEDIALOCALPATH`, `ZTHUMBNAILLOCALPATH`, `ZLATITUDE`, `ZLONGITUDE`, `ZTITLE` (caption), `ZVCARDNAME`
- `ZWACHATSESSION` -- chat sessions; `ZSESSIONTYPE` (0=private, 1=group, 2=broadcast, 3=status)
- `ZWAPROFILEPUSHNAME` -- display names
- Timestamps use Apple Core Foundation Absolute Time (seconds since 2001-01-01 00:00:00 UTC)
- File path: `/private/var/mobile/Applications/group.net.whatsapp.WhatsApp.shared/`

---

## 2. Android Backup Parsing (msgstore.db, crypt12/14/15)

**[ElDavoo/wa-crypt-tools](https://github.com/ElDavoo/wa-crypt-tools)** -- 1,012 stars, Python
- The definitive tool for decrypting WhatsApp `.crypt12`, `.crypt14`, and `.crypt15` files. Takes a key file (`key` for crypt14, `encrypted_backup.key` for crypt15) or a 64-character hex key. Outputs decrypted SQLite database or ZIP (for wallpapers/stickers). Includes protobuf handling for modern formats. Installable via pip.

**[andreas-mausch/whatsapp-viewer](https://github.com/andreas-mausch/whatsapp-viewer)** -- 1,400 stars, C
- Windows desktop application for viewing decrypted Android `msgstore.db`. The original "WhatsApp Viewer" tool. Built with Visual Studio. Does not support the latest WhatsApp database schema but is still periodically updated.

**[absadiki/whatsapp-msgstore-viewer](https://github.com/absadiki/whatsapp-msgstore-viewer)**
- Cross-platform (Linux/Windows/Mac) GUI for decrypting and viewing `msgstore.db`. Supports crypt12/14/15 decryption with key file. Includes call log viewing and media browsing.

**[Dexter2389/whatsapp-backup-chat-viewer](https://github.com/Dexter2389/whatsapp-backup-chat-viewer)** -- 85 stars, Python
- Extracts WhatsApp conversations from SQLite databases, exports to JSON or TXT.

**Android msgstore.db Schema (key tables):**
- `message` -- core messages table; key columns: `chat_row_id` (FK to `chat`), `sender_jid_row_id` (FK to `jid`), `from_me`, `message_type` (0=text, 1=picture, 2=audio, 3=video, 4=contact, 5=location, 7=system, 9=document, 15=deleted, 16=live location), `text_data`, `timestamp` (Unix epoch ms)
- `message_media` -- media file paths and metadata
- `message_location` -- geolocation data
- `message_thumbnail` -- graphic previews
- `message_vcard` -- contact cards
- `message_quoted` -- quoted/replied messages (preserves content of deleted messages that were quoted)
- `message_add_on` -- reactions, edits, kept messages in disappearing chats
- `call_logs` -- voice/video call records
- `chat` -- conversation list
- `jid` -- WhatsApp JID (phone@s.whatsapp.net) mapping
- Older schema used `key_from_me` instead of `from_me`; newer versions split data across more tables

**Encryption details:**
- All crypt formats use AES-GCM-256
- Key file is 158 bytes: validation token at offset 30 (32 bytes), AES key at offset 126 (32 bytes)
- Crypt12: IV (16 bytes) at offset 51, encrypted data from offset 67, zlib-compressed after decryption
- Crypt15: same encryption as crypt14, different key source (HSM-backed Backup Key Vault for E2E backups)
- Key file location: `/data/data/com.whatsapp/files/key` (crypt14) or `encrypted_backup.key` (crypt15)
- Backup location: `/data/media/0/WhatsApp/Databases/`

---

## 3. Cross-Platform Conversion Tools (iOS <-> Android)

**[residentsummer/watoi](https://github.com/residentsummer/watoi)** -- 449 stars, Objective-C
- WhatsApp Android To iOS Importer. Converts Android `msgstore.db` to iOS CoreData `ChatStorage.sqlite` format. Requires a Mac with Xcode and iTunes. Works by extracting the iOS backup, replacing the chat database with converted data, and restoring the modified backup. Limitations: media files are not imported (placeholders inserted), contacts that changed phone numbers are not linked.

**[mukulkadel/mwatoi](https://github.com/mukulkadel/mwatoi)** -- 39 stars, Python
- Python reimplementation inspired by watoi. Automatically extracts WhatsApp chats from Android devices and copies them into an iPhone backup. Uses Android emulator workaround to bypass rooting. Windows-only tested. Cannot copy media files.

**[MobitrixTechnology/Mobitrix-WhatsAppTrans](https://github.com/MobitrixTechnology/Mobitrix-WhatsAppTrans)** -- 15 stars, C++ (archived)
- Bidirectional iOS-to-Android and Android-to-iOS WhatsApp message transfer. Now archived.

**Commercial tools** (non-open-source): WazzapMigrator (iPhone to Android, paid), Wondershare MobileTrans/Mutsapper, FonePaw WhatsApp Transfer.

---

## 4. Extracting WhatsApp from iTunes Backups

**[jsharkey13/iphone_backup_decrypt](https://github.com/jsharkey13/iphone_backup_decrypt)** -- 365 stars, Python
- Decrypts encrypted local iOS backups (iOS 13+). Uses PBKDF2 with SHA256 (10 million rounds) then SHA-1 (10,000 rounds) for key derivation. Provides built-in constants `RelativePath.WHATSAPP_MESSAGES` for the chat database and `MatchFiles.WHATSAPP_ATTACHMENTS` for media extraction. Requires the iTunes backup passphrase.

**WhatsApp-Chat-Exporter** (listed above) also handles iOS iTunes backup extraction natively.

---

## 5. WhatsApp Protobuf Format Documentation

**[tulir/whatsmeow](https://github.com/tulir/whatsmeow)** -- 5,666 stars, Go
- The most actively maintained WhatsApp Web multi-device API library. Contains the most up-to-date compiled protobuf definitions under the `proto/` directory, organized into sub-packages: `waE2E`, `waHistorySync`, `waWeb`, `waCompanionReg`, `waMmsRetry`, `waVnameCert`, `waWa6`. The best reference for current WhatsApp message structures.

**[nlitsme/whatsapp-apk-proto](https://github.com/nlitsme/whatsapp-apk-proto)**
- Raw `.proto` files extracted from WhatsApp Android APK files (versions 2.22.6.7 through 2.22.13.5). WhatsApp accidentally included `.proto` source files with comments in these APK versions. The git history shows protocol evolution over time. Includes `wa5.proto` with the complete message definition.

**[wppconnect-team/wa-proto](https://github.com/wppconnect-team/wa-proto)**
- Up-to-date Protocol Buffer definitions extracted from WhatsApp Web (2.3000.x series) with auto-checking for updates. Node.js/TypeScript focused, uses protobufjs.

**[sigalor/whatsapp-web-reveng](https://github.com/sigalor/whatsapp-web-reveng)** -- 6,357 stars, JavaScript
- The foundational WhatsApp Web reverse engineering project. Contains compiled Python protobuf bindings at `backend/whatsapp_protobuf_pb2.py`. Documents the `WebMessageInfo` wrapper message type. Older but historically significant.

**[revwa/protobuf](https://github.com/revwa/protobuf)**
- Automatically generated protobuf definitions parsed from WhatsApp Web's obfuscated JavaScript. WhatsApp uses Protocol Buffers v2.

**[mildsunrise/protobuf-inspector](https://github.com/mildsunrise/protobuf-inspector)** -- 1,117 stars, Python
- General-purpose tool for reverse-engineering Protocol Buffers with unknown definitions. Useful for analyzing unknown WhatsApp binary blobs.

---

## 6. Specific Named Tools

**[B16f00t/whapa](https://github.com/B16f00t/whapa)** -- 1,438 stars, Python
- WhatsApp Parser Toolset for forensic analysis. Modules include:
  - **Whapa** -- database parser (legacy format)
  - **Whacipher** -- encryption/decryption (crypt12/14, no crypt15)
  - **Whagodri** -- Google Drive backup extractor
  - **Whamerge** -- database merger for multiple backups
  - **Whachat** -- chat export converter
  - **Whacloud** -- iCloud backup extractor (beta, non-functional)
  - Tested on Linux, Windows, macOS. Reports in English or Spanish.

**[bitonic/wadump](https://github.com/bitonic/wadump)** -- 59 stars, JavaScript
- Dumps data from the multi-device WhatsApp Web client.

**[shekohex/wadump](https://github.com/shekohex/wadump)** -- 21 stars, Rust
- CLI tool to dump and analyze WhatsApp Web packets. Focused on reverse engineering.

**[wwebjs/whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js)** -- 21,438 stars, JavaScript
- The largest WhatsApp Web client library for Node.js. Not a backup parser per se, but useful for understanding the WhatsApp protocol and extracting live data.

---

## 7. Research Papers and Blog Posts

**Research papers:**
- **Anglano (2014)** -- "Forensic Analysis of WhatsApp Messenger on Android Smartphones" ([arXiv:1507.07739](https://arxiv.org/abs/1507.07739)). The foundational paper. Describes the complete `msgstore.db` schema, `wa.db` contacts database, artifact correlation, and deleted message recovery.
- **Fayyad-Kazan et al. (2022)** -- "Forensic Analysis of WhatsApp SQLite Databases on the Unrooted Android Phones" ([HighTech and Innovation Journal](https://hightechjournal.org/index.php/HIJ/article/view/199)). Updated schema analysis for modern WhatsApp versions with crypt14/15 decryption.
- **Thakur (2013)** -- "Forensic Analysis of WhatsApp on Android Smartphones" ([ScholarWorks@UNO](https://scholarworks.uno.edu/cgi/viewcontent.cgi?article=2736&context=td)). Thesis covering file system extraction and RAM analysis.
- **IJCSE paper** -- "Forensic Analysis of WhatsApp Messenger on iOS" ([PDF](https://www.ijcseonline.org/pub_paper/1-IJCSE-08330.pdf)). iOS-specific schema analysis.

**Blog posts and technical articles:**
- [Belkasoft -- iOS WhatsApp Forensics](https://belkasoft.com/ios-whatsapp-forensics-with-belkasoft-x) -- Detailed walkthrough of `ChatStorage.sqlite` tables
- [Belkasoft -- Android WhatsApp Forensics: Analysis](https://belkasoft.com/android-whatsapp-forensics-analysis) -- Android `msgstore.db` schema deep dive
- [Group-IB -- WhatsApp Forensic Artifacts](https://www.group-ib.com/blog/whatsapp-forensic-artifacts/) -- Both platforms, comprehensive artifact catalog
- [Magnet Forensics -- WhatsApp Artifact Profile](https://www.magnetforensics.com/blog/artifact-profile-whatsapp-messenger/) -- Cross-platform artifact reference
- [The Binary Hick -- "New msgstore, Who 'Dis?"](https://thebinaryhick.blog/2022/06/09/new-msgstore-who-dis-a-look-at-an-updated-whatsapp-on-android/) -- Analysis of the updated Android schema where data was split across multiple tables
- [Towards Data Science -- Analyzing WhatsApp Database using SQL](https://towardsdatascience.com/analyzing-my-whatsapp-database-using-sql-and-redash-5ef9bd6a0b0/) -- iOS `ZMESSAGETYPE` field mappings and practical SQL queries
- [Medium -- "Adventures in WhatsApp DB"](https://medium.com/@Med1um1/extracting-whatsapp-messages-from-backups-with-code-examples-49186de94ab4) -- Code examples for backup extraction
- [snee.la -- "The Workings of WhatsApp's Backups"](https://snee.la/posts/the-workings-of-whatsapps-end-to-end-encrypted-backups/) -- Technical deep dive into E2E encrypted backup format
- [WhatsApp E2E Backup Whitepaper (2021)](https://www.whatsapp.com/security/WhatsApp_Security_Encrypted_Backups_Whitepaper.pdf) -- Official technical whitepaper on the HSM-backed Backup Key Vault
