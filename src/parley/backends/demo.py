"""The offline simulator.

Same API, CLI, TUI and HTTP behavior as the real CDP attach — but with zero
WhatsApp involved. This is what makes `parley --demo` instant, keeps CI green,
and lets people prototype bots without touching their account.
"""

from __future__ import annotations

import random
import time
from datetime import datetime

from ..models import Chat, Contact, Message, OutboxMessage


def _now() -> float:
    return time.time()


class DemoBackend:
    """A scripted in-memory host with a believable cast of conversations.

    The dataset is deliberately small and kind: two 1:1 chats (one unread), a
    group with a plan, and a pinned thread. Changing the dataset is a one-line
    edit under :meth:`DemoBackend._seed`.
    """

    def __init__(self, now: float | None = None) -> None:
        self._t0 = now if now is not None else _now()
        self._seed()

    # ------------------------------------------------------------------ seed
    def _seed(self) -> None:
        self.contacts_list: list[Contact] = [
            Contact(id="15551234567@c.us", name="Ava", short="Ava"),
            Contact(id="15559876543@c.us", name="Omar", short="Omar"),
            Contact(id="f4c3b3a1c62a49e2b8001@c.us", name="Design Sync", is_group=True),
            Contact(id="e9f0a9c8d711b4a2b8002@g.us", name="Weekend Hikers", is_group=True),
        ]
        self.chats_list: list[Chat] = []
        self.messages_map: dict[str, list[Message]] = {}
        self._mk_chat(
            "15551234567@c.us",
            "Ava",
            unread=2,
            pinned=True,
            lines=[
                ("Ava", "Did you push the icon tile fix?"),
                (True, "On it — landing in a few"),
                ("Ava", "Ship it, then tell me when dinner"),
            ],
        )
        self._mk_chat(
            "15559876543@c.us",
            "Omar",
            lines=[
                ("Omar", "parley looks wild, does it really not touch a cloud?"),
                (True, "Correct. CDP attach to the installed app only."),
                ("Omar", "ok you have to show me"),
            ],
        )
        self._mk_chat(
            "f4c3b3a1c62a49e2b8001@c.us",
            "Design Sync",
            is_group=True,
            unread=1,
            lines=[
                ("Mina", "v2 mockups are in /design"),
                ("Igor", "the dark palette reads so much better"),
                (True, "Merging the palette into the token set now"),
            ],
        )
        self._mk_chat(
            "e9f0a9c8d711b4a2b8002@g.us",
            "Weekend Hikers",
            is_group=True,
            lines=[
                ("Theo", "trailhead at 7:00 Saturday"),
                (True, "Bringing the good camera"),
            ],
        )

    def _mk_chat(
        self,
        chat_id: str,
        name: str,
        is_group: bool = False,
        unread: int = 0,
        pinned: bool = False,
        lines: list[tuple] | None = None,
    ) -> None:
        messages: list[Message] = []
        for i, line in enumerate(lines or []):
            from_me = bool(line[0])
            author = "Me" if from_me else str(line[0])
            text = str(line[1])
            messages.append(
                Message(
                    id=f"{chat_id}:{i}",
                    chat=chat_id,
                    author=author,
                    text=text,
                    timestamp=self._t0 - (len(lines) - i) * 412,
                    from_me=from_me,
                )
            )
        self.messages_map[chat_id] = messages
        last = messages[-1]
        self.chats_list.append(
            Chat(
                id=chat_id,
                name=name,
                is_group=is_group,
                unread=unread,
                pinned=pinned,
                last_message=last.preview(80),
                last_timestamp=last.timestamp,
            )
        )

    # --------------------------------------------------------------- backend
    def status(self) -> dict:
        return {
            "backend": "demo",
            "brand": "parley simulator (no WhatsApp)",
            "me": "Me",
            "contacts": len(self.contacts_list),
            "chats": len(self.chats_list),
            "since": datetime.fromtimestamp(self._t0).isoformat(timespec="seconds"),
        }

    def contacts(self) -> list[Contact]:
        return list(self.contacts_list)

    def chats(self, limit: int = 50, unread_only: bool = False) -> list[Chat]:
        chats = sorted(self.chats_list, key=lambda c: (c.pinned, c.last_timestamp or 0), reverse=True)
        if unread_only:
            chats = [c for c in chats if c.unread > 0]
        return chats[:limit]

    def messages(self, chat_id: str, limit: int = 50) -> list[Message]:
        return self.messages_map.get(chat_id, [])[-limit:]

    def send(self, outbox: OutboxMessage) -> Message:
        if outbox.chat not in self.messages_map:
            raise ValueError(f"unknown chat {outbox.chat!r}")
        msg = Message(
            id=f"{outbox.chat}:{random.randint(10_000, 99_999)}",
            chat=outbox.chat,
            author="Me",
            text=outbox.text,
            timestamp=_now(),
            from_me=True,
        )
        self.messages_map[outbox.chat].append(msg)
        self._touch_chat(outbox.chat, msg)
        return msg

    def react(self, message_id: str, emoji: str | None) -> Message:
        for chat_id, msgs in self.messages_map.items():
            for m in msgs:
                if m.id == message_id:
                    return Message(
                        id=message_id, chat=chat_id, author="me", text=emoji or "", from_me=True
                    )
        raise ValueError(f"unknown message {message_id!r}")

    def _touch_chat(self, chat_id: str, msg: Message) -> None:
        for c in self.chats_list:
            if c.id == chat_id:
                self.chats_list.remove(c)
                self.chats_list.append(
                    Chat(
                        id=c.id,
                        name=c.name,
                        is_group=c.is_group,
                        unread=c.unread,
                        pinned=c.pinned,
                        last_message=msg.preview(80),
                        last_timestamp=msg.timestamp,
                    )
                )
                return

    def close(self) -> None:
        self.messages_map.clear()
