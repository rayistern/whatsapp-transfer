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
    backup: Path = typer.Option(..., exists=True, file_okay=False, help="iTunes backup directory."),
    key: Path = typer.Option(..., exists=True, dir_okay=False, help="WhatsApp encryption key file."),
    out: Path = typer.Option(..., file_okay=False, help="Output directory (will hold WhatsApp/ tree)."),
) -> None:
    """Phase 7: full pipeline — extract, convert, remap media, encrypt."""
    raise typer.Exit(code=_not_implemented("run"))


def _not_implemented(stage: str) -> int:
    console.print(f"[yellow]{stage}[/yellow] is not implemented yet. See plan file.")
    return 2


if __name__ == "__main__":
    app()
