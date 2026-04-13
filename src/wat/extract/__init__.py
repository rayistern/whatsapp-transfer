"""Parse an iOS ChatStorage.sqlite into the neutral domain model."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from wat.model import Chat, Corpus, GroupMember, Jid, Media, Message


def _parse_jid(raw: str) -> Jid:
    """Split a raw JID string like '14155551234@s.whatsapp.net' into parts."""
    if "@" in raw:
        user, server = raw.split("@", 1)
    else:
        user, server = raw, ""
    return Jid(raw=raw, user=user, server=server)


def _fetch_chats(conn: sqlite3.Connection) -> list[Chat]:
    rows = conn.execute(
        """
        SELECT Z_PK, ZCONTACTJID, ZPARTNERNAME, ZGROUPINFO, ZLASTMESSAGEDATE
        FROM ZWACHATSESSION
        ORDER BY Z_PK
        """
    ).fetchall()
    return [
        Chat(
            pk=r[0],
            partner_jid=r[1] or "",
            partner_name=r[2],
            is_group=r[3] is not None,
            last_message_ts_ios=r[4],
        )
        for r in rows
    ]


def _fetch_media(conn: sqlite3.Connection) -> dict[int, Media]:
    rows = conn.execute(
        """
        SELECT Z_PK, ZMEDIALOCALPATH, ZVCARDSTRING, ZMEDIAKEY,
               ZFILESIZE, ZMOVIEDURATION, ZLATITUDE, ZLONGITUDE, ZTITLE
        FROM ZWAMEDIAITEM
        """
    ).fetchall()
    result: dict[int, Media] = {}
    for r in rows:
        result[r[0]] = Media(
            local_path=r[1],
            mime_type=r[2],
            media_key=r[3],
            file_size=int(r[4]) if r[4] is not None else None,
            width=None,   # not in this iOS schema version
            height=None,  # not in this iOS schema version
            duration=int(r[5]) if r[5] is not None else None,
            latitude=r[6],
            longitude=r[7],
            title=r[8],
        )
    return result


def _fetch_messages(
    conn: sqlite3.Connection, media_map: dict[int, Media]
) -> list[Message]:
    rows = conn.execute(
        """
        SELECT Z_PK, ZCHATSESSION, ZSTANZAID, ZISFROMME, ZMESSAGETYPE,
               ZMESSAGEDATE, ZSORT, ZTEXT, ZFROMJID, ZTOJID,
               ZSTARRED, ZMEDIAITEM
        FROM ZWAMESSAGE
        ORDER BY Z_PK
        """
    ).fetchall()
    return [
        Message(
            pk=r[0],
            chat_pk=r[1],
            stanza_id=r[2],
            from_me=bool(r[3]),
            ios_type=r[4] if r[4] is not None else 0,
            ios_timestamp=r[5] if r[5] is not None else 0.0,
            sort=r[6],
            text=r[7],
            from_jid=r[8],
            to_jid=r[9],
            starred=bool(r[10]) if r[10] is not None else False,
            media=media_map.get(r[11]) if r[11] is not None else None,
        )
        for r in rows
    ]


def _fetch_group_members(conn: sqlite3.Connection) -> list[GroupMember]:
    rows = conn.execute(
        """
        SELECT ZCHATSESSION, ZMEMBERJID, ZCONTACTNAME
        FROM ZWAGROUPMEMBER
        ORDER BY Z_PK
        """
    ).fetchall()
    return [
        GroupMember(
            chat_pk=r[0] if r[0] is not None else 0,
            member_jid=r[1] or "",
            display_name=r[2],
        )
        for r in rows
    ]


def _fetch_push_names(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT ZJID, ZPUSHNAME FROM ZWAPROFILEPUSHNAME"
    ).fetchall()
    return {r[0]: r[1] for r in rows if r[0] is not None and r[1] is not None}


def parse_ios_db(path: Path) -> Corpus:
    """Parse an iOS ChatStorage.sqlite file and return a Corpus."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = None  # use tuple rows for speed
    try:
        media_map = _fetch_media(conn)
        return Corpus(
            chats=_fetch_chats(conn),
            messages=_fetch_messages(conn, media_map),
            group_members=_fetch_group_members(conn),
            push_names=_fetch_push_names(conn),
        )
    finally:
        conn.close()
