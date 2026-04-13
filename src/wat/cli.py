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

from pathlib import Path

import typer
from rich.console import Console

from typing import Optional

from wat.extract import parse_ios_db
from wat.extract.backup import extract_backup
from wat.convert.writer import convert_corpus
from wat.convert.media import MediaRemapper, copy_media_files
from wat.encrypt import encrypt_db

app = typer.Typer(
    add_completion=False,
    help="Convert an iTunes WhatsApp backup into an Android msgstore.db.crypt15.",
)
console = Console()


@app.command()
def extract(
    backup: Path = typer.Option(..., exists=True, file_okay=False, help="iTunes backup directory."),
    out: Path = typer.Option(..., file_okay=False, help="Output directory for extracted files."),
    password: Optional[str] = typer.Option(None, help="Backup encryption passphrase (if encrypted)."),
) -> None:
    """Phase 1: pull ChatStorage.sqlite and Message/Media/* from an iTunes backup."""
    try:
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
) -> None:
    """Phase 3+: convert iOS ChatStorage.sqlite into an Android msgstore.db."""
    corpus = parse_ios_db(ios)
    convert_corpus(corpus, out)
    console.print(
        f"[green]Converted {len(corpus.messages)} messages, "
        f"{len(corpus.chats)} chats[/green]"
    )
    console.print(f"Output: {out}")


@app.command()
def encrypt(
    db: Path = typer.Option(..., exists=True, dir_okay=False, help="Unencrypted msgstore.db."),
    key: Path = typer.Option(..., exists=True, dir_okay=False, help="WhatsApp encryption key file."),
    out: Path = typer.Option(..., dir_okay=False, help="Output msgstore.db.crypt15."),
) -> None:
    """Phase 7: wrap msgstore.db as a .crypt15 using wa-crypt-tools."""
    encrypt_db(db, key, out)
    console.print(f"[green]Encrypted[/green] {db} -> {out}")


@app.command()
def run(
    ios: Optional[Path] = typer.Option(None, exists=True, file_okay=False, help="Already-extracted iOS data directory."),
    backup: Optional[Path] = typer.Option(None, exists=True, file_okay=False, help="iTunes backup directory."),
    out: Path = typer.Option(..., file_okay=False, help="Output directory (will hold WhatsApp/ tree)."),
    key: Optional[Path] = typer.Option(None, exists=True, dir_okay=False, help="WhatsApp encryption key file."),
    password: Optional[str] = typer.Option(None, help="Backup encryption passphrase (if encrypted)."),
) -> None:
    """Full pipeline -- extract, convert, remap media, encrypt."""
    import tempfile

    # Validate mutually-exclusive sources
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

        corpus = parse_ios_db(db_path)
        console.print(f"Parsed {len(corpus.messages)} messages, {len(corpus.chats)} chats")

        # Step 3: convert
        out.mkdir(parents=True, exist_ok=True)
        db_out = out / "WhatsApp" / "Databases" / "msgstore.db"
        db_out.parent.mkdir(parents=True, exist_ok=True)
        convert_corpus(corpus, db_out)
        console.print(f"[green]Wrote[/green] {db_out}")

        # Step 4: copy media
        ios_media_dir = extracted_dir / "Message"
        android_media_dir = out / "WhatsApp" / "Media"
        android_media_dir.mkdir(parents=True, exist_ok=True)

        # Use a second remapper with the same settings so paths match
        # Note: convert_corpus uses its own internal remapper; we need a fresh
        # one here that will produce paths consistent with what the DB has.
        # Since both start from seq=0 and process messages in the same order,
        # the paths will match.
        remapper = MediaRemapper()
        media_stats = copy_media_files(ios_media_dir, android_media_dir, remapper, corpus.messages)
        console.print(
            f"Media: [green]{media_stats['copied']} copied[/green], "
            f"{media_stats['skipped']} skipped, "
            f"[yellow]{media_stats['missing']} missing[/yellow]"
        )

        # Step 5: encrypt (optional)
        if key:
            crypt_out = out / "WhatsApp" / "Databases" / "msgstore.db.crypt15"
            encrypt_db(db_out, key, crypt_out)
            console.print(f"[green]Encrypted[/green] -> {crypt_out}")

        # Summary
        console.print("\n[bold green]Pipeline complete.[/bold green]")
        console.print(f"Output directory: {out}")

    finally:
        if tmp_dir_obj is not None:
            tmp_dir_obj.cleanup()


def _not_implemented(stage: str) -> int:
    console.print(f"[yellow]{stage}[/yellow] is not implemented yet. See plan file.")
    return 2


if __name__ == "__main__":
    app()
