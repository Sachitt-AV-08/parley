"""Session behavior tests against the offline simulator.

The demo backend gives the exact Session surface the live CDP attach does, so
resolution, pacing and payloads are tested without WhatsApp.
"""

from __future__ import annotations

import pytest

from parley import Session
from parley.pacing import BudgetExceeded


@pytest.fixture()
def session():
    s = Session(demo=True)
    yield s
    s.close()


def test_status_reports_demo(session):
    st = session.status()
    assert st["backend"] == "demo"
    assert "contacts" in st and "chats" in st


def test_contacts_and_chats_shape(session):
    contacts = session.contacts()
    assert any(c.name == "Ava" for c in contacts)
    chats = session.chats()
    assert {c.name for c in chats} == {"Ava", "Omar", "Design Sync", "Weekend Hikers"}
    group = next(c for c in chats if c.name == "Weekend Hikers")
    assert group.is_group


def test_unread_only(session):
    chats = session.chats(unread_only=True)
    names = {c.name for c in chats}
    assert "Ava" in names and "Design Sync" in names
    assert "Omar" not in names


def test_messages_are_oldest_last(session):
    msgs = session.messages("15551234567@c.us")
    times = [m.timestamp for m in msgs]
    assert times == sorted(times)
    assert msgs[-1].text == "Ship it, then tell me when dinner"


class TestResolution:
    @pytest.mark.parametrize(
        "needle, expected_id",
        [
            ("15551234567@c.us", "15551234567@c.us"),
            ("Ava", "15551234567@c.us"),
            ("ava", "15551234567@c.us"),
            ("15551234567", "15551234567@c.us"),
            ("1555", "15551234567@c.us"),
            ("Weekend Hikers", "e9f0a9c8d711b4a2b8002@g.us"),
            ("hikers", "e9f0a9c8d711b4a2b8002@g.us"),
            ("design sync", "f4c3b3a1c62a49e2b8001@c.us"),
        ],
    )
    def test_resolves_to_right_chat(self, session, needle, expected_id):
        chat_id, name = session.resolve_recipient(needle)
        assert chat_id == expected_id
        assert name  # display name is always non-empty for known recipients

    def test_unknown_recipient_raises(self, session):
        with pytest.raises(ValueError):
            session.resolve_recipient("nobody-by-this-name")

    def test_id_not_in_chat_collection_still_resolves_via_contacts(self, session):
        """A contact with no chat row yet (LID-style on live builds) resolves."""
        found = session.find_chat("15559876543@c.us")
        assert found is not None and found.name == "Omar"


class TestWrites:
    def test_send_by_name(self, session):
        msg = session.send("Ava", "hello there")
        assert msg.chat == "15551234567@c.us"
        assert msg.from_me
        msgs = session.messages("15551234567@c.us")
        assert msgs[-1].text == "hello there"

    def test_send_to_group_by_partial_name(self, session):
        msg = session.send("hikers", "packing the rain jackets")
        assert msg.chat == "e9f0a9c8d711b4a2b8002@g.us"

    def test_reply_and_react(self, session):
        target = session.messages("15551234567@c.us")[0]
        replied = session.reply(target.id, "replying")
        assert replied.chat == target.chat
        reacted = session.react(target.id, "👍")
        assert reacted.text == "👍"
        cleared = session.react(target.id, None)
        assert cleared.text in ("", None)

    def test_find_message_matches_exact_and_prefix(self, session):
        target = session.messages("15551234567@c.us")[-1]
        assert session.find_message(target.id) is not None
        assert session.find_message(target.id.split(":")[0]) is not None
        assert session.find_message("no-such-message-id") is None

    def test_find_message_scan_past_first_50_chats(self, session, monkeypatch):
        """Reply/react must reach messages that live in chats beyond the first
        screenful — the old 50-chat scan missed them."""
        from parley.models import Message

        burried = Message(
            id="deadbeef09",
            chat="99999999999@c.us",
            author="Omar",
            text="buried but findable",
            timestamp=1,
        )
        fake_chats = [type("C", (), {"id": f"chat-{i}@c.us", "name": f"Chat {i}"})() for i in range(60)]
        fake_chats.append(type("C", (), {"id": "99999999999@c.us", "name": "Omar"})())
        monkeypatch.setattr(session, "chats", lambda limit=50, unread_only=False: fake_chats)
        monkeypatch.setattr(
            session, "messages",
            lambda chat_id, limit=50: [burried] if chat_id == "99999999999@c.us" else [],
        )
        found = session.find_message(burried.id)
        assert found is not None and found.text == burried.text


def test_pacing_budget_enforced():
    from parley.session import HumanPacing

    pacing = HumanPacing(window_seconds=600, window_budget=3, typing_per_char=0.0, network=0.0)
    for _ in range(3):
        pacing._reserve()
    with pytest.raises(BudgetExceeded):
        pacing._reserve()
