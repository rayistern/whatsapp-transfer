"""Tests for iOS ChatStorage.sqlite parser against real test data."""

from pathlib import Path

import pytest

from wat.extract import parse_ios_db, _parse_jid
from wat.model import Corpus, Chat, Message, Media, GroupMember

DB_PATH = Path(__file__).resolve().parent.parent / "test-data" / "extracted" / "ChatStorage.sqlite"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    """Parse the test database once for all tests."""
    assert DB_PATH.exists(), f"Test database not found at {DB_PATH}"
    return parse_ios_db(DB_PATH)


# ---------------------------------------------------------------------------
# Count tests
# ---------------------------------------------------------------------------

class TestCounts:
    def test_chat_count(self, corpus: Corpus):
        assert len(corpus.chats) == 3

    def test_message_count(self, corpus: Corpus):
        assert len(corpus.messages) == 85

    def test_media_count(self, corpus: Corpus):
        media_messages = [m for m in corpus.messages if m.media is not None]
        assert len(media_messages) == 76

    def test_group_member_count(self, corpus: Corpus):
        assert len(corpus.group_members) == 460

    def test_push_name_count(self, corpus: Corpus):
        assert len(corpus.push_names) == 50


# ---------------------------------------------------------------------------
# Chat tests
# ---------------------------------------------------------------------------

class TestChats:
    def test_chat_pks(self, corpus: Corpus):
        pks = [c.pk for c in corpus.chats]
        assert pks == [1, 2, 3]

    def test_private_chat(self, corpus: Corpus):
        c = corpus.chats[0]
        assert c.pk == 1
        assert c.partner_jid == "16467142629@s.whatsapp.net"
        assert c.is_group is False

    def test_group_chat_2(self, corpus: Corpus):
        c = corpus.chats[1]
        assert c.pk == 2
        assert c.partner_jid == "17189740857-1517518006@g.us"
        assert c.is_group is True

    def test_group_chat_3(self, corpus: Corpus):
        c = corpus.chats[2]
        assert c.pk == 3
        assert "g.us" in c.partner_jid
        assert c.is_group is True

    def test_partner_name_not_none_for_some(self, corpus: Corpus):
        """At least one chat should have a partner name."""
        names = [c.partner_name for c in corpus.chats]
        assert any(n is not None for n in names)


# ---------------------------------------------------------------------------
# Message tests
# ---------------------------------------------------------------------------

class TestMessages:
    def test_message_type_distribution(self, corpus: Corpus):
        from collections import Counter
        type_counts = Counter(m.ios_type for m in corpus.messages)
        assert type_counts[0] == 66
        assert type_counts[1] == 5
        assert type_counts[2] == 2
        assert type_counts[6] == 3
        assert type_counts[7] == 3
        assert type_counts[8] == 1
        assert type_counts[10] == 4
        assert type_counts[14] == 1

    def test_all_messages_have_chat_pk(self, corpus: Corpus):
        chat_pks = {c.pk for c in corpus.chats}
        for m in corpus.messages:
            assert m.chat_pk in chat_pks

    def test_from_me_is_bool(self, corpus: Corpus):
        for m in corpus.messages:
            assert isinstance(m.from_me, bool)

    def test_timestamps_are_core_data_epoch(self, corpus: Corpus):
        """Core Data epoch timestamps should be around 5-8e8 for recent data."""
        for m in corpus.messages:
            assert isinstance(m.ios_timestamp, (int, float))

    def test_some_messages_have_text(self, corpus: Corpus):
        texts = [m.text for m in corpus.messages if m.text is not None]
        assert len(texts) > 0

    def test_starred_is_bool(self, corpus: Corpus):
        for m in corpus.messages:
            assert isinstance(m.starred, bool)


# ---------------------------------------------------------------------------
# Media tests
# ---------------------------------------------------------------------------

class TestMedia:
    def test_media_linked_to_messages(self, corpus: Corpus):
        """Every message with media should have a Media object."""
        media_msgs = [m for m in corpus.messages if m.media is not None]
        assert len(media_msgs) == 76
        for m in media_msgs:
            assert isinstance(m.media, Media)

    def test_media_fields_nullable(self, corpus: Corpus):
        """Media fields can be None; verify no crashes."""
        for m in corpus.messages:
            if m.media:
                # These should be the right types or None
                assert m.media.file_size is None or isinstance(m.media.file_size, int)
                assert m.media.duration is None or isinstance(m.media.duration, int)
                assert m.media.latitude is None or isinstance(m.media.latitude, float)
                assert m.media.longitude is None or isinstance(m.media.longitude, float)


# ---------------------------------------------------------------------------
# Group member tests
# ---------------------------------------------------------------------------

class TestGroupMembers:
    def test_all_members_have_jid(self, corpus: Corpus):
        for gm in corpus.group_members:
            assert isinstance(gm.member_jid, str)

    def test_members_belong_to_group_chats(self, corpus: Corpus):
        group_pks = {c.pk for c in corpus.chats if c.is_group}
        member_chat_pks = {gm.chat_pk for gm in corpus.group_members}
        # All member chat_pks should reference group chats
        assert member_chat_pks.issubset(group_pks)


# ---------------------------------------------------------------------------
# Push names tests
# ---------------------------------------------------------------------------

class TestPushNames:
    def test_push_names_are_strings(self, corpus: Corpus):
        for jid, name in corpus.push_names.items():
            assert isinstance(jid, str)
            assert isinstance(name, str)
            assert "@" in jid  # JIDs should contain @

    def test_push_names_non_empty(self, corpus: Corpus):
        assert len(corpus.push_names) > 0


# ---------------------------------------------------------------------------
# JID parser tests
# ---------------------------------------------------------------------------

class TestJidParser:
    def test_standard_jid(self):
        jid = _parse_jid("14155551234@s.whatsapp.net")
        assert jid.raw == "14155551234@s.whatsapp.net"
        assert jid.user == "14155551234"
        assert jid.server == "s.whatsapp.net"

    def test_group_jid(self):
        jid = _parse_jid("17189740857-1517518006@g.us")
        assert jid.user == "17189740857-1517518006"
        assert jid.server == "g.us"

    def test_no_at_sign(self):
        jid = _parse_jid("something")
        assert jid.user == "something"
        assert jid.server == ""
