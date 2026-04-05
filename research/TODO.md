# Research TODO — Remaining Gaps

## Must-Have Before Spec

- [x] **Android restore mechanism**: Two paths found. Path A: encrypted `.crypt15` at `Android/media/com.whatsapp/WhatsApp/Databases/`. Path B: root — unencrypted `msgstore.db` directly in `/data/data/com.whatsapp/databases/` with correct ownership. See `06-deep-dive-remaining-gaps.md`.

- [x] **The paracycle gist**: Full SQL extracted and analyzed. Column mappings are valid but **targets legacy schema** (`messages` plural). Modern WhatsApp uses normalized `message` + satellite tables. Needs rewriting. See `06-deep-dive-remaining-gaps.md`.

- [x] **Modern message types**: Reactions via `message_add_on` (type 56), edits (type 74), disappearing via `message_ephemeral`. Polls and channels poorly documented. These would be lost in a naive conversion. See `06-deep-dive-remaining-gaps.md`.

- [x] **Media re-download via CDN**: **NOT viable.** URLs expire after ~30 days. Media must be extracted from source backup/device. See `06-deep-dive-remaining-gaps.md`.

- [x] **Baileys history sync payload format**: Returns `proto.IWebMessageInfo` protobuf. Platform-agnostic. On-demand backfill available but best-effort. See `06-deep-dive-remaining-gaps.md`.

- [x] **WhatsApp version ↔ schema version mapping**: No clean version marker. Detect by checking table names (`message` vs `messages`, presence of `jid` table, etc.). The schema split happened ~v2.22.x (2022). See `06-deep-dive-remaining-gaps.md`.

- [x] **The WazzapMigrator restore trick**: Uses Path A — places converted backup in the Databases folder. WhatsApp detects it on fresh install. Must be encrypted (`.crypt15`). See `06-deep-dive-remaining-gaps.md`.
