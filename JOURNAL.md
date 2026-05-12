# JOURNAL.md -- WhatsApp iPhone-to-Android Transfer Tool

> Comprehensive development journal. Every architectural, schema, and implementation
> decision is recorded here so future developers can understand *why*, not just *what*.

---

## Table of Contents

1. [Architecture Decisions](#architecture-decisions)
2. [Schema Decisions](#schema-decisions)
3. [Type Mapping Decisions](#type-mapping-decisions)
4. [Media Decisions](#media-decisions)
5. [Extraction Decisions](#extraction-decisions)
6. [Encryption Decisions](#encryption-decisions)
7. [CLI Decisions](#cli-decisions)
8. [Testing Decisions](#testing-decisions)
9. [Phase-by-Phase Timeline](#phase-by-phase-timeline)
10. [Known Limitations](#known-limitations)

---

## Architecture Decisions

### Why Three-Layer Pipeline (Extract -> Transform -> Load)

The tool follows a classic ETL pattern with three distinct layers:

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

**Why this separation matters:**

- **Testability.** Each layer can be tested independently. The extractor is tested
  against real iOS data. The converter is tested against its own output. The model
  sits in between as a stable contract.
- **Future extensibility.** If a new source format appears (e.g., WhatsApp Web
  protocol via Baileys, or a different iOS schema version), only the Extract layer
  changes. If Android changes its schema, only the Load layer changes. The neutral
  model insulates them from each other.
- **Debuggability.** The `Corpus` object is fully inspectable at the boundary
  between extraction and conversion. You can serialize it, print it, or write
  tests against it without touching either database.

Every commercial WhatsApp transfer tool (Wondershare MobileTrans, Tenorshare
iCareFone, WazzapMigrator) uses this same three-stage architecture. It is the
proven pattern for backup-based cross-platform data migration.

### Why Python + Typer + Rich (not Go, not Rust, not Java)

**Python was chosen for several concrete reasons:**

- **SQLite stdlib support.** Python's `sqlite3` module is battle-tested and
  requires zero additional dependencies. Both the iOS and Android databases are
  SQLite, so the entire read/write pipeline is built on a single library that
  ships with every Python installation.
- **Fast iteration speed.** Schema reverse-engineering requires constant
  experimentation --- query a table, inspect results, adjust mappings, re-run.
  Python's REPL and short feedback loop make this practical.
- **Ecosystem fit.** The two critical dependencies (`iphone_backup_decrypt` for
  iTunes backup extraction and `wa-crypt-tools` for crypt15 encryption) are both
  Python libraries. Using Python avoids FFI overhead and version mismatch issues.
- **Prototyping-to-production path.** The tool is a personal-use CLI, not a
  high-throughput server. Python's performance is more than sufficient for
  processing a few hundred thousand messages and media files.

**Why not Go/Rust/Java:**

- Go and Rust would require CGo or an FFI layer to call `wa-crypt-tools` and
  `iphone_backup_decrypt`, adding complexity without meaningful benefit.
- Java was used by the archived `WhatsAppIphoneToAndroid` project (Kethen), but
  it targets the legacy pre-2022 Android schema and has no community momentum.
- The only open-source iOS-to-Android tool with any traction
  (`WhatsApp-Chat-Exporter`, 996 stars) is also Python.

**Typer** was chosen over Click or argparse because it provides type-checked
command definitions with minimal boilerplate. Each pipeline stage is a subcommand
(`extract`, `convert`, `encrypt`, `run`), which maps naturally to Typer's
decorator model.

**Rich** provides formatted terminal output (tables, progress bars, colored
status messages) with zero configuration. The `_build_summary_table` function
in `cli.py` uses Rich's `Table` class to display conversion statistics.

### Why Dataclasses Instead of SQLAlchemy/Pydantic

The domain model (`wat.model`) uses plain Python `@dataclass` classes:

```python
@dataclass
class Message:
    pk: int
    chat_pk: int
    stanza_id: str | None
    from_me: bool
    ios_type: int
    ios_timestamp: float
    sort: int | None
    text: str | None
    from_jid: str | None
    to_jid: str | None
    starred: bool = False
    media: Media | None = None
    quoted_stanza_id: str | None = None
```

**Why not SQLAlchemy:**

- The tool reads from one SQLite database and writes to a completely different
  one. An ORM would need to model both schemas, and the mapping between them is
  not a simple table-to-table correspondence. The iOS `ZWAMESSAGE` table maps
  to `message` + `message_media` + `message_location` + `message_quoted` +
  `message_system` on Android. An ORM would obscure this fan-out rather than
  simplify it.
- The raw `sqlite3` module gives us full control over INSERT ordering and
  foreign key resolution (e.g., `_JidCache.get_or_insert` which deduplicates
  JIDs on the fly). This would be awkward with an ORM's unit-of-work pattern.

**Why not Pydantic:**

- The domain model has no external input validation requirements. Data comes from
  a SQLite database with known types, not from user input or an API. Pydantic's
  validation machinery would add overhead and dependency weight for no benefit.
- Dataclasses give us `__init__`, `__repr__`, and `__eq__` for free, which is
  all we need.

### Why No ORM for SQLite Access

Direct `sqlite3` is used for both reading the iOS database and writing the
Android database. The key reasons:

- **Schema mismatch.** The iOS schema uses Core Data conventions (`Z_PK`,
  `ZWAMESSAGE`, `ZFROMJID`) while Android uses a modern normalized schema
  (`_id`, `message`, `sender_jid_row_id`). No ORM can bridge this naturally.
- **Insert ordering matters.** Android's `jid` table has a UNIQUE constraint
  on `(user, server)`. The `_JidCache` class uses `INSERT OR IGNORE` followed
  by `SELECT` to get the row ID. This deduplication pattern is trivial with raw
  SQL but awkward with an ORM.
- **Performance.** The converter processes all messages in a single pass with
  a single open connection. No ORM session management needed.
- **Inspectability.** Every SQL statement is visible in `writer.py`. There is
  no query generation layer to debug through.

---

## Schema Decisions

### Why Modern Android Schema Only (Not Legacy Pre-2022)

WhatsApp for Android underwent a major schema normalization around 2022. The
old schema had a monolithic `messages` (plural) table with inline JIDs. The
modern schema has a singular `message` table with foreign keys to a normalized
`jid` table, plus satellite tables for media, locations, quotes, etc.

**We target only the modern schema because:**

- Every actively maintained WhatsApp installation on Android 12+ uses the modern
  schema. The legacy schema exists only on very old devices that haven't updated
  WhatsApp in years.
- The modern schema is what WhatsApp will restore from a `.crypt15` backup.
  Writing the legacy schema would only work with root-based restore on old
  devices.
- Dual-schema support would double the converter code with no practical benefit.

**Detection heuristic:** If table `messages` (plural) exists instead of
`message` (singular), you're on the legacy schema. We don't implement this
detection --- we simply target modern.

### Why 16+ Tables in the DDL

The `android_schema.py` DDL creates 16 tables. Nine are actively populated
during conversion:

| Table | Purpose | Populated? |
|-------|---------|------------|
| `jid` | Normalized JID store | Yes |
| `chat` | Chat sessions | Yes |
| `message` | Core messages | Yes |
| `message_media` | Media metadata | Yes |
| `message_location` | GPS coordinates | Yes |
| `message_quoted` | Reply references | Yes |
| `message_system` | System messages | Yes |
| `message_vcard` | Contact cards | Created empty |
| `group_participants` | Group membership | Yes |

Seven additional tables are created empty because WhatsApp Android may check
for their existence during startup:

| Table | Why Created Empty |
|-------|-------------------|
| `message_add_on` | Reactions (type 56), edits (type 74), keep-flags (type 68) |
| `message_forwarded` | Forward score tracking |
| `receipt_device` | Per-device delivery receipts |
| `receipt_user` | Per-user read receipts |
| `props` | Key-value configuration (populated with `schema_version`) |
| `message_thumbnail` | Inline thumbnail blobs |
| `audio_data` | Voice note waveform data |

These were identified from open-source Android schema dumps (whatsapp-viewer,
The Binary Hick blog) and forensic analysis papers. WhatsApp may crash or refuse
to load a database that is missing expected tables, even if those tables are
empty.

### Why WAL Mode and page_size=4096

```python
conn.execute("PRAGMA page_size = 4096")
conn.execute("PRAGMA journal_mode = WAL")
```

- **WAL mode (Write-Ahead Logging):** This is what WhatsApp Android uses in
  production. WAL allows concurrent reads while writing, which is important
  because WhatsApp's background services may read the database while the UI
  is writing. Using a different journal mode could cause WhatsApp to switch
  modes on first open, potentially corrupting data or triggering a rebuild.
- **page_size=4096:** This matches the default page size used by WhatsApp's
  SQLite databases. Mismatched page sizes between the database file and
  WhatsApp's expectations could cause performance degradation or errors.

Both settings must be applied before any tables are created, which is why they
appear at the top of `create_android_db`.

### Why Additional Empty Tables (message_add_on, props, receipts, etc.)

When WhatsApp Android opens `msgstore.db`, it does not run a full schema
migration from scratch. It expects certain tables to already exist. If they
are missing, WhatsApp may:

1. Crash with a "corrupt database" error
2. Silently rebuild the database from the cloud backup, discarding our data
3. Create the tables itself but with different column definitions

To avoid all three failure modes, we pre-create every table that WhatsApp
might reference. The tables are empty (except `props`), so they add negligible
size to the database.

### The props Table and schema_version Entry

```python
conn.execute("INSERT INTO props (key, value) VALUES ('schema_version', '1')")
```

WhatsApp uses the `props` table as a key-value store for internal configuration.
The `schema_version` key tells WhatsApp which schema migration level the database
is at. Without this entry, WhatsApp may attempt to run migrations on the database,
which could fail because our table definitions don't match WhatsApp's internal
migration expectations exactly.

We set `schema_version` to `'1'` as a baseline. This is intentionally low ---
WhatsApp will upgrade it as needed. Setting it too high could cause WhatsApp to
skip migrations it needs to run.

---

## Type Mapping Decisions

### Complete iOS -> Android Type Mapping Table

```python
IOS_TO_ANDROID_MESSAGE_TYPE: dict[int, int] = {
    0: 0,   # text -> text
    1: 1,   # image -> image
    2: 3,   # iOS video -> Android video (SWAPPED)
    3: 2,   # iOS audio/voice -> Android audio (SWAPPED)
    4: 4,   # contact -> contact
    5: 5,   # location -> location
    6: 7,   # system -> Android system (message_system satellite)
    7: 0,   # url -> text (Android renders URLs inline)
    8: 9,   # document -> document
    10: 0,  # missed call / group event -> text (no Android equivalent)
    14: 15, # deleted/revoked -> Android deleted marker
}
```

### Why Audio/Video Are Swapped (Historical WhatsApp Platform Decision)

This is the single most critical mapping detail. On iOS, video is type 2 and
audio is type 3. On Android, video is type 3 and audio is type 2. They are
swapped.

This is not a bug --- it reflects independent engineering decisions made by the
iOS and Android WhatsApp teams early in WhatsApp's history, before the two
platforms had unified type codes. By the time anyone noticed the inconsistency,
billions of messages were stored with these codes, making it impossible to change
without a massive migration.

Every known WhatsApp transfer tool (commercial and open-source) documents this
swap. The paracycle gist (2013) was the first public documentation. Our test
suite explicitly validates it:

```python
def test_video_swap(self):
    assert IOS_TO_ANDROID_MESSAGE_TYPE[2] == 3

def test_audio_swap(self):
    assert IOS_TO_ANDROID_MESSAGE_TYPE[3] == 2
```

And we verify it end-to-end against real data:

```python
def test_video_messages_in_db(self, android_db: Path):
    """iOS has 2 video messages (type 2). In Android they should be type 3."""
    conn = sqlite3.connect(str(android_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM message WHERE message_type = 3"
    ).fetchone()[0]
    assert count == 2  # the 2 iOS video messages
```

### Why Type 7 (URL) Maps to 0 (Text)

iOS treats URL messages as a distinct type (7) with rich preview metadata
(title, description, thumbnail). Android renders URLs as plain text messages
(type 0) with inline link detection. There is no dedicated URL message type in
the Android schema.

Mapping 7 -> 0 preserves the URL in the `text_data` field. Android's WhatsApp
client will detect the URL and render a clickable link with a preview card
automatically. No information is lost.

### Why Type 10 (Missed Call) Maps to 0 (Text)

iOS type 10 covers both missed voice/video calls and certain group events
(participant joins/leaves that don't use type 6). Android has separate call
log tables and a different mechanism for call notifications.

We map type 10 to text (0) as a best-effort preservation strategy:

- The original text content (e.g., "Missed voice call" or "You were added")
  is preserved in `text_data`.
- This is better than dropping the message entirely.
- It is rare in practice --- only 4 out of 85 messages in our test data have
  type 10.

### Why Type 14 (Deleted) Maps to 15

iOS uses type 14 for deleted/revoked messages ("This message was deleted").
Android uses type 15 for the same purpose. The mapping is straightforward:

```python
14: 15,  # deleted/revoked message -> Android deleted
```

WhatsApp Android renders type 15 as "This message was deleted" with the
characteristic strikethrough bubble. Our test data has exactly 1 deleted
message, and we verify the mapping:

```python
def test_deleted_messages_have_type_15(self, android_db: Path):
    conn = sqlite3.connect(str(android_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM message WHERE message_type = 15"
    ).fetchone()[0]
    assert count == 1
```

### Why Unmapped Types Default to 0 (Text) with Content Preserved

```python
android_type = IOS_TO_ANDROID_MESSAGE_TYPE.get(msg.ios_type, 0)
```

Any iOS message type not in the mapping dictionary defaults to text (0). This
is a deliberate safety net:

- Future iOS WhatsApp versions may introduce new message types. Defaulting to
  text ensures these messages are preserved rather than silently dropped.
- The `text_data` field always contains whatever text content the message had,
  so even if the rendering is imperfect, the content is not lost.
- This matches the behavior of other open-source tools (WhatsApp-Chat-Exporter
  uses a similar fallback).

---

## Media Decisions

### Why MediaRemapper Uses a Sequence Counter

```python
class MediaRemapper:
    def __init__(self, reference_date: date | None = None) -> None:
        self._date = reference_date or date.today()
        self._seq: int = 0  # global counter across all media types

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq
```

The `MediaRemapper` maintains a global sequence counter that increments across
all media types (images, videos, audio, documents). This ensures unique filenames
across the entire conversion run.

**Why global rather than per-type counters:**

- Android WhatsApp uses a single global counter for its `WA####` suffix. An
  image might be `IMG-20260413-WA0001.jpg` and the next video might be
  `VID-20260413-WA0002.mp4`. There is no per-type reset.
- A global counter prevents filename collisions when two different media types
  happen to produce the same base name.
- The counter is stateful and lives on the `MediaRemapper` instance. The same
  instance is used for both DB conversion (where paths are written to
  `message_media.file_path`) and the actual file copy (`copy_media_files`), so
  the paths are guaranteed to match.

### Why Android Naming Convention (IMG-YYYYMMDD-WA####)

Android WhatsApp uses a specific naming convention for media files:

- Images: `IMG-YYYYMMDD-WA####.ext`
- Videos: `VID-YYYYMMDD-WA####.ext`
- Audio: `AUD-YYYYMMDD-WA####.ext`
- Voice notes: `PTT-YYYYMMDD-WA####.opus`
- Documents: original filename preserved

This convention is not just cosmetic. WhatsApp Android's media scanner
recognizes these prefixes to categorize files in its internal media library.
Files that don't follow this convention may not appear in the correct media
tab within a chat.

### Why Voice Notes Detected by "ptt" in Path

```python
if "ptt" in ios_path.lower():
    return f"WhatsApp Voice Notes/PTT-{date_str}-WA{seq:04d}.opus"
```

"PTT" stands for "push-to-talk", WhatsApp's internal name for voice notes.
iOS stores voice notes in paths containing `/ptt/` (e.g.,
`Media/group@g.us/ptt/voice.ogg`). This is the most reliable signal to
distinguish voice notes from regular audio messages.

We check for "ptt" case-insensitively because iOS path casing is inconsistent.
The test suite validates both lowercase and uppercase:

```python
def test_voice_note_ptt(self):
    r = MediaRemapper(reference_date=FIXED_DATE)
    result = r.remap("Media/group@g.us/ptt/voice.ogg", "audio/ogg")
    assert result == "WhatsApp Voice Notes/PTT-20250315-WA0001.opus"

def test_ptt_case_insensitive(self):
    r = MediaRemapper(reference_date=FIXED_DATE)
    result = r.remap("Media/group@g.us/PTT/voice.ogg", "audio/ogg")
    assert result == "WhatsApp Voice Notes/PTT-20250315-WA0001.opus"
```

Voice notes are always output as `.opus` regardless of the input extension,
because Android WhatsApp expects voice notes in Opus format.

### Why MIME Inference from Extension as Fallback

```python
def _resolve_mime(ios_path: str, mime_type: str | None) -> str | None:
    if mime_type and "/" in mime_type:
        return mime_type
    _, ext = os.path.splitext(ios_path)
    return _EXT_TO_MIME.get(ext.lower())
```

The MIME type fallback chain is:

1. Use `ZVCARDSTRING` from the iOS database if it contains a `/` (valid MIME).
2. If `ZVCARDSTRING` is null, empty, or not a valid MIME type, infer from the
   file extension.
3. If neither works, fall back to treating the file as a document.

**Why the `/` check matters:** The `ZVCARDSTRING` column is sometimes populated
with non-MIME data. In our test data, some entries contain JID strings like
`13479949770@s.whatsapp.net` instead of MIME types. The `/` check filters these
out:

```python
def test_invalid_mime_not_slash(self):
    """A MIME-type without '/' (like a JID stored in ZVCARDSTRING) should
    be treated as unknown and fall back to extension inference."""
    r = MediaRemapper(reference_date=FIXED_DATE)
    result = r.remap("Media/group@g.us/a/b/photo.jpg", "13479949770@s.whatsapp.net")
    assert result == "WhatsApp Images/IMG-20250315-WA0001.jpg"
```

### Why ZVCARDSTRING Is Actually MIME Type (Apple Naming Confusion)

The iOS `ZWAMEDIAITEM` table has a column called `ZVCARDSTRING`. Despite the
name suggesting vCard data, this column stores the MIME type of the media
attachment (e.g., `image/jpeg`, `video/mp4`, `application/pdf`).

This naming comes from Apple's Core Data conventions. WhatsApp's iOS codebase
uses Core Data, and the column was likely originally intended for vCard contact
data. When WhatsApp later needed to store MIME types, they reused this column
rather than adding a new one. The `Z` prefix is Core Data's standard entity
prefix.

This confusion is documented in forensic analysis papers (Belkasoft, Group-IB)
and is a well-known gotcha for anyone parsing WhatsApp iOS databases.

---

## Extraction Decisions

### Why We Support Both Encrypted and Unencrypted iTunes Backups

Users may have either type of backup depending on their iTunes/Finder settings:

- **Unencrypted backups** are simpler to extract but don't contain certain
  sensitive data (keychain items, health data). Most WhatsApp data is present
  in unencrypted backups.
- **Encrypted backups** require a passphrase but contain everything. Some users
  have encryption enabled by default (especially on corporate-managed devices).

The tool auto-detects the backup type by checking `Manifest.plist` for the
`IsEncrypted` flag:

```python
def detect_backup_type(backup_dir: Path) -> str | None:
    manifest_db = backup_dir / "Manifest.db"
    manifest_plist = backup_dir / "Manifest.plist"
    if not manifest_db.exists():
        return None
    if manifest_plist.exists():
        plist = plistlib.load(f)
        if plist.get("IsEncrypted", False):
            return "encrypted"
    return "unencrypted"
```

### How Unencrypted Backup Hashed File Storage Works

iTunes stores backup files in a hashed directory structure, not by their
original filename. The mapping is:

1. Each file in the backup has a `fileID` computed as
   `SHA1(domain + "-" + relativePath)`.
2. The file is stored at `<backup_dir>/<fileID[:2]>/<fileID>` (first two
   hex characters as subdirectory).
3. `Manifest.db` contains a `Files` table mapping `fileID` to `domain` and
   `relativePath`.

Our extraction process:

1. Open `Manifest.db`, query for files matching the WhatsApp domain
   (`AppDomainGroup-group.net.whatsapp.WhatsApp.shared`).
2. Filter to `flags = 1` (regular files, not directories).
3. For each file, locate the source at `<backup>/<fileID[:2]>/<fileID>`.
4. Copy to `<output>/<relativePath>`, preserving the original directory structure.

```python
WHATSAPP_DOMAIN = "AppDomainGroup-group.net.whatsapp.WhatsApp.shared"
WHATSAPP_DOMAIN_LIKE = "%net.whatsapp.%"
```

We use `LIKE` matching (`%net.whatsapp.%`) rather than exact domain matching
to catch potential domain variations across iOS versions.

### Why iphone_backup_decrypt for Encrypted, Manual Manifest.db for Unencrypted

- **Encrypted backups** require decryption of each file using per-file keys
  derived from the backup passphrase. The `iphone_backup_decrypt` library
  handles this complex key derivation (PBKDF2 + AES unwrapping). Reimplementing
  this would be error-prone and unnecessary.
- **Unencrypted backups** don't need decryption --- files are stored in plain
  form. We only need to parse `Manifest.db` and copy files from the hashed
  storage. This is simple enough to implement directly without a library
  dependency.

This split keeps the unencrypted path dependency-free (only `sqlite3` and
`hashlib`, both stdlib) while using the specialized library only when actually
needed.

---

## Encryption Decisions

### Why zlib Compression Level 1 (WhatsApp Convention)

```python
compressed = zlib.compress(plaintext, 1)
```

WhatsApp uses zlib compression level 1 (fastest) for its backup encryption
pipeline. This was determined by examining the `wa-crypt-tools` source code
and verified by round-trip testing.

Level 1 was chosen by WhatsApp because:

- Backup encryption happens on the phone, where battery and CPU are constrained.
- The database is already compact (SQLite pages are not highly compressible).
- The marginal size reduction from higher compression levels is not worth the
  CPU cost.

We match this exactly to produce byte-compatible output.

### How Key15 and Database15 Work

The crypt15 encryption process:

1. **Key15:** Takes a raw 32-byte key (the WhatsApp root key material, extracted
   from a rooted device at `/data/data/com.whatsapp/files/key` or
   `encrypted_backup.key`).
2. **zlib compress:** The plaintext `msgstore.db` is compressed with level 1.
3. **Database15:** Generates a random IV, encrypts the compressed data using
   AES-GCM with the key material, and wraps it in WhatsApp's crypt15 container
   format (which includes headers, the IV, and authentication tags).
4. **Output:** A `.crypt15` file that WhatsApp Android recognizes as a valid
   local backup.

```python
key = Key15(key=key_bytes)
plaintext = db_path.read_bytes()
compressed = zlib.compress(plaintext, 1)
db = Database15(key=key)
props = Props()
encrypted = db.encrypt(key, props, compressed)
```

### Round-Trip Verification Approach

The encryption test suite verifies the entire cycle:

1. Create a test SQLite database with known content.
2. Encrypt it using `encrypt_db`.
3. Decrypt using `wa-crypt-tools`' `DatabaseFactory.from_file` and `db.decrypt`.
4. Decompress with `zlib.decompress`.
5. Verify the decrypted bytes match the original exactly.
6. Open the decrypted bytes as a SQLite database and verify row contents.

```python
def test_round_trip(self, tmp_path: Path) -> None:
    # ... encrypt ...
    key = Key15(key=key_bytes)
    with open(out_path, "rb") as f:
        db = DatabaseFactory.from_file(f)
        encrypted_data = f.read()
    decrypted_compressed = db.decrypt(key, encrypted_data)
    decrypted_bytes = zlib.decompress(decrypted_compressed)
    assert decrypted_bytes == original_bytes
```

This round-trip test is the strongest guarantee that our encryption output
will be accepted by WhatsApp.

---

## CLI Decisions

### Why --ios and --backup Are Mutually Exclusive

The `run` command accepts two input sources:

- `--ios <dir>`: Points to an already-extracted directory containing
  `ChatStorage.sqlite` and `Message/Media/`.
- `--backup <dir>`: Points to a raw iTunes backup directory.

These are mutually exclusive because they represent two different starting
points in the pipeline:

```python
if ios and backup:
    console.print("[red]Error:[/red] --ios and --backup are mutually exclusive.")
    raise typer.Exit(code=1)
if not ios and not backup:
    console.print("[red]Error:[/red] provide either --ios or --backup.")
    raise typer.Exit(code=1)
```

**Why not just `--input`?** Making the input source explicit avoids ambiguity.
An already-extracted directory and an iTunes backup directory can look similar
(both contain subdirectories with files). Explicit flags prevent the tool from
guessing wrong and producing confusing errors.

When `--backup` is used, the tool extracts to a temporary directory and cleans
up after the pipeline completes:

```python
tmp_dir_obj = tempfile.TemporaryDirectory(prefix="wat_")
# ... extract and process ...
# finally:
tmp_dir_obj.cleanup()
```

### Why --chats Supports Both PKs and Names

```python
def _filter_corpus(corpus: Corpus, chats_spec: str) -> Corpus:
    tokens = [t.strip() for t in chats_spec.split(",") if t.strip()]
    for tok in tokens:
        try:
            pk_filters.append(int(tok))
        except ValueError:
            name_filters.append(tok.lower())
```

The `--chats` flag accepts a comma-separated list where each token is
automatically interpreted as either an integer PK or a name substring:

- `--chats 1,3` selects chats by their iOS primary key.
- `--chats "Rayi,JLI"` selects by case-insensitive substring match.
- `--chats "1,Rayi"` mixes both.

**Why support PKs at all?** PKs are unambiguous. If two chats have similar
names ("John" and "John Smith"), a name match might select both. PKs let the
user be precise. They can discover PKs by running `convert` without `--chats`
first and examining the output.

**Why case-insensitive substring?** Users don't remember exact chat names.
`--chats rayi` should match "Rayi Rayi" without requiring exact casing or
the full name.

### Why --key Is Optional (Supports Both Rooted and Encrypted Restore)

The `run` command's `--key` flag is optional:

```python
key: Optional[Path] = typer.Option(None, ...)
```

This supports two restore workflows:

1. **Rooted device (no key needed):** The user can push the unencrypted
   `msgstore.db` directly to `/data/data/com.whatsapp/databases/` via ADB.
   No encryption step required.
2. **Non-rooted device (key needed):** The user provides a 32-byte key file
   extracted from a rooted device, and the tool produces `msgstore.db.crypt15`
   for local backup restore.

Making encryption optional keeps the tool useful for the simpler rooted-device
workflow without forcing users through unnecessary key extraction.

---

## Testing Decisions

### Why Real Test Data Only (No Synthetic Fixtures)

All tests run against a real `ChatStorage.sqlite` extracted from an actual
iTunes backup. No synthetic fixtures are used for the core pipeline tests.

**Why real data:**

- **Schema fidelity.** A real database contains all the quirks of WhatsApp's
  iOS schema: NULL values in unexpected places, `ZVCARDSTRING` containing JIDs
  instead of MIME types, type 10 messages for missed calls, etc. Synthetic data
  would miss these edge cases.
- **Confidence.** If the pipeline handles a real database correctly, it will
  handle other real databases. Synthetic data provides weaker guarantees because
  it reflects the developer's assumptions about the data, not reality.
- **Regression detection.** The exact counts (85 messages, 3 chats, 76 media
  items, 460 group members, 50 push names) serve as regression markers. Any
  change that alters these counts indicates a real behavioral change.

**The one exception:** `test_backup_extract.py` uses synthetic iTunes backup
fixtures because creating real encrypted backups for testing would require an
actual iOS device and passphrase. The synthetic backups test the extraction
logic (Manifest.db parsing, hashed storage resolution) without needing real
backup content.

### What the Test Data Contains and Where It Comes From

The test data at `test-data/extracted/` contains:

- **ChatStorage.sqlite**: Real iOS WhatsApp database with:
  - 85 messages across 3 chats
  - Chat 1: Private chat ("Rayi"), 4 messages
  - Chat 2: Group chat ("JLI Instructors", `17189740857-1517518006@g.us`), 80 messages
  - Chat 3: Group chat, 1 message
  - 76 media items (most with NULL `local_path` --- downloaded but not cached locally)
  - 460 group members (across 2 groups)
  - 50 push names (JID -> display name mappings)
  - Message type distribution: 66 text, 5 image, 2 video, 3 system, 3 URL,
    1 document, 4 missed-call, 1 deleted
- **22 media files** under `Message/Media/` preserving original iOS paths
  (jpg, mp4, pdf, png, webp, thumb files). Of these, 8 are reachable via
  `local_path` references in the database.
- **Additional WhatsApp SQLite databases**: ContactsV2.sqlite, CallHistory.sqlite,
  and 6 others (not used by the tool but present in the extraction).

The data was extracted from the developer's own iTunes backup. It is gitignored
because it contains real personal WhatsApp messages and media.

### Why 150 Tests Across 7 Files

The test suite has 150 tests organized by concern:

| File | Count | Scope |
|------|-------|-------|
| `test_extract.py` | 25 | iOS parser correctness: counts, types, media linkage, JID parsing, push names, group members |
| `test_media.py` | 22 | Media path remapping: MIME detection, sequence counters, voice note detection, unknown MIME fallback, integration with full conversion |
| `test_convert.py` | 38 | Android schema creation, JID dedup, full conversion, timestamp spot-checks, type mapping, status codes, satellite tables (system messages, locations, group participants), deleted message handling |
| `test_e2e.py` | 28 | End-to-end pipeline: parse -> convert -> verify DB, CLI integration via `CliRunner`, selective chat transfer (`--chats` flag), error handling for bad inputs |
| `test_encrypt.py` | 5 | Crypt15 round-trip (encrypt then decrypt and verify), directory creation, error cases (missing DB, missing key, bad key length) |
| `test_backup_extract.py` | 14 | Backup type detection (encrypted/unencrypted/invalid), unencrypted extraction from synthetic iTunes backups, edge cases (no WhatsApp data, missing files, directories skipped) |
| `test_pipeline.py` | 18 | Full `run` command: media copy, crypt15 output, `--chats` filter, mutually exclusive flags, summary output |

The tests are designed for fast feedback: the corpus is parsed once per module
(`scope="module"`) and reused across tests. Only the output database is
recreated per test function.

---

## Phase-by-Phase Timeline

### Phase 0: Research and Specification (April 2026, days 1-3)

**What was implemented:**

- Six research documents (`research/01` through `research/06`) covering:
  open-source tools, iOS and Android database schemas, market/legal landscape,
  known issues with existing tools, alternative approaches (Baileys, WhatsApp
  Web protocol), and deep-dive on remaining gaps (restore mechanism, CDN expiry,
  modern message types).
- Full technical specification (`SPEC.md`): 9 sections covering problem
  statement, prior art, data formats, candidate approaches, experiments,
  technical design, implementation plan, risks, and references.
- Python project scaffold: CLI entrypoint with Typer stubs, domain model
  dataclasses, conversion mappings, package structure.

**Key decisions:**

- **Approach A** (Backup Extraction + DB Conversion) chosen over Approach B
  (WhatsApp Web Protocol) and Approach C (Hybrid). Rationale: complete data,
  proven pattern, no account risk, offline-capable.
- **Python 3.10+** selected as implementation language.
- **Modern Android schema only** (2022+ normalized).
- **Real test data** acquired from personal iTunes backup.

**Test count after phase: 0** (scaffold only, no implementation yet)

### Phase 1: Foundation and Extraction (April 2026)

**What was implemented:**

- iOS `ChatStorage.sqlite` parser (`wat.extract.__init__`).
- Five query functions: `_fetch_chats`, `_fetch_messages`, `_fetch_media`,
  `_fetch_group_members`, `_fetch_push_names`.
- Media objects linked to messages via the `ZMEDIAITEM` foreign key.
- JID parser (`_parse_jid`) splitting raw JID strings into user/server parts.
- The `parse_ios_db` entry point that returns a fully populated `Corpus`.

**Key decisions:**

- Media fetched separately into a `dict[int, Media]` map, then joined to
  messages during message fetch. This avoids a complex JOIN query and keeps
  the extraction code linear.
- `ZVCARDSTRING` read as `mime_type` with documentation of the naming confusion.
- `ios_type` defaults to 0 if `ZMESSAGETYPE` is NULL (defensive).
- `ios_timestamp` defaults to 0.0 if `ZMESSAGEDATE` is NULL.
- `is_group` derived from `ZGROUPINFO IS NOT NULL` rather than JID suffix
  matching, because some edge-case JIDs can be misleading.

**Test count after phase: 25** (`test_extract.py`)

### Phase 2: Schema Conversion -- Text Messages (April 2026)

**What was implemented:**

- Android `msgstore.db` DDL in `convert/android_schema.py` with 9 core tables.
- `create_android_db` function: creates file, sets PRAGMA, runs DDL.
- `_JidCache` class for JID deduplication with INSERT OR IGNORE + SELECT pattern.
- `_split_jid` utility for parsing `user@server` strings.
- `_insert_chats` with iOS PK -> Android `_id` mapping.
- `_insert_messages` with timestamp conversion, type mapping, status codes.
- `convert_corpus` entry point orchestrating the full conversion.
- Timestamp conversion: `(ios_ts + 978_307_200) * 1000`.
- Status mapping: outgoing -> 5 (delivered), incoming -> 0 (received),
  system -> 6.

**Key decisions:**

- Chat PK mapping (`dict[int, int]`) used to resolve message -> chat
  associations. iOS `Z_PK` is not reused as Android `_id` because Android
  uses autoincrement and the IDs may differ.
- `sender_jid_row_id` set to 0 for 1:1 incoming messages (Android convention),
  and to the actual JID row ID only for group messages from other participants.
- Sort order preserved directly: iOS `ZSORT` -> Android `sort_id`. No
  re-computation needed because the relative ordering is what matters.

**Test count after phase: 63** (25 + 38 in `test_convert.py`)

### Phase 3: Media Handling (April 2026)

**What was implemented:**

- `MediaRemapper` class with per-run sequence counter.
- Path remapping for images, videos, audio, voice notes, and documents.
- MIME type resolution chain: ZVCARDSTRING -> extension inference -> fallback.
- `_MIME_TO_EXT` and `_EXT_TO_MIME` lookup dictionaries.
- `_resolve_mime` and `_ext_for` helper functions.
- `remap_media_path` convenience wrapper.
- `message_media` table population during `_insert_messages`.

**Key decisions:**

- Voice notes identified by "ptt" substring in the iOS path, not by MIME type,
  because the MIME type for voice notes (`audio/ogg`) is identical to regular
  audio messages.
- Documents preserve their original filename (no renaming). Users expect to
  find their PDFs by name.
- The remapper returns `None` for `None` input paths (68 of 76 media items in
  test data have NULL `local_path`).

**Test count after phase: 85** (63 + 22 in `test_media.py`)

### Phase 4: Advanced Message Types (April 2026)

**What was implemented:**

- Location messages: `message_location` satellite table populated from
  `Media.latitude` / `Media.longitude` when `ios_type == 5`.
- Quoted messages: `message_quoted` table with `key_id` (stanza ID of the
  quoted message) and `text_data` (resolved from the same conversion batch
  via `stanza_text_map`).
- System messages: `message_system` table with `action_type = 0` (generic)
  for all iOS type 6 messages.
- Group participants: `group_participants` table with `gjid_row_id` (group's
  JID row ID) and `jid_row_id` (member's JID row ID).

**Key decisions:**

- Location coordinates only written when `ios_type == 5`. The iOS schema
  overloads `ZLATITUDE`/`ZLONGITUDE` for pixel dimensions on image messages,
  so writing them for non-location messages would corrupt the data.
- Quoted message text resolution is best-effort: only works for messages in
  the same conversion batch. Cross-batch references produce NULL `text_data`.
- `action_type = 0` used for all system messages because the iOS schema does
  not distinguish system message subtypes in a way that maps cleanly to
  Android's action_type codes.
- `group_participants.gjid_row_id` resolves through the `chat` table to get
  the group JID's row ID from the `jid` table, not the chat's row ID.

**Test count after phase: 85** (advanced types tested within existing test files;
satellite table tests added to `test_convert.py`)

### Phase 5: CLI Wiring and End-to-End Validation (April 2026)

**What was implemented:**

- CLI commands wired to real implementations: `extract`, `convert`, `encrypt`, `run`.
- `convert` command: parses iOS DB, runs conversion, prints Rich summary table.
- Error handling: `FileNotFoundError`, `sqlite3.DatabaseError`, `ValueError`.
- `_build_summary_table`: message type breakdown and chat count display.
- CLI tests via Typer's `CliRunner`.
- Documented rooted ADB push procedure in `docs/RESTORE.md`.
- Documented encrypted backup restore procedure.

**Key decisions:**

- CLI uses Typer's `exists=True` parameter on file/directory options for early
  validation before our code runs.
- Error messages use Rich markup (`[red]Error:[/red]`) for visual clarity.
- The `convert` command always prints a summary table, even for small conversions.

**Test count after phase: 113** (85 + 28 in `test_e2e.py`)

### Phase 6: Selective Chat Transfer (April 2026)

**What was implemented:**

- `--chats` flag on `convert` and `run` commands.
- `_filter_corpus` function: parses comma-separated tokens, filters by PK
  (integer) or name (case-insensitive substring).
- Filtered corpus preserves only selected chats, their messages, and their
  group members. Push names are preserved in full (cheap and potentially useful).

**Key decisions:**

- Empty `--chats` value raises `ValueError` rather than silently returning all
  chats. Explicit is better than implicit.
- Non-matching filter raises `ValueError` with a helpful message listing
  available chat names: `"No chats matched --chats='NoSuchChat'. Available: ..."`.
- Group members filtered by `chat_pk` to avoid including members from unselected
  groups.

**Test count after phase: 113** (selective transfer tests are part of `test_e2e.py`)

### Phase 7: Encryption (April 2026)

**What was implemented:**

- `wat.encrypt` module with `encrypt_db` function.
- Integration with `wa-crypt-tools`: `Key15` for key handling, `Database15` for
  crypt15 container format, `Props` for metadata.
- `encrypt` CLI command: `--db`, `--key`, `--out` flags.
- Validation: key file must be exactly 32 bytes.

**Key decisions:**

- Compression level 1 (matching WhatsApp's convention).
- Random IV generated per encryption (by `Database15`), ensuring unique output
  even for identical inputs.
- Output directory auto-created (`output_path.parent.mkdir(parents=True)`).

**Test count after phase: 118** (113 + 5 in `test_encrypt.py`)

### Phase 8: iTunes Backup Extraction (April 2026)

**What was implemented:**

- `wat.extract.backup` module.
- `detect_backup_type`: checks `Manifest.db` and `Manifest.plist` for
  encryption status.
- `extract_from_unencrypted_backup`: parses `Manifest.db`, resolves SHA-1 file
  IDs, copies from hashed storage.
- `extract_from_encrypted_backup`: wraps `iphone_backup_decrypt` library.
- `extract_backup`: unified entry point with auto-detection.
- `extract` CLI command.

**Key decisions:**

- LIKE-based domain matching (`%net.whatsapp.%`) rather than exact domain string
  to handle potential variations.
- `flags = 1` filter to skip directory entries in `Manifest.db`.
- Graceful handling of missing source files (skipped, not errored).
- Encrypted extraction uses `iphone_backup_decrypt`'s `DomainLike.WHATSAPP` and
  `RelativePath.WHATSAPP_MESSAGES` constants for robust file identification.

**Test count after phase: 132** (118 + 14 in `test_backup_extract.py`)

### Phase 9: Media Copy and Schema Robustness (April 2026)

**What was implemented:**

- `copy_media_files` function in `convert/media.py`.
- File copy using `shutil.copy2` (preserves metadata).
- Source resolution: `ios_media_dir / msg.media.local_path`.
- Stats tracking: copied, skipped, missing.
- Additional empty tables in DDL: `message_add_on`, `message_forwarded`,
  `receipt_device`, `receipt_user`, `props`, `message_thumbnail`, `audio_data`.
- `props` table seeded with `schema_version = '1'`.

**Key decisions:**

- The same `MediaRemapper` instance used for both DB path writing and file
  copying, ensuring path consistency.
- Missing source files are counted but do not fail the pipeline. Users expect
  some media to be unavailable (expired cloud links, etc.).
- `copy2` used instead of `copy` to preserve modification timestamps, which
  helps WhatsApp's media scanner.

**Test count after phase: 132** (media copy tests added to `test_pipeline.py`)

### Phase 10: Full Pipeline (April 2026)

**What was implemented:**

- `run` CLI command chaining all stages: extract -> parse -> convert -> media
  copy -> encrypt.
- Mutual exclusion of `--ios` and `--backup` flags.
- Temporary directory management for `--backup` mode.
- Rich summary table with message type breakdown and media stats.
- `--chats` filter support in the `run` command.
- Error handling and progress reporting (`console.status` spinners).
- Output directory structure: `WhatsApp/Databases/msgstore.db[.crypt15]` and
  `WhatsApp/Media/`.

**Key decisions:**

- Output structure mirrors Android's internal WhatsApp directory layout so
  files can be directly pushed via ADB.
- Temporary directory cleaned up in a `finally` block to prevent disk space
  leaks.
- Pipeline failures at any stage produce a clear error message and non-zero
  exit code.

**Test count after phase: 150** (132 + 18 in `test_pipeline.py`)

### Phase 11: Documentation (April 2026)

**What was implemented:**

- `JOURNAL.md` (this document): development journal.
- `NEXT_STEPS.md`: roadmap for future work and babysitter orchestration notes.
- `docs/RESTORE.md`: user-facing restore instructions.
- `docs/ACQUIRING_SAMPLE_DATA.md`: how to obtain test data.

**Key decisions:**

- Documentation kept in the repository alongside code, not in a separate wiki.
- `NEXT_STEPS.md` written to enable continuity if development moves to a
  different machine or developer.

**Test count after phase: 150** (no new tests; documentation only)

---

## Known Limitations

- **No merge capability.** The tool creates a fresh `msgstore.db`. It cannot
  merge into an existing Android backup that already has messages. This is the
  most frequently requested feature in competing tools and the hardest to
  implement correctly (WhatsApp may have internal consistency checks).

- **No quoted message content across batches.** `message_quoted.text_data` is
  populated when the quoted message exists in the same conversion batch, but
  cross-batch references (e.g., quoting a message from a chat not included in
  `--chats`) produce NULL text.

- **No vCard population.** `message_vcard` table is created but never written
  to. Contact card messages (iOS type 4) are converted as type 4 in Android
  but without the actual vCard data in the satellite table.

- **No reactions/edits/polls/disappearing.** These use newer Android schema
  features (`message_add_on` table, types 56/68/74) that are not yet mapped
  from iOS. The `message_add_on` table is created empty.

- **Device testing pending.** Output has not yet been validated on a real
  Android device. All verification is against schema structure and data
  integrity, not WhatsApp's runtime behavior.

- **No EXIF date injection.** Media files are copied with original metadata
  preserved via `shutil.copy2`, but EXIF dates are not updated to match
  message timestamps. Photos may appear under the wrong date in the device
  gallery.

- **No FTS index rebuilding.** WhatsApp's full-text search indexes are not
  populated. WhatsApp should rebuild these automatically on first launch, but
  this is untested.
