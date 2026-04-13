# wat -- WhatsApp iPhone to Android Transfer Tool

A command-line tool that converts an iOS WhatsApp database (`ChatStorage.sqlite`) into an Android-compatible `msgstore.db`, with optional `.crypt15` encryption for non-rooted restore. Supports extracting data directly from iTunes backups (encrypted or unencrypted).

## Features

- Parse iOS `ChatStorage.sqlite` into a platform-neutral domain model
- Convert to modern Android `msgstore.db` (2022+ normalized schema)
- Remap iOS media paths to Android conventions (`WhatsApp Images/`, `WhatsApp Video/`, etc.)
- Copy media files into the Android directory structure
- Extract WhatsApp data from encrypted and unencrypted iTunes backups
- Encrypt output as `.crypt15` using `wa-crypt-tools` for non-rooted restore
- Selective chat transfer (filter by chat name or ID)
- Full pipeline (`run`) that chains extract, convert, media copy, and encrypt

## Installation

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Quick Start

### Convert a database directly

If you already have `ChatStorage.sqlite` extracted:

```bash
wat convert --ios ChatStorage.sqlite --out msgstore.db
```

### Extract from an iTunes backup

Pull WhatsApp data from a raw iTunes backup directory:

```bash
wat extract --backup /path/to/backup --out extracted/ --password "mypassword"
```

The `--password` flag is only needed for encrypted backups. Omit it for unencrypted backups.

### Encrypt for non-rooted restore

Wrap an unencrypted `msgstore.db` as a `.crypt15` file:

```bash
wat encrypt --db msgstore.db --key key.bin --out msgstore.db.crypt15
```

The key file must be exactly 32 bytes of raw WhatsApp root key material.

### Full pipeline (extracted data)

Run the complete pipeline from already-extracted iOS data:

```bash
wat run --ios extracted/ --out output/ --key key.bin
```

### Full pipeline (from iTunes backup)

Extract, convert, copy media, and encrypt in one step:

```bash
wat run --backup /path/to/backup --out output/ --password "pw" --key key.bin
```

### Selective chat transfer

Convert only specific chats by name (substring match, case-insensitive) or by iOS primary key:

```bash
wat convert --ios db.sqlite --out out.db --chats "GroupName"
wat convert --ios db.sqlite --out out.db --chats "1,3"
wat run --ios extracted/ --out output/ --chats "Family"
```

## Supported Message Types

| iOS Type | Android Type | Description |
|----------|--------------|-------------|
| 0        | 0            | Text |
| 1        | 1            | Image |
| 2        | 3            | Video (swapped) |
| 3        | 2            | Audio / Voice note (swapped) |
| 4        | 4            | Contact card |
| 5        | 5            | Location |
| 6        | 7            | System message (group events) |
| 7        | 0            | URL (rendered as text) |
| 8        | 9            | Document |
| 10       | 0            | Missed call / group event (text fallback) |
| 14       | 15           | Deleted / revoked message |

## Restoring to Android

The `run` command produces a `WhatsApp/` directory tree ready for restore:

```
output/
  WhatsApp/
    Databases/
      msgstore.db
      msgstore.db.crypt15   # if --key was provided
    Media/
      WhatsApp Images/
      WhatsApp Video/
      WhatsApp Voice Notes/
      WhatsApp Audio/
      WhatsApp Documents/
```

For detailed restore instructions (rooted and non-rooted paths), see [docs/RESTORE.md](docs/RESTORE.md).

## Known Limitations

- **No merge capability**: Creates a fresh `msgstore.db`. Cannot merge into an existing Android backup that already has messages.
- **No quoted message content**: `message_quoted.text_data` is populated when the quoted message is in the same conversion batch, but cross-batch references are not resolved.
- **No vCard population**: The `message_vcard` table is created but not written to (contact card content is not extracted).
- **No reactions, edits, polls, or disappearing messages**: These use newer schema features not yet mapped.
- **Modern schema only**: Targets the 2022+ normalized Android schema. Does not support the legacy flat-table `messages` format.
- **Device testing pending**: The output has not yet been validated on a real Android device.

## Development

Install in editable mode with dev dependencies:

```bash
pip install -e ".[dev]"
```

Run the test suite (150 tests across 7 test files):

```bash
pytest tests/
```

All tests run against a real 85-message, 3-chat `ChatStorage.sqlite` extracted from an iTunes backup. The test data is gitignored and must be placed at `test-data/extracted/` manually.

## Architecture

Three-layer pipeline: **Extract, Transform, Load**.

1. **Extract** (`wat.extract`): Parses iOS `ChatStorage.sqlite` into a neutral domain model (`Corpus`). Also supports extracting from raw iTunes backups via `wat.extract.backup`.
2. **Transform** (`wat.model`): The `Corpus` dataclass holds `Chat`, `Message`, `Media`, `GroupMember`, and push-name data in a platform-neutral form.
3. **Load** (`wat.convert`): Writes into a modern Android `msgstore.db`. Handles JID deduplication, type/timestamp mapping, media path remapping, and satellite table population.

CLI entry point: `wat.cli` (Typer). Each pipeline stage is a subcommand (`extract`, `convert`, `encrypt`, `run`).
