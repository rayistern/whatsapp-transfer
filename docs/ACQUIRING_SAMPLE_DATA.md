# Acquiring Sample Data

The project is gated on two real-data fixtures before we can meaningfully
implement conversion:

1. **`ChatStorage.sqlite`** — a real iOS WhatsApp database, for Experiment 1
2. **`msgstore.db`** (decrypted) — a real modern Android WhatsApp database, for
   Experiment 2 and as the source of the target schema DDL

We also need one **WhatsApp key file** (for the `.crypt15` re-encryption step
in Phase 7).

> **Privacy:** None of these files should ever land in git in their raw form.
> Drop them into `experiments/_raw/` (already gitignored). Only commit
> deliberately anonymized fixtures into `tests/fixtures/` once we have a
> scrubbing script.

---

## 1. Getting `ChatStorage.sqlite` from an iPhone

The recommended path is an **unencrypted iTunes / Finder backup**. WhatsApp
stores the DB under the shared app group and backs it up by default.

### macOS (Finder)

1. Plug the iPhone into a Mac running Finder (macOS 10.15+).
2. In the device sidebar → General tab → "Back up all of the data on your
   iPhone to this Mac". **Leave "Encrypt local backup" _off_** for the
   easy path. (Encrypted is also supported — see §1a.)
3. Click "Back Up Now". Wait for completion.
4. Backup location: `~/Library/Application Support/MobileSync/Backup/<UDID>/`

### Windows (iTunes / Apple Devices app)

1. Install "Apple Devices" from the Microsoft Store (or iTunes).
2. Back up locally, unencrypted.
3. Backup location: `%APPDATA%\Apple Computer\MobileSync\Backup\<UDID>\`

### Extracting `ChatStorage.sqlite` from the backup

The file lives under the domain
`AppDomainGroup-group.net.whatsapp.WhatsApp.shared` at the relative path
`ChatStorage.sqlite`. iTunes backups store files under hashed names, resolved
via `Manifest.db`.

We'll automate this in `wat extract`, but for now you can do it by hand:

```sh
# Using our eventual CLI (not implemented yet)
wat extract --backup ~/Library/Application\ Support/MobileSync/Backup/<UDID> \
            --out  experiments/_raw/ios
```

or with any third-party backup explorer (iMazing, iBackup Viewer, `idevicebackup2`).

### 1a. Encrypted backups

If "Encrypt local backup" is on, we use the `iphone_backup_decrypt` Python
library. You'll need the backup password. We'll wire this into `wat extract`
automatically.

### What to drop where

```
experiments/_raw/ios/
  ChatStorage.sqlite
  Message/Media/   # optional but needed for media experiments
```

---

## 2. Getting a decrypted modern `msgstore.db` from Android

The goal is to capture a real, current (2022+ normalized) `msgstore.db` so we
can (a) diff against our schema documentation, (b) extract the full DDL as our
emission template, and (c) sanity-check that our converter output "looks like"
a real one.

You have **three viable paths**, in order of ease:

### Path A — Local backup + key file (no root, modern Android)

1. On an Android phone with WhatsApp installed, back up locally:
   *WhatsApp → Settings → Chats → Chat backup → "Back up"*.
   This writes `msgstore.db.crypt15` under
   `Android/media/com.whatsapp/WhatsApp/Databases/`.
2. Obtain the **encryption key**. Options:
   - If you set an **end-to-end encryption password**, you have a 64-digit
     key shown once during setup. `wa-crypt-tools` accepts this.
   - Otherwise on Android ≤ 9 the key sits at
     `/data/data/com.whatsapp/files/key` and can be pulled via an
     `adb backup` trick. On Android 10+ this is only accessible via root.
3. Decrypt:
   ```sh
   pip install wa-crypt-tools
   wadecrypt <keyfile> msgstore.db.crypt15 msgstore.db
   ```
4. Drop the decrypted file:
   ```
   experiments/_raw/android/msgstore.db
   experiments/_raw/android/key          # keep the key for Phase 7
   ```

### Path B — Rooted device / emulator (simplest if available)

1. Root an Android test device, or use a rooted AVD (`rooted` variant).
2. Install WhatsApp, register, send a few test messages (mixed text + image +
   voice + group + reply).
3. Pull directly:
   ```sh
   adb root
   adb pull /data/data/com.whatsapp/databases/msgstore.db experiments/_raw/android/
   adb pull /data/data/com.whatsapp/files/key            experiments/_raw/android/
   ```
   This bypasses crypt15 entirely.

### Path C — Android emulator (Google APIs image, no root)

Works but you still need one of the decryption methods in Path A. Less
recommended — only use if you can't root an AVD.

### What to drop where

```
experiments/_raw/android/
  msgstore.db        # decrypted
  key                # WhatsApp key file (binary)
```

---

## 3. Seed content recommendation

For meaningful experiments, send these before taking the backup:

- 1:1 chat with ~10 text messages in both directions
- At least one **image**, one **video**, one **voice note**, one **document**
- A **group chat** with 3+ participants and at least one system event
  ("X created group", "Y was added")
- A **quoted reply**
- A **location** share
- A **starred** message
- (Nice-to-have, not yet in MVP) a reaction and an edit

---

## 4. After you have the files

1. Put them under `experiments/_raw/` (gitignored).
2. Ping back so we start **Phase 1 (Experiment 1)** — parse
   `ChatStorage.sqlite` and diff its schema against `SPEC.md §3.1`.
3. Then **Phase 2 (Experiment 2)** — capture the modern msgstore DDL from the
   decrypted `msgstore.db` and commit it to `src/wat/convert/schema.sql`.
