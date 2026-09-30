"""Model Context Protocol (MCP) server for parley.

Turn your installed WhatsApp into an AI-agent toolchain over the standard
``stdio`` MCP transport: Claude, Cursor, Copilot and any MCP client can list
your chats, read messages, send, reply, react and schedule — through a local
Session, `127.0.0.1` only, with the same pacing and verification as every
other parley path.

The two layers live apart on purpose:

* :mod:`parley.mcp_server` tool functions take a ``Session`` and return plain
  JSON-able dicts — unit-testable against ``DemoBackend`` with no MCP
  dependency at all;
* :func:`build_mcp` only imports the ``mcp`` SDK (optional extra
  ``parley-wa[mcp]``) and binds those functions to ``FastMCP``.

Run it with::

    parley mcp              # live WhatsApp Desktop
    parley mcp --demo       # offline simulator
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import asdict

from .scheduler import Scheduler
from .session import Session, backend_from_env, parley_connect

# ------------------------------------------------------------------ tools ----
# These are thin functions over Session/Scheduler so they are testable without
# the `mcp` dependency. Docstrings become the tool descriptions an agent sees.


def tool_status(session: Session) -> dict:
    """Return attach health and login state."""
    return {"ok": True, **session.status()}


def tool_list_chats(session: Session, limit: int = 50, unread_only: bool = False) -> dict:
    """List recent conversations (id, name, unread, pinned, last message).

    `unread_only=true` filters to chats with unseen messages.
    """
    chats = session.chats(limit=limit, unread_only=unread_only)
    return {"ok": True, "chats": [asdict(c) for c in chats]}


def tool_read_messages(session: Session, chat: str, limit: int = 50) -> dict:
    """Read recent messages from one chat.

    `chat` accepts a chat id, contact name, group subject, or phone number.
    """
    try:
        chat_id, name = session.resolve_recipient(chat)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    msgs = session.messages(chat_id, limit=limit)
    return {"ok": True, "chat": chat_id, "name": name, "messages": [asdict(m) for m in msgs]}


def tool_send_message(session: Session, to: str, text: str) -> dict:
    """Send `text` to a person, group, number, or chat id.

    Recipients are resolved first and the message is confirmed to have landed
    before this returns `ok: true`.
    """
    try:
        sent = session.send(to, text)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "chat": sent.chat, "id": sent.id, "text": sent.text}


def tool_reply_message(session: Session, message_id: str, text: str) -> dict:
    """Reply to a specific message, quoting it if the platform supports it."""
    try:
        sent = session.reply(message_id, text)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "id": sent.id}


def tool_react_message(session: Session, message_id: str, emoji: str) -> dict:
    """React to a message with `emoji` (e.g. '👀'); pass emoji='' to clear."""
    try:
        session.react(message_id, emoji or None)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "message": message_id, "emoji": emoji}


def _scheduler(session: Session) -> Scheduler:
    return Scheduler(session=session)


def tool_schedule_message(scheduler: Scheduler, to: str, text: str, at: str, repeat: str | None = None) -> dict:
    """Queue a message for later.

    `at` is an ISO 8601 local time (e.g. 2026-10-02T09:00:00). `repeat` may be
    'hourly', 'daily' or 'weekly'. Use run_due_schedules() to fire it.
    """
    if repeat not in (None, "hourly", "daily", "weekly"):
        return {"ok": False, "error": f"unsupported repeat {repeat!r}"}
    try:
        entry = scheduler.add(to=to, text=text, at=at, repeat=repeat)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "id": entry.id, "at": entry.at, "repeat": entry.repeat}


def tool_list_schedules(scheduler: Scheduler) -> dict:
    """List queued/recurring messages and their status."""
    return {"ok": True, "schedules": [asdict(e) for e in scheduler.list()]}


def tool_cancel_schedule(scheduler: Scheduler, entry_id: str) -> dict:
    """Remove a queued message by its schedule id."""
    removed = scheduler.remove(entry_id)
    return {"ok": True, "removed": removed, "id": entry_id}


def tool_run_due_schedules(scheduler: Scheduler) -> dict:
    """Fire any schedules that are due right now, through the paced session."""
    fired = scheduler.fire_due()
    return {"ok": True, "fired": [asdict(e) for e in fired]}


# ---------------------------------------------------------------- MCP bind ----
TOOL_FUNCTIONS = (
    tool_status,
    tool_list_chats,
    tool_read_messages,
    tool_send_message,
    tool_reply_message,
    tool_react_message,
    tool_schedule_message,
    tool_list_schedules,
    tool_cancel_schedule,
    tool_run_due_schedules,
)


def _bind(fn, session, scheduler):
    """Build a real named callable for ``fn`` that an MCP client can inspect.

    Keeps the public parameter names and defaults (schema-wise) while hiding
    the injected ``session`` / ``scheduler`` arguments. Works with both the
    ``mcp<2`` FastMCP decorator and the ``mcp>=2`` MCPServer API.
    """
    sig = inspect.signature(fn)
    parts = []
    for p in sig.parameters.values():
        if p.name in ("session", "scheduler"):
            continue
        if p.default is inspect.Parameter.empty:
            parts.append(p.name)
        else:
            parts.append(f"{p.name}={p.default!r}")
    params = ", ".join(parts)
    src = f"def {fn.__name__}({params}):\n    return _ret(_fn, _session, _scheduler, **dict(locals()))"
    ns = {
        "_ret": lambda f, s, sc, **kw: f(s, **kw) if "session" in f.__code__.co_varnames else f(sc, **kw),
        "_fn": fn,
        "_session": session,
        "_scheduler": scheduler,
    }
    exec(src, ns)  # noqa: S102 - trusted, fixed input
    bound = ns[fn.__name__]
    bound.__doc__ = fn.__doc__
    return bound


def _server_class():
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

        return FastMCP, "v1"
    except ImportError:  # pragma: no cover - mcp>=2 renamed fastmcp
        from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

        return MCPServer, "v2"


def build_mcp(session: Session, name: str = "parley") -> object:
    """Bind the tool functions to a fresh MCP server (requires the `mcp` SDK)."""
    try:
        cls, _ = _server_class()
    except ImportError as exc:
        raise ImportError(
            "parley[mcp] is required for the MCP server (pip install 'parley-wa[mcp]')"
        ) from exc

    scheduler = _scheduler(session)
    server = cls(name)
    for fn in TOOL_FUNCTIONS:
        bound = _bind(fn, session, scheduler)
        server.tool(name=fn.__name__[5:] if fn.__name__.startswith("tool_") else fn.__name__,
                    description=(fn.__doc__ or "").strip())(bound)
    return server


def run(demo: bool = False, name: str = "parley", port: int | None = None) -> int:
    """Build a Session + MCP server and serve on stdio. Blocks until stdin closes."""
    from .backends.webview import DEFAULT_PORT

    port = port or DEFAULT_PORT
    if demo:
        session = parley_connect(demo=True)
    else:
        session = Session(backend=backend_from_env(port=port))
    session.status()  # fail fast with a friendly error if the host is unreachable
    server = build_mcp(session, name=name)
    server.run()  # stdio transport
    return 0


if __name__ == "__main__":
    import argparse
    import sys

    from .backends.webview import DEFAULT_PORT

    parser = argparse.ArgumentParser(prog="parley mcp", description=__doc__.split("\n\n")[0])
    parser.add_argument("--demo", action="store_true", help="run against the offline simulator")
    parser.add_argument("--name", default="parley", help="server name shown by clients")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="WhatsApp CDP port to attach to")
    args = parser.parse_args()
    sys.exit(run(demo=args.demo, name=args.name, port=args.port))
