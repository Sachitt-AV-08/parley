"""The user-facing session.

:class:`Session` wraps a :class:`Backend` with human pacing and light retries,
so the CLI, HTTP server and TUI all behave identically on the live CDP host or
the offline simulator.

Backend selection precedence:

1. ``SESSION`` explicitly passed,
2. ``PARLEY_DEMO=1`` / ``--demo``  → simulator,
3. otherwise the live WebView2 CDP attach.
"""

from __future__ import annotations

import os
import time

from .backends.base import Backend
from .backends.webview import DEFAULT_PORT, WebViewBackend
from .errors import ProtocolError
from .models import Chat, Contact, Message, OutboxMessage
from .pacing import HumanPacing
from .scheduler import audit_send

DEFAULT_RETRIES = 2
DEFAULT_RETRY_BACKOFF = 2.0


def backend_from_env(port: int = DEFAULT_PORT, demo: bool | None = None, timeout_s: float = 120) -> Backend:
    """Build the right backend for this machine/environment.

    ``PARLEY_CDP_HOST`` / ``PARLEY_CDP_PORT`` override where to look for the
    debugging endpoint, so the same CLI works against WhatsApp Desktop on
    Windows or any Chromium browser pointed at web.whatsapp.com (macOS/Linux,
    containers, remote boxes).
    """
    if demo is None:
        demo = os.environ.get("PARLEY_DEMO") in {"1", "true", "yes", "demo"}
    if demo:
        from .backends.demo import DemoBackend

        return DemoBackend()
    host = os.environ.get("PARLEY_CDP_HOST", "127.0.0.1")
    port = int(os.environ.get("PARLEY_CDP_PORT", port))
    return WebViewBackend(port=port, host=host, timeout_s=timeout_s)


