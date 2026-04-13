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

## Known Limitations

- **No crypt15 encryption**: The `encrypt` command is a stub. Needs
  `wa-crypt-tools` integration to produce `.crypt15` files.
- **No iTunes backup extraction**: The `extract` command is a stub. Needs
  `iphone-backup-decrypt` to pull `ChatStorage.sqlite` from an iTunes backup.
- **No merge capability**: The tool creates a fresh `msgstore.db`. It cannot
  merge into an existing Android backup that already has messages.
- **No quoted message content**: `message_quoted.text_data` is not populated
  (only `key_id` is set for reply references).
- **No vCard population**: `message_vcard` table is created but never written to.

## Test Results

- **81+ tests across 4 test files**, all passing.
- `test_extract.py`: iOS parser correctness (counts, types, media linkage).
- `test_media.py`: Media path remapping (MIME detection, sequence counters).
- `test_convert.py`: Android schema creation, JID dedup, full conversion,
  timestamp spot-checks, type mapping, status codes, satellite tables.
- `test_e2e.py`: End-to-end pipeline (parse -> convert -> verify DB),
  CLI integration via `CliRunner`.
