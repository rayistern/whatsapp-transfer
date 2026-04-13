# Next Steps — WhatsApp iPhone-to-Android Transfer Tool

> Written 2026-04-12. Summarizes current state and outlines the plan for a
> babysitter-orchestrated build on a different machine.

---

## Current State

### What exists

- **Full SPEC** (`SPEC.md`) — 9 sections covering problem statement, prior art,
  data formats, candidate approaches, experiments, technical design,
  implementation plan, risks, and references.
- **6 research documents** (`research/01`–`06`) backing the spec.
- **Python scaffold** (`src/wat/`) with:
  - CLI entrypoint (`cli.py`) — Typer app with `extract`, `convert`, `encrypt`,
    `run` subcommands (stubs).
  - Domain model (`model.py`) — `Jid`, `Chat`, `Media`, `Message`,
    `GroupMember`, `Corpus` dataclasses.
  - Conversion mappings (`mappings.py`) — timestamp conversion, iOS-to-Android
    message type map, status codes.
  - Package structure: `convert/`, `extract/`, `encrypt/` modules (empty).
- **Real test data** (`test-data/extracted/`, 30MB, gitignored) containing:
  - `ChatStorage.sqlite` — real iOS WhatsApp DB: **85 messages, 3 chats**
    (1 private, 1 group with 80 msgs, 1 test), 76 media items, 460 group
    members, 50 push names.
  - `ContactsV2.sqlite`, `CallHistory.sqlite`, and 6 other WhatsApp SQLite DBs.
  - 22 media files under `Message/Media/` preserving original iOS path structure
    (jpg, mp4, pdf, png, webp, thumb files).
  - Additional WhatsApp internal files (preferences, stickers, emoji DB, etc.).
- **Raw iTunes backups** (31GB total, gitignored) in `test-data/` — three
  backup directories, only one has usable WhatsApp data.
- **Docs** — `docs/ACQUIRING_SAMPLE_DATA.md`, `docs/RESTORE.md`.

### What has been built

- Full working pipeline: extract, parse, convert, media copy, encrypt.
- 150 tests across 7 test files, all passing.
- CLI with `extract`, `convert`, `encrypt`, and `run` subcommands.
- Android schema DDL (modern 2022+ normalized) in `convert/android_schema.py`.

### What remains

- **Device testing**: Output has not yet been validated on a real Android device.
- **Merge capability**: Cannot merge into an existing Android backup with
  messages. Creates a fresh `msgstore.db` only.
- **vCard population**: `message_vcard` table is created but not written to.
- **Reactions/edits/polls**: Newer Android schema features not yet mapped.

### Test data portability

The `test-data/extracted/` directory (30MB) is self-contained and portable.
Copy it to the new machine at the same relative path. It is gitignored since
it contains real personal WhatsApp messages and media.

The raw iTunes backups (31GB) under `test-data/` are NOT needed — everything
useful has been extracted.

---

## Implementation Plan

### Overview

Build the complete iOS-to-Android WhatsApp transfer tool using **Approach A**
(Backup Extraction + DB Conversion) as defined in SPEC.md Section 4.

The tool takes an iTunes backup (or already-extracted `ChatStorage.sqlite`) and
produces a `msgstore.db` (and optionally `msgstore.db.crypt15`) that WhatsApp
for Android will accept.

### Phase 1: Foundation & Extraction -- COMPLETE

- [x] Implemented iOS `ChatStorage.sqlite` parser (`wat.extract`).
- [x] Populated the `Corpus` domain model from `ZWAMESSAGE`, `ZWAMEDIAITEM`,
  `ZWACHATSESSION`, `ZWAGROUPMEMBER`, `ZWAPROFILEPUSHNAME`.
- [x] 25 tests validating 85 messages, 3 chats, 76 media items, 460 group members.

### Phase 2: Schema Conversion (Text Only) -- COMPLETE

- [x] Created Android `msgstore.db` DDL (modern 2022+ normalized schema).
- [x] Implemented JID normalization and deduplication via `_JidCache`.
- [x] Implemented timestamp, type, status, and sort_id mapping.
- [x] 38 tests covering schema, JID dedup, full conversion, timestamps, types.

### Phase 3: Media Handling -- COMPLETE

- [x] Implemented `MediaRemapper` with per-date sequence counters.
- [x] Populated `message_media` table with remapped paths and MIME types.
- [x] Handled images, videos, audio, voice notes, and documents.
- [x] 22 tests covering all media types and edge cases.

### Phase 4: Advanced Message Types -- COMPLETE

- [x] Location messages -> `message_location` satellite table.
- [x] Quoted/reply messages -> `message_quoted` with text resolution.
- [x] Group metadata -> `group_participants` with JID references.
- [x] System messages -> `message_system` satellite table.
- [x] All 85 test messages convert without errors.

### Phase 5: Restore Mechanism -- COMPLETE

