"""Shared data shapes for the parley protocol.

Every backend normalises the messy host data (WhatsApp's internal "Store",
WebView2 DOM, or the offline simulator) into these three small types.

Chat ids follow the WhatsApp wire format so they round-trip between every
backend and the CLI/TUI/HTTP layers:

* people:  ``<cc><number>@c.us``  (e.g. ``15551234567@c.us``)
* groups:  ``<hex>@g.us``
* broadcast lists and status get their usual suffixes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Contact:
    """A person or group you can message."""

    id: str
    name: str
    is_group: bool = False
    pushname: str | None = None
    short: str | None = None


@dataclass(frozen=True)
class Chat:
    """A conversation row — enough to render a chat list and open a chat."""

    id: str
    name: str
    is_group: bool = False
    unread: int = 0
    pinned: bool = False
    last_message: str | None = None
    last_timestamp: float | None = None


@dataclass(frozen=True)
class Message:
    """A single message inside a chat."""

    id: str
    chat: str
    author: str = ""
    text: str = ""
    timestamp: float | None = None
    from_me: bool = False
    kind: str = "text"

    def preview(self, length: int = 70) -> str:
        body = self.text.strip().replace("\n", " ")
        return body if len(body) <= length else f"{body[: length - 1]}\u2026"


@dataclass
class OutboxMessage:
    """A message we are about to hand to a human-paced sender."""

    chat: str
    text: str
    quoted_message_id: str | None = None
    name: str | None = None
    extras: dict = field(default_factory=dict)