class Session:
    """A paced, retried, normalized doorway to WhatsApp via a backend."""

    def __init__(
        self,
        backend: Backend | None = None,
        pacing: HumanPacing | None = None,
        retries: int = DEFAULT_RETRIES,
        demo: bool | None = None,
        port: int = DEFAULT_PORT,
        timeout_s: float = 120,
    ) -> None:
        self.pacing = pacing or HumanPacing()
        self.retries = retries
        self.backend = backend or backend_from_env(port=port, demo=demo, timeout_s=timeout_s)

    # -------------------------------------------------------------- reads
    def status(self) -> dict:
        st = self.backend.status()
        st["pacing"] = {
            "window_seconds": self.pacing.window_seconds,
            "window_budget": self.pacing.window_budget,
            "budget_used": self.pacing.window_budget - self.pacing.budget_remaining(),
            "budget_remaining": self.pacing.budget_remaining(),
        }
        return st

    def contacts(self) -> list[Contact]:
        return self.backend.contacts()

    def chats(self, limit: int = 50, unread_only: bool = False) -> list[Chat]:
        return self.backend.chats(limit=limit, unread_only=unread_only)

    def messages(self, chat_id: str, limit: int = 50) -> list[Message]:
        return self.backend.messages(chat_id, limit=limit)

    def find_chat(self, needle: str) -> Chat | None:
        """Resolve a person or group by id, exact name, or phone digits.

        Accepts ``15551234567@c.us``, ``+1 555 123 4567``, ``7384273605``, a
        contact pushname ("Ava"), or a group subject ("Weekend Hikers"). A known
        contact with no chat row yet still resolves (parley will open the chat
        on send). Best match wins; ties go to exact matches.
        """
        needle = needle.strip().lower()
        chats = self.chats(limit=400)
        by_id = {c.id.lower(): c for c in chats}
        contacts = self.contacts()
        contact_by_id = {c.id.lower(): c for c in contacts}

        def as_chat(source) -> Chat | None:
            cid = source.id.lower()
            return by_id.get(cid) or Chat(id=source.id, name=source.name or source.id, is_group=source.is_group)

        if "@" in needle:
            if needle in by_id:
                return by_id[needle]
            if needle in contact_by_id:
                return as_chat(contact_by_id[needle])
        for c in chats:
            if c.name and c.name.lower() == needle:
                return c
        for c in contacts:
            name = (c.name or "").lower()
            push = (c.pushname or "").lower()
            short = (c.short or "").lower()
            if needle in (name, push, short) and needle:
                return as_chat(c)
        digits = "".join(ch for ch in needle if ch.isdigit())
        if digits:
            for c in contacts:
                cid = "".join(ch for ch in c.id.split("@")[0] if ch.isdigit())
                if cid and (digits == cid or digits in cid or cid.endswith(digits[-10:])):
                    return as_chat(c)

        def rank(c: Chat) -> tuple:
            name = c.name.lower()
            if needle in name:
                return (0, name.index(needle))
            return (9, 9**9)

        matches = sorted((c for c in chats if needle in (c.name or "").lower()), key=rank)
        return matches[0] if matches else None

    def resolve_recipient(self, needle: str) -> tuple[str, str]:
        """Return ``(chat_id, display_name)`` for a chat id or searchable handle.

        ``display_name`` is the exact name to hunt for in the UI (group subject
        or pushname), which makes name-based searching precise.
        """
        needle = needle.strip()
        if "@" in needle:
            found = self.find_chat(needle)
            return needle, (found.name if found else "")
        found = self.find_chat(needle)
        if found is None:
            raise ValueError(
                f"could not resolve {needle!r}: not a chat id, and no contact or "
                "group name matched. Try `parley contacts`."
            )
        return found.id, found.name

    def find_message(self, message_id: str, chat_limit: int = 200) -> Message | None:
        """Locate a message by id — exact, or by id / chat/seq prefix.

        Walks the most recent chats (newest first) and reads a deep window of
        each so `reply` and `react` work on older messages too, not just the
        last screenful.
        """
        mid = message_id.strip()
        prefix = mid.split(":")[0]
        for chat in self.chats(limit=chat_limit):
            for m in self.messages(chat.id, limit=300):
                if m.id in (mid, prefix) or m.id.startswith(f"{prefix}:") or mid.startswith(m.id.split(":")[0]):
                    return m
        return None

    # ------------------------------------------------------------- writes
    def send(self, chat: str, text: str) -> Message:
        """Send `text` to a chat id, contact name, group subject, or number."""
        chat_id, name = self.resolve_recipient(chat)
        msg = self._guarded(
            lambda: self.backend.send(OutboxMessage(chat=chat_id, text=str(text), name=name))
        )
        audit_send(chat_id, name or chat, text, source="send")
        return msg

    def reply(self, message_id: str, text: str) -> Message:
        """Reply to a message by id (quote it when the host supports it)."""
        target = self.find_message(message_id)
        if target is None:
            raise ValueError(f"could not locate message {message_id!r}")
        msg = self._guarded(
            lambda: self.backend.send(OutboxMessage(chat=target.chat, text=str(text), quoted_message_id=message_id))
        )
        audit_send(target.chat, target.chat, text, source="reply")
        return msg

    def react(self, message_id: str, emoji: str | None) -> Message:
        """React (or clear a reaction with ``emoji=None``) on a message by id."""
        if not self.find_message(message_id):
            raise ValueError(f"could not locate message {message_id!r}")
        msg = self._guarded(lambda: self.backend.react(message_id, emoji))
        audit_send(message_id, message_id, emoji or "clear", source="react")
        return msg

    # ------------------------------------------------------------- helpers
    def _resolve_chat_id(self, chat: str) -> str:
        return self.resolve_recipient(chat)[0]

    def _guarded(self, op):
        last_error: BaseException | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(DEFAULT_RETRY_BACKOFF * attempt)
            try:
                self.pacing.before_send("")
                return op()
            except (ProtocolError, ConnectionError, OSError) as exc:
                last_error = exc
        raise last_error  # type: ignore[misc]

    def close(self) -> None:
        self.backend.close()


def parley_connect(*, demo: bool | None = None, port: int = DEFAULT_PORT, timeout_s: float = 120) -> Session:
    """Convenience factory: ``with parley_connect() as s: s.send(...)``."""
    return Session(demo=demo, port=port, timeout_s=timeout_s)