- [x] Documented rooted ADB push procedure in `docs/RESTORE.md`.
- [x] Documented encrypted backup restore procedure.
- [x] Added troubleshooting guide.

### Phase 6: Selective Chat Transfer -- COMPLETE

- [x] `--chats` flag on `convert` and `run` commands.
- [x] Supports filtering by PK (integer) or name (case-insensitive substring).
- [x] 10 tests covering PK, name, multi-select, error cases.

### Phase 7: Encryption -- COMPLETE

- [x] Integrated `wa-crypt-tools` (`Key15` + `Database15`) for crypt15 output.
- [x] `encrypt` CLI command and `encrypt_db` function.
- [x] 5 tests including round-trip encrypt/decrypt verification.

### Phase 8: iTunes Backup Extraction -- COMPLETE

- [x] Unencrypted extraction via `Manifest.db` parsing and SHA-1 file ID resolution.
- [x] Encrypted extraction via `iphone_backup_decrypt`.
- [x] Unified `extract_backup` entry point with auto-detection.
- [x] 14 tests with synthetic iTunes backup fixtures.

### Phase 9: Media Copy -- COMPLETE

- [x] `copy_media_files` copies iOS media to Android directory structure.
- [x] Uses same `MediaRemapper` as DB conversion for path consistency.
- [x] Tracks copied/skipped/missing counts.
- [x] 5 tests validating file copy behavior.

### Phase 10: Full Pipeline -- COMPLETE

- [x] `run` command chains extract, parse, convert, media copy, and encrypt.
- [x] Supports `--ios` (pre-extracted) and `--backup` (raw iTunes backup).
- [x] Rich summary table with message type breakdown and media stats.
- [x] Error handling and progress reporting throughout.
- [x] 18 tests covering the full pipeline.

---

## Babysitter Orchestration Notes

### Recommended specializations (from plugin library)

The babysitter plugin has several relevant specialization process files:

| Specialization | Path (relative to plugin `skills/babysit/process/specializations/`) | Use for |
|---|---|---|
| **ETL/ELT Pipeline** | `data-engineering-analytics/etl-elt-pipeline.js` | Core extraction + transformation pipeline design |
| **Data Quality Framework** | `data-engineering-analytics/data-quality-framework.js` | Validation gates for converted data |
| **CLI Application Bootstrap** | `cli-mcp-development/cli-application-bootstrap.js` | CLI project structure (already scaffolded, but patterns useful) |
| **CLI Testing** | `cli-mcp-development/cli-unit-integration-testing.js` | Test strategy for the CLI tool |
| **Database Schema Migration** | `code-migration-modernization/database-schema-migration.js` | Schema conversion patterns |
| **Data Format Migration** | `code-migration-modernization/data-format-migration.js` | Format conversion with validation |
| **Test Data Management** | `qa-testing-automation/test-data-management.js` | Managing real vs synthetic test fixtures |
| **TDD Quality Convergence** | `tdd-quality-convergence.js` (process root) | Iterative quality gates reference |

### Recommended approach for the babysitter run

- **Compose** a custom process from the specializations above — the pipeline is
  essentially an ETL job (extract from iOS, transform schema, load into Android
  DB) with a CLI wrapper.
- Use **quality-gated iterative development** — each phase has a test gate that
  validates against the real `ChatStorage.sqlite`.
- Use **agent tasks** for implementation, **shell tasks** for running pytest,
  **breakpoints** at phase boundaries for review.
- The real `test-data/extracted/ChatStorage.sqlite` is the primary validation
  fixture throughout.

### Key decisions already made

- **Language:** Python 3.10+ (scaffold exists).
- **Approach:** A (Backup Extraction + DB Conversion) — per SPEC Section 4.
- **Android schema source:** Open-source DDL (no real `msgstore.db` available
  yet). Will validate against real device during restore phase.
- **Test data:** Real iOS ChatStorage.sqlite with 85 messages across 3 chats.

### Key decisions resolved

- **Android DDL source**: Reconstructed from SPEC and open-source references,
  stored in `src/wat/convert/android_schema.py`.
- **Schema target**: Modern only (2022+ normalized). Legacy schema not supported.
- **Merge capability**: Deferred. Not implemented; tool creates a fresh DB.

---

## Quick Start on New Machine

```bash
# Clone and checkout
git clone <repo-url> && cd whatsapp-transfer

# Copy test data (from USB/network — not in git)
# Place test-data/extracted/ at the same relative path

# Verify test data
python -c "
import sqlite3
conn = sqlite3.connect('test-data/extracted/ChatStorage.sqlite')
msgs = conn.execute('SELECT COUNT(*) FROM ZWAMESSAGE').fetchone()[0]
chats = conn.execute('SELECT COUNT(*) FROM ZWACHATSESSION').fetchone()[0]
print(f'{msgs} messages, {chats} chats')
conn.close()
"
# Expected: 85 messages, 3 chats

# Install the project
pip install -e ".[dev]"

# Start babysitter run
# /babysitter:call
```
