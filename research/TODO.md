# Research TODO — Remaining Gaps

## Must-Have Before Spec

- [ ] **Android restore mechanism**: How does WhatsApp on Android detect and restore a local backup? What file path, filename, format (`msgstore.db` vs `.crypt15` wrapper)? Does it validate checksums, schema version, or triggers? What happens if validation fails?

- [ ] **The paracycle gist**: Read the actual SQL conversion code at https://gist.github.com/paracycle/6107205. This is the iOS→Android column mapping Rosetta Stone. Document what's outdated vs still valid for current WhatsApp schema.

- [ ] **Modern message types**: Reactions, message edits, polls, disappearing messages, view-once media, channels, communities, pinned messages. What tables/columns handle these in each platform? Would they survive a naive conversion or silently vanish?

- [ ] **Media re-download via CDN**: The databases store `media_key` and `media_url`/`message_url`. Can media be re-downloaded from WhatsApp CDN using those keys after transfer? How long do CDN URLs stay valid? This could eliminate the need to copy media files entirely.

- [ ] **Baileys history sync payload format**: What exactly comes back in the `messaging-history.set` event? Protobuf schema? How complete is it in practice? Has anyone documented real-world completeness (e.g., "got 6 months of history" vs "got everything")?

- [ ] **WhatsApp version ↔ schema version mapping**: Which DB schema changes correspond to which WhatsApp app versions? How do we detect which schema we're dealing with? Is there a version marker in the database itself?

- [ ] **The actual WazzapMigrator restore trick**: Their flow ends with "reinstall WhatsApp → it detects local backup → restore." What exact path and filename does WhatsApp for Android check? Is it `/sdcard/WhatsApp/Databases/msgstore.db.crypt15`? Can it be an unencrypted `msgstore.db`?
