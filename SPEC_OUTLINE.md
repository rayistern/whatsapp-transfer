# SPEC OUTLINE — WhatsApp iPhone→Android Transfer Tool

## 1. Problem Statement
- What users need and why it's hard
- Why the market is thin (schema differences, encryption, legal gray zone)
- Official transfer limitations (factory reset, no merge, sort order bugs)

## 2. Prior Art
- Commercial tools (Wondershare, Tenorshare, Mobitrix, WazzapMigrator)
- Open-source tools (watoi, Kethen/WhatsAppIphoneToAndroid, paracycle gist, WhatsApp-Chat-Exporter)
- What each gets right and wrong

## 3. Data Formats
- iOS: ChatStorage.sqlite schema (ZWAMESSAGE, ZWAMEDIAITEM, ZWACHATSESSION)
- Android: msgstore.db schema (message, message_media, chat, jid — modern normalized)
- Key differences table (column mappings, timestamp epochs, message type codes)
- Media storage paths on each platform

## 4. Three Candidate Approaches
- **A: Backup Extraction + DB Conversion** (iTunes backup → parse → convert → Android backup)
- **B: WhatsApp Web Protocol** (Baileys/whatsmeow → history sync → write to target)
- **C: Hybrid** (A for complete history, B to fill gaps)
- Pros/cons matrix for each

## 5. Experiments (BEFORE choosing a direction)
- **Experiment 1:** Parse a real ChatStorage.sqlite — verify schema matches documentation
- **Experiment 2:** Parse a real msgstore.db — verify modern schema, detect version
- **Experiment 3:** Baileys history sync — connect, measure how much history arrives, inspect protobuf format
- **Experiment 4:** Android restore — can we produce a msgstore.db that WhatsApp accepts? (root path)
- **Experiment 5:** wa-crypt-tools — can we re-encrypt a modified msgstore.db into valid .crypt15?
- **Experiment 6:** End-to-end smoke test — take a known iOS message, convert, restore on Android, verify it displays correctly
- Each experiment has: hypothesis, setup, procedure, success criteria, results (TBD)

## 6. Technical Design (filled in AFTER experiments)
- Chosen approach with rationale
- Architecture diagram
- Data flow
- Schema conversion logic (SQL mappings updated for modern schema)
- Media handling strategy
- Restore mechanism

## 7. Implementation Plan
- Phase 1: iOS backup extraction + parsing
- Phase 2: Schema conversion (messages, chats, contacts)
- Phase 3: Media file handling
- Phase 4: Android database generation
- Phase 5: Android restore (root path first, then encrypted backup path)
- Phase 6: Verification & edge cases (groups, reactions, edits, etc.)
- Tech stack recommendation

## 8. Known Risks & Open Questions
- Schema drift (WhatsApp updates break things)
- Legal considerations (ToS, DMCA interoperability exemption, GDPR)
- Modern message types that may not survive conversion
- Media CDN expiry (30 days — must extract from backup)
- Baileys history sync completeness (best-effort)

## 9. References
- All research docs (01 through 06)
- Key GitHub repos, papers, blog posts
