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

### What does NOT exist yet

- No Android `msgstore.db` sample — plan is to use open-source DDL
  (whatsapp-viewer project) for schema, then validate when we actually restore.
- No implementation code beyond stubs.
- No tests.
- No babysitter run has been started.

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

### Phase 1: Foundation & Extraction

- Implement iTunes backup locator and file extraction using `iphone_backup_decrypt`.
- Parse `ChatStorage.sqlite` — populate the `Corpus` domain model.
- Handle both encrypted and unencrypted iTunes backups.
- **Test gate:** Parse the real `ChatStorage.sqlite` from `test-data/extracted/`,
  verify all 85 messages, 3 chats, 76 media items are read correctly.
- **Validates SPEC Experiment 1.**

### Phase 2: Schema Conversion (Text Only)

- Obtain Android `msgstore.db` DDL from whatsapp-viewer or similar open-source
  project. Create an empty database with the modern normalized schema.
- Implement JID normalization (inline JIDs to `jid` table).
- Implement message conversion (text messages only):
  - Timestamp: `(ZMESSAGEDATE + 978307200) * 1000`
  - Message types: swap video (2<->3) and audio (3<->2)
  - Direction: derive `key_remote_jid` from `ZISFROMME`/`ZFROMJID`/`ZTOJID`
  - Sort order: map `ZSORT` to `sort_id`
  - Status codes: outgoing->5, incoming->0, system->6
- Populate `chat` table from `ZWACHATSESSION`.
- **Test gate:** Generated `msgstore.db` opens in sqlite3, has correct row
  counts, text messages have correct timestamps and content.

### Phase 3: Media Handling

- Implement media file remapping (iOS `Message/Media/` paths to Android
  `WhatsApp Images/`, `WhatsApp Video/`, etc.).
- Populate `message_media` table with updated paths, MIME types, dimensions.
- Handle media types: images, videos, voice notes, documents.
- **Test gate:** Media entries in `message_media` reference valid remapped paths.

### Phase 4: Advanced Message Types

- Location messages -> `message_location`
- Quoted/reply messages -> `message_quoted`
- Contact cards -> `message_vcard`
- Group metadata -> `group_participants`
- System messages -> `message_system`
- **Test gate:** All 85 messages from test data convert without errors.

### Phase 5: Restore Mechanism

- Root path: ADB push script + ownership fix.
- Encrypted path: wa-crypt-tools integration for `.crypt15` output.
- User-facing instructions for restore process.
- **Validates SPEC Experiments 4, 5.**

### Phase 6: End-to-End Validation & Polish

- Schema version detection (modern vs legacy Android WhatsApp).
- Error handling, progress reporting (Rich console output).
- Selective chat transfer option.
- **Validates SPEC Experiment 6:** Take real iOS messages, convert, restore on
  Android, verify display.

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

### Key decisions still open

- Exact Android DDL source (whatsapp-viewer repo vs reconstructing from SPEC).
- Whether to support legacy Android schema (pre-2022 `messages` table) or
  modern only.
- Merge capability (append to existing Android chats) — ambitious, defer to
  Phase 6+.

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
