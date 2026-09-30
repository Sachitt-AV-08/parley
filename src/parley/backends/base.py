"""Backend protocol — the one thing every host implements.

A backend adapts a specific way of reaching WhatsApp ("the host") to parley's
normalized read/send surface. Implementations today:

* :class:`parley.backends.webview.WebViewBackend` — attach over CDP to the
  installed (Windows) WhatsApp Desktop app via its internal ``window.Store``,
  with a DOM fallback.
* :class:`parley.backends.demo.DemoBackend` — a fully scripted offline
  simulator used by ``parley --demo``, the TUI, tests and CI.

Low-level and honest: backends do *not* pace or retry. :class:`Session`
wraps them with human pacing and retries, so behavior is identical no matter
which backend is selected.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import Chat, Contact, Message, OutboxMessage


@runtime_checkable
class Backend(Protocol):
    """The normalized host interface."""

    def status(self) -> dict:
        """Return a JSON-serializable description of the host connection."""
        ...

    def contacts(self) -> list[Contact]:
        """Every known person/group that is addressable."""
        ...

    def chats(self, limit: int = 50, unread_only: bool = False) -> list[Chat]:
        """Recent conversation rows."""
        ...

    def messages(self, chat_id: str, limit: int = 50) -> list[Message]:
        """Recent messages inside a chat, oldest-last."""
        ...

    def send(self, outbox: OutboxMessage) -> Message:
        """Send (or reply to) one normalized message. Returns it as sent."""
        ...

    def react(self, message_id: str, emoji: str | None) -> Message:
        """Add (or clear, with ``emoji=None``) a reaction on a message."""
        ...

    def close(self) -> None:
        """Release the host (detach / close the CDP connection)."""
        ...
