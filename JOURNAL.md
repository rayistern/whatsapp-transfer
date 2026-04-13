# JOURNAL.md -- WhatsApp Transfer Tool

## Architecture

Three-layer pipeline: **Extract -> Transform -> Load**

1. **Extract** (`wat.extract`): Parses iOS `ChatStorage.sqlite` into a neutral
   domain model (`Corpus`). Reads `ZWACHATSESSION`, `ZWAMESSAGE`,
   `ZWAMEDIAITEM`, `ZWAGROUPMEMBER`, and `ZWAPROFILEPUSHNAME` tables.

2. **Transform** (`wat.model`): The `Corpus` dataclass holds `Chat`, `Message`,
   `Media`, `GroupMember`, and push-name data in a platform-neutral form. No iOS
   or Android specifics leak into this layer.

3. **Load** (`wat.convert`): Writes into a modern Android `msgstore.db`
   (2022+ normalized schema). Handles JID deduplication, type/timestamp mapping,
   media path remapping, and satellite table population (`message_media`,
   `message_location`, `message_system`, `group_participants`).

CLI entry point: `wat.cli` (Typer). Each pipeline stage is a subcommand
(`extract`, `convert`, `encrypt`, `run`).

## Key Decisions

- **Python + Typer**: Fast iteration, strong SQLite stdlib, Rich for output.
- **Modern Android schema only**: Targets the 2022+ normalized schema (separate
  `jid`, `chat`, `message` tables). Does not support legacy flat-table format.
- **Real test data validation**: All tests run against a real 85-message,
  3-chat `ChatStorage.sqlite` extracted from an iTunes backup. No synthetic
  fixtures.

## Type Mapping

iOS `ZMESSAGETYPE` -> Android `message.message_type`:

| iOS | Android | Notes |
|-----|---------|-------|
| 0   | 0       | Text |
| 1   | 1       | Image |
| 2   | 3       | Video (swapped!) |
| 3   | 2       | Audio (swapped!) |
| 4   | 4       | Contact |
| 5   | 5       | Location |
| 6   | 7       | System -> message_system satellite |
| 7   | 0       | URL rendered as text |
| 8   | 9       | Document |
| 10  | 0       | Missed call / group event -> text (best-effort) |
| 14  | 15      | Deleted/revoked message |

**Type 10** (missed call / group event): Rare in practice. Mapped to text (0)
because Android has no direct equivalent and the text content is still useful.

**Type 14** (deleted/revoked): Maps to Android's type 15, which WhatsApp
renders as "This message was deleted."

## Media Remapping

iOS stores media at paths like `Media/<group-jid>/e/9/<uuid>.jpg`. Android
expects convention-based paths:

- Images: `WhatsApp Images/IMG-YYYYMMDD-WA0001.jpg`
- Video: `WhatsApp Video/VID-YYYYMMDD-WA0001.mp4`
- Audio: `WhatsApp Audio/AUD-YYYYMMDD-WA0001.opus`
- Voice notes: `WhatsApp Voice Notes/PTT-YYYYMMDD-WA0001.opus`
- Documents: `WhatsApp Documents/<original_filename>`

The `MediaRemapper` class maintains a global sequence counter per conversion
run. MIME type is resolved from the iOS `ZVCARDSTRING` field (misleadingly
named) with extension-based fallback.

## Phase 6-10 Decisions

- **Phase 6 (Selective transfer)**: Added `--chats` flag supporting comma-separated
  chat PKs or name substrings (case-insensitive). Filter applied before conversion
  so the output DB contains only selected chats and their messages/members.
- **Phase 7 (Encryption)**: Integrated `wa-crypt-tools` (`Key15` + `Database15`)
  for crypt15 output. Reads a raw 32-byte key file, zlib-compresses the plaintext
  DB, and encrypts with a random IV. Round-trip verified in tests.
- **Phase 8 (iTunes backup extraction)**: Implemented both unencrypted extraction
  (parse `Manifest.db`, resolve SHA-1 file IDs, copy from hashed storage) and
  encrypted extraction (via `iphone_backup_decrypt`). Unified entry point
  auto-detects backup type.
- **Phase 9 (Media copy)**: `copy_media_files` walks messages with media,
  resolves iOS source paths, copies to Android directory structure using the
  same `MediaRemapper` used during DB conversion so paths match.
- **Phase 10 (Full pipeline)**: The `run` command chains extract, parse, convert,
  media copy, and encrypt into a single invocation. Supports `--ios` (pre-extracted)
  and `--backup` (raw iTunes backup) as mutually exclusive input sources. Temporary
  directory cleanup handled via `TemporaryDirectory` context manager.

## Known Limitations

- **No merge capability**: The tool creates a fresh `msgstore.db`. It cannot
  merge into an existing Android backup that already has messages.
- **No quoted message content**: `message_quoted.text_data` is populated when the
  quoted message exists in the same conversion batch, but cross-batch references
  are not resolved.
- **No vCard population**: `message_vcard` table is created but never written to.
- **No reactions/edits/polls/disappearing**: These use newer Android schema
  features (`message_add_on`) not yet mapped.
- **Device testing pending**: Output has not yet been validated on a real Android
  device.

## Test Results

- **150 tests across 7 test files**, all passing.
- `test_extract.py` (25): iOS parser correctness (counts, types, media linkage,
  JID parsing, push names, group members).
- `test_media.py` (22): Media path remapping (MIME detection, sequence counters,
  voice note detection, unknown MIME fallback, integration with full conversion).
- `test_convert.py` (38): Android schema creation, JID dedup, full conversion,
  timestamp spot-checks, type mapping, status codes, satellite tables
  (system messages, locations, group participants), deleted message handling.
- `test_e2e.py` (28): End-to-end pipeline (parse -> convert -> verify DB),
  CLI integration via `CliRunner`, selective chat transfer (`--chats` flag),
  error handling for bad inputs.
- `test_encrypt.py` (5): Crypt15 round-trip (encrypt then decrypt and verify),
  directory creation, error cases (missing DB, missing key, bad key length).
- `test_backup_extract.py` (14): Backup type detection (encrypted/unencrypted/
  invalid), unencrypted extraction from synthetic iTunes backups, edge cases
  (no WhatsApp data, missing files, directories skipped).
- `test_pipeline.py` (18): Full `run` command tests (media copy, crypt15
  output, `--chats` filter, mutually exclusive flags, summary output).
