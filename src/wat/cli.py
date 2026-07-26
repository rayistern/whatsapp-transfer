"""Typer CLI entrypoint for wat.

Subcommands correspond to pipeline stages so each can be run independently
during development and debugging:

    wat extract   --backup <dir> --out <dir>
    wat convert   --ios <ChatStorage.sqlite> --out <msgstore.db>
    wat encrypt   --db <msgstore.db> --key <keyfile> --out <msgstore.db.crypt15>
    wat run       --backup <dir> --key <keyfile> --out <dir>

Only stubs are wired up at scaffold time; real implementations land in their
respective phases (see plan file).
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from typing import Optional

from wat.extract import parse_ios_db
from wat.extract.backup import extract_backup
from wat.convert.writer import convert_corpus
from wat.convert.media import MediaRemapper, copy_media_files
from wat.encrypt import encrypt_db
from wat.model import Corpus

app = typer.Typer(
    add_completion=False,
    help="Convert an iTunes WhatsApp backup into an Android msgstore.db.crypt15.",
)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Map iOS message types to human-readable category names for the summary table.
# These labels are display-only (not used in conversion logic).
_TYPE_LABELS: dict[int, str] = {
    0: "text",
    1: "image",
    2: "video",
    3: "audio",
    4: "contact",
    5: "location",
    6: "system",
    7: "text",      # URL rendered as text on Android
    8: "document",
    10: "text",     # missed call / group event -> text
    14: "other",    # deleted/revoked
}


def _build_summary_table(corpus: Corpus) -> Table:
    """Build a Rich table summarising the corpus by message type and chat."""
    # --- message counts by category ---
    cat_counter: Counter[str] = Counter()
    for m in corpus.messages:
        cat_counter[_TYPE_LABELS.get(m.ios_type, "other")] += 1

    tbl = Table(title="Conversion Summary", show_lines=False)
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Count", justify="right")

    ordered = ["text", "image", "video", "audio", "document", "system", "other"]
    for cat in ordered:
        if cat_counter[cat]:
            tbl.add_row(f"  {cat}", str(cat_counter[cat]))

    tbl.add_row("Total messages", str(len(corpus.messages)), style="bold")

    # --- chat breakdown ---
    n_private = sum(1 for c in corpus.chats if not c.is_group)
    n_group = sum(1 for c in corpus.chats if c.is_group)
    tbl.add_row("Chats (private)", str(n_private))
    tbl.add_row("Chats (group)", str(n_group))

    return tbl


def _add_media_rows(tbl: Table, media_stats: dict) -> None:
    """Append media-copy rows to an existing summary table."""
    tbl.add_row("Media copied", str(media_stats["copied"]))
    tbl.add_row("Media skipped", str(media_stats["skipped"]))
    tbl.add_row("Media missing", str(media_stats["missing"]))


def _filter_corpus(corpus: Corpus, chats_spec: str) -> Corpus:
    """Return a new Corpus containing only the chats matching *chats_spec*.

    *chats_spec* is a comma-separated string where each token is interpreted as:
      - an integer  -> match by ``Chat.pk`` (useful for scripting / exact selection)
      - a string    -> case-insensitive substring match against ``Chat.partner_name``
                       (useful for interactive use: ``--chats "John,Family Group"``)

    This dual-mode matching (PKs and names) lets users filter chats without
    needing to look up internal IDs first. The function builds a set of
    matching chat PKs, then returns a new Corpus with only the matching
    chats, their messages, and their group members. push_names are kept
    in full (they're lightweight and may be needed for display-name lookups
    even for contacts outside the selected chats).
    """
    tokens = [t.strip() for t in chats_spec.split(",") if t.strip()]
    if not tokens:
        raise ValueError("--chats value is empty")

    pk_filters: list[int] = []
    name_filters: list[str] = []
    for tok in tokens:
        try:
            pk_filters.append(int(tok))
        except ValueError:
            name_filters.append(tok.lower())

    selected_pks: set[int] = set()
    for chat in corpus.chats:
        if chat.pk in pk_filters:
            selected_pks.add(chat.pk)
        for nf in name_filters:
            if chat.partner_name and nf in chat.partner_name.lower():
                selected_pks.add(chat.pk)

    if not selected_pks:
        raise ValueError(
            f"No chats matched --chats={chats_spec!r}. "
            f"Available: {', '.join(repr(c.partner_name) for c in corpus.chats)}"
        )

    filtered_chats = [c for c in corpus.chats if c.pk in selected_pks]
    filtered_messages = [m for m in corpus.messages if m.chat_pk in selected_pks]
    filtered_members = [gm for gm in corpus.group_members if gm.chat_pk in selected_pks]

    return Corpus(
        chats=filtered_chats,
        messages=filtered_messages,
        group_members=filtered_members,
        push_names=corpus.push_names,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def extract(
    backup: Path = typer.Option(..., exists=True, file_okay=False, help="iTunes backup directory."),
    out: Path = typer.Option(..., file_okay=False, help="Output directory for extracted files."),
    password: Optional[str] = typer.Option(None, help="Backup encryption passphrase (if encrypted)."),
) -> None:
    """Phase 1: pull ChatStorage.sqlite and Message/Media/* from an iTunes backup."""
    try:
        with console.status("Extracting backup..."):
            stats = extract_backup(backup, out, password=password)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[green]Extracted {stats['files_extracted']} files[/green]")
    if stats["chat_storage_found"]:
        console.print("[green]ChatStorage.sqlite found[/green]")
    else:
        console.print("[yellow]Warning: ChatStorage.sqlite not found in backup[/yellow]")
    console.print(f"Output: {out}")


@app.command()
def convert(
    ios: Path = typer.Option(..., exists=True, dir_okay=False, help="Path to ChatStorage.sqlite."),
    out: Path = typer.Option(..., dir_okay=False, help="Output msgstore.db to create."),
    chats: Optional[str] = typer.Option(None, help="Comma-separated chat PKs or names to include."),
) -> None:
    """Phase 3+: convert iOS ChatStorage.sqlite into an Android msgstore.db."""
    try:
        with console.status("Parsing iOS database..."):
            corpus = parse_ios_db(ios)

        if chats is not None:
            corpus = _filter_corpus(corpus, chats)
            console.print(
                f"Filtered to {len(corpus.chats)} chat(s), "
                f"{len(corpus.messages)} messages"
            )

        with console.status("Converting to Android format..."):
            convert_corpus(corpus, out)

        console.print(
            f"[green]Converted {len(corpus.messages)} messages, "
            f"{len(corpus.chats)} chats[/green]"
        )
        console.print(f"Output: {out}")
        console.print()
        console.print(_build_summary_table(corpus))
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)
    except sqlite3.DatabaseError as exc:
        console.print(f"[red]Error:[/red] Invalid database: {exc}")
        raise typer.Exit(code=1)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def encrypt(
    db: Path = typer.Option(..., exists=True, dir_okay=False, help="Unencrypted msgstore.db."),
    key: Path = typer.Option(..., exists=True, dir_okay=False, help="WhatsApp encryption key file."),
    out: Path = typer.Option(..., dir_okay=False, help="Output msgstore.db.crypt15."),
) -> None:
    """Phase 7: wrap msgstore.db as a .crypt15 using wa-crypt-tools."""
    try:
        with console.status("Encrypting..."):
            encrypt_db(db, key, out)
        console.print(f"[green]Encrypted[/green] {db} -> {out}")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def run(
    ios: Optional[Path] = typer.Option(None, exists=True, file_okay=False, help="Already-extracted iOS data directory."),
    backup: Optional[Path] = typer.Option(None, exists=True, file_okay=False, help="iTunes backup directory."),
    out: Path = typer.Option(..., file_okay=False, help="Output directory (will hold WhatsApp/ tree)."),
    key: Optional[Path] = typer.Option(None, exists=True, dir_okay=False, help="WhatsApp encryption key file."),
    password: Optional[str] = typer.Option(None, help="Backup encryption passphrase (if encrypted)."),
    chats: Optional[str] = typer.Option(None, help="Comma-separated chat PKs or names to include."),
) -> None:
    """Full pipeline -- extract, convert, remap media, encrypt."""
    import tempfile

    # --ios and --backup are mutually exclusive because they represent two
    # different starting points for the pipeline:
    # - --backup: raw iTunes backup directory (needs extraction first)
    # - --ios: already-extracted directory (skip extraction, go straight to parse)
    # Providing both would be ambiguous — which source wins? Rather than
    # defining precedence rules, we require exactly one.
    if ios and backup:
        console.print("[red]Error:[/red] --ios and --backup are mutually exclusive.")
        raise typer.Exit(code=1)
    if not ios and not backup:
        console.print("[red]Error:[/red] provide either --ios or --backup.")
        raise typer.Exit(code=1)

    # Step 1: determine extracted_dir
    tmp_dir_obj = None
    if backup:
        tmp_dir_obj = tempfile.TemporaryDirectory(prefix="wat_")
        tmp_dir = Path(tmp_dir_obj.name)
        try:
            with console.status("Extracting backup..."):
                stats = extract_backup(backup, tmp_dir, password=password)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1)
        console.print(f"[green]Extracted {stats['files_extracted']} files from backup[/green]")
        extracted_dir = tmp_dir
    else:
        assert ios is not None
        extracted_dir = ios

    try:
        # Step 2: parse
        db_path = extracted_dir / "ChatStorage.sqlite"
        if not db_path.exists():
            console.print(f"[red]Error:[/red] ChatStorage.sqlite not found in {extracted_dir}")
            raise typer.Exit(code=1)

        with console.status("Parsing iOS database..."):
            corpus = parse_ios_db(db_path)
        console.print(f"Parsed {len(corpus.messages)} messages, {len(corpus.chats)} chats")

        # Optional chat filtering
        if chats is not None:
            try:
                corpus = _filter_corpus(corpus, chats)
            except ValueError as exc:
                console.print(f"[red]Error:[/red] {exc}")
                raise typer.Exit(code=1)
            console.print(
                f"Filtered to {len(corpus.chats)} chat(s), "
                f"{len(corpus.messages)} messages"
            )

        # Step 3: convert
        out.mkdir(parents=True, exist_ok=True)
        db_out = out / "WhatsApp" / "Databases" / "msgstore.db"
        db_out.parent.mkdir(parents=True, exist_ok=True)
        with console.status("Converting to Android format..."):
            convert_corpus(corpus, db_out)
        console.print(f"[green]Wrote[/green] {db_out}")

        # Step 4: copy media
        ios_media_dir = extracted_dir / "Message"
        android_media_dir = out / "WhatsApp" / "Media"
        android_media_dir.mkdir(parents=True, exist_ok=True)

        remapper = MediaRemapper()
        with console.status("Copying media files..."):
            media_stats = copy_media_files(ios_media_dir, android_media_dir, remapper, corpus.messages)
        console.print(
            f"Media: [green]{media_stats['copied']} copied[/green], "
            f"{media_stats['skipped']} skipped, "
            f"[yellow]{media_stats['missing']} missing[/yellow]"
        )

        # Step 5: encrypt (optional)
        if key:
            with console.status("Encrypting database..."):
                crypt_out = out / "WhatsApp" / "Databases" / "msgstore.db.crypt15"
                encrypt_db(db_out, key, crypt_out)
            console.print(f"[green]Encrypted[/green] -> {crypt_out}")

        # Summary table
        tbl = _build_summary_table(corpus)
        _add_media_rows(tbl, media_stats)
        console.print()
        console.print(tbl)

        console.print("\n[bold green]Pipeline complete.[/bold green]")
        console.print(f"Output directory: {out}")

    except sqlite3.DatabaseError as exc:
        console.print(f"[red]Error:[/red] Invalid database: {exc}")
        raise typer.Exit(code=1)
    finally:
        if tmp_dir_obj is not None:
            tmp_dir_obj.cleanup()


def _not_implemented(stage: str) -> int:
    console.print(f"[yellow]{stage}[/yellow] is not implemented yet. See plan file.")
    return 2


if __name__ == "__main__":
    app()
