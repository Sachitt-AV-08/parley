"""parley command-line interface.

Every command prints JSON when ``--json`` is given so it is pipe-friendly and
agent-friendly. Human output is a small aligned table.

    parley setup            enable the WebView2 debugging port (Windows)
    parley doctor           read-only health report
    parley status           attached? logged in? which account?
    parley chats            recent conversations
    parley chat <id|name>   recent messages in one chat
    parley contacts         addressable people/groups
    parley send --to <id|name> --text <...>
    parley reply --message <id> --text <...>
    parley react --message <id> --emoji <...>
    parley server --port 8300    local HTTP API
    parley tui                  Textual terminal app
    parley demo                 alias: run any command against the simulator

Pass ``--demo`` to any read/write command to run it on the offline simulator
(e.g. ``parley --demo send --to Ava --text hi``).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from . import __version__
from .models import Chat, Contact, Message

WIDTH = shutil.get_terminal_size((100, 24)).columns


def out(obj, as_json: bool, human: list[str] | None = None) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, default=_jsonable))
        return
    if human:
        for line in human:
            print(line)
    else:
        print(obj)


def _jsonable(o):
    if isinstance(o, (Chat, Contact, Message)):
        return o.__dict__ if hasattr(o, "__dict__") else {
            "id": o.id,
            "name": getattr(o, "name", ""),
            "text": getattr(o, "text", ""),
            "chat": getattr(o, "chat", ""),
            "author": getattr(o, "author", ""),
            "timestamp": getattr(o, "timestamp", None),
            "from_me": getattr(o, "from_me", False),
            "kind": getattr(o, "kind", "text"),
        }
    return str(o)


def _open_session(args, *, write: bool) -> None:
    from .session import Session

    pacing = None
    if write:
        from .pacing import HumanPacing

        pacing = HumanPacing(
            typing_per_char=getattr(args, "typing_per_char", None) or 0.09,
            typing_max=getattr(args, "typing_max", None) or 3.5,
            network=getattr(args, "network", None) or 0.6,
            window_seconds=getattr(args, "window_seconds", None) or 60,
            window_budget=getattr(args, "window_budget", None) or 18,
        )
    return Session(demo=args.demo, pacing=pacing)


def _render_chat_table(chats) -> str:
    def line(c: Chat) -> str:
        marker = "\u2022 " if c.unread else "  "
        pin = "pin " if c.pinned else ""
        group = "[group] " if c.is_group else ""
        ts = ""
        if c.last_timestamp:
            import datetime

            ts = datetime.datetime.fromtimestamp(c.last_timestamp).strftime("%H:%M")
        last = (c.last_message or "").replace("\n", " ")
        if len(last) > 44:
            last = last[:43] + "\u2026"
        return f"{marker}{pin}{group}{c.name or c.id:<24} {ts:>6}  {last}"

    header = "\n".join(line(c) for c in chats)
    return header


def _render_message_table(msgs) -> str:
    lines = []
    for m in msgs:
        who = "me" if m.from_me else (m.author or "?")
        stamp = ""
        if m.timestamp:
            import datetime

            stamp = datetime.datetime.fromtimestamp(m.timestamp).strftime("%m-%d %H:%M")
        body = m.preview(120)
        kind = f"<{m.kind}> " if m.kind and m.kind != "text" else ""
        lines.append(f"{stamp:<14} {who:<16} {kind}{body}")
    return "\n".join(lines)


# ------------------------------------------------------------------ commands
def cmd_setup(args) -> int:
    from .doctor import setup, undo_setup

    if args.undo:
        out(undo_setup(), args.json)
        return 0
    result = setup(port=args.port, force=args.force, dry_run=args.dry_run, admin=args.admin)
    out(result, args.json)
    if not args.json:
        method = result.get("method", "")
        print(f"debug flag set via {method} for port {args.port}")
    if result.get("hint"):
        print(result["hint"], file=sys.stderr)
    return 0 if result.get("ok") else 1


def cmd_doctor(args) -> int:
    from .doctor import doctor

    result = doctor(port=args.port)
    out(result, args.json)
    if not args.json:
        print()
        for c in result["checks"]:
            status = "ok" if c["ok"] is True else ("open" if c["ok"] is None else "FAIL")
            print(f"[{status:>4}] {c['name']}: {c['detail']}")
        return 0 if result["ok"] else 1
    return 0


def cmd_status(args) -> int:
    session = _open_session(args, write=False)
    try:
        st = session.status()
        out(st, args.json)
        if not args.json:
            print(f"backend    {st.get('brand')}")
            print(f"logged in  {st.get('loggedIn')}")
            if st.get("me"):
                print(f"me         {st['me']}")
            if st.get("store"):
                print("store      available")
        return 0
    finally:
        session.close()


def cmd_chats(args) -> int:
    session = _open_session(args, write=False)
    try:
        chats = session.chats(limit=args.limit, unread_only=args.unread)
        if args.json:
            out([c.__dict__ if hasattr(c, "__dict__") else c for c in chats], True)
        else:
            print(_render_chat_table(chats))
        return 0
    finally:
        session.close()


def cmd_contacts(args) -> int:
    session = _open_session(args, write=False)
    try:
        contacts = session.contacts()
        if args.json:
            out([c.__dict__ if hasattr(c, "__dict__") else c for c in contacts], True)
        else:
            for c in contacts:
                group = "[group] " if c.is_group else ""
                print(f"{group}{c.id:<40} {c.name}")
        return 0
    finally:
        session.close()


def cmd_chat(args) -> int:
    session = _open_session(args, write=False)
    try:
        chat_id = session._resolve_chat_id(args.chat)
        msgs = session.messages(chat_id, limit=args.limit)
        if args.json:
            out([m.__dict__ if hasattr(m, "__dict__") else _jsonable(m) for m in msgs], True)
        else:
            print(f"# {args.chat}  ({len(msgs)} shown, oldest last)")
            print(_render_message_table(msgs))
        return 0
    finally:
        session.close()


def cmd_send(args) -> int:
    session = _open_session(args, write=True)
    try:
        if not args.text:
            print("--text is required", file=sys.stderr)
            return 2
        msg = session.send(args.to, args.text)
        out({"ok": True, "chat": msg.chat, "text": msg.text, "id": msg.id}, args.json)
        if not args.json:
            print(f"sent to {msg.chat}: {msg.text}")
        return 0
    finally:
        session.close()


def cmd_reply(args) -> int:
    session = _open_session(args, write=True)
    try:
        if not args.text:
            print("--text is required", file=sys.stderr)
            return 2
        msg = session.reply(args.message, args.text)
        out({"ok": True, "in_reply_to": args.message, "chat": msg.chat, "text": msg.text}, args.json)
        if not args.json:
            print(f"replied in {msg.chat}: {msg.text}")
        return 0
    finally:
        session.close()


def cmd_react(args) -> int:
    session = _open_session(args, write=True)
    try:
        session.react(args.message, args.emoji)
        out({"ok": True, "message": args.message, "emoji": args.emoji}, args.json)
        if not args.json:
            print(f"reacted {args.emoji or 'clear'} on {args.message}")
        return 0
    finally:
        session.close()


def cmd_demo(args) -> int:
    print(
        "parley demo: running the offline simulator.\n"
        "try:\n  parley --demo status\n  parley --demo chats\n  parley --demo chat Ava\n"
        "  parley --demo send --to Ava --text 'hi from parley'\n  parley --demo tui"
    )
    return 0


# ---------------------------------------------------------------- schedule
def cmd_schedule(args) -> int:
    from .scheduler import Scheduler

    action = args.schedule_action
    scheduler = Scheduler()

    if action == "add":
        if not args.text:
            print("--text is required", file=sys.stderr)
            return 2
        entry = scheduler.add(to=args.to, text=args.text, at=args.at, repeat=args.repeat)
        out(asdict_entry(entry), args.json)
        if not args.json:
            print(f"scheduled #{entry.id} -> {entry.to} at {entry.at}" + (f" ({entry.repeat})" if entry.repeat else ""))
        return 0

    if action == "list":
        rows = [asdict_entry(e) for e in scheduler.list()]
        out(rows, args.json)
        if not args.json:
            if not rows:
                print("no scheduled messages (add one: `parley schedule add --at ... --to ... --text ...`)")
            for e in rows:
                mark = "next" if e["status"] == "pending" else e["status"]
                print(f"{e['id']:<14} {mark:<7} {e['at']:<20} {e['repeat'] or 'once':<7} -> {e['to']}")
        return 0

    if action == "remove":
        gone = scheduler.remove(args.id)
        out({"ok": gone, "id": args.id}, args.json)
        return 0 if gone else 1

    if action == "run":
        session = _open_session(args, write=True)
        scheduler.session = session
        try:
            from .scheduler import run_loop

            if args.once:
                fired = scheduler.fire_due()
                out({"ok": True, "fired": [asdict_entry(e) for e in fired]}, args.json)
                if not args.json:
                    print(f"checked the queue: {len(fired)} due message(s) fired")
                return 0
            print(f"watching ~{scheduler.path} every {args.interval}s (Ctrl-C to stop)")
            run_loop(scheduler, interval=args.interval)
            return 0
        finally:
            session.close()

    print("usage: parley schedule {add|list|remove|run} [options]", file=sys.stderr)
    return 2


def asdict_entry(e) -> dict:
    from dataclasses import asdict

    return asdict(e)


# ------------------------------------------------------------------- server
def cmd_server(args) -> int:
    from .server import serve

    serve(host=args.host, port=args.port, demo=args.demo, token=args.token)
    return 0


# ---------------------------------------------------------------------- tui
def cmd_tui(args) -> int:
    try:
        from .tui import run as run_tui
    except ImportError:  # pragma: no cover
        print("the TUI needs `textual`:  pip install 'parley[tui]'", file=sys.stderr)
        return 2
    run_tui(demo=args.demo)
    return 0


# ------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parley",
        description="Drive your installed WhatsApp Desktop locally — no cloud, no QR, no Composio.",
    )
    parser.add_argument("--version", action="version", version=f"parley {__version__}")
    parser.add_argument("--demo", action="store_true", help="use the offline simulator instead of the real app")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    parser.add_argument("--port", type=int, default=None, help="CDP port to attach/monitor (default 9334)")

    sub = parser.add_subparsers(dest="command", metavar="command")

    p_setup = sub.add_parser("setup", help="enable the WebView2 debugging port (Windows)")
    p_setup.add_argument("--force", action="store_true")
    p_setup.add_argument("--dry-run", action="store_true")
    p_setup.add_argument("--admin", action="store_true", help="write the machine-wide HKLM registry policy instead")
    p_setup.add_argument("--undo", action="store_true", help="remove whatever setup wrote (env var + registry)")

    sub.add_parser("doctor", help="read-only health report for attaching to the real app")

    sub.add_parser("status", help="attached? logged in? which account?")

    sub.add_parser("contacts", help="list addressable people and groups")

    p_chats = sub.add_parser("chats", help="recent conversations")
    p_chats.add_argument("--limit", type=int, default=25)
    p_chats.add_argument("--unread", action="store_true", help="only chats with unread messages")

    p_chat = sub.add_parser("chat", help="recent messages in one chat")
    p_chat.add_argument("chat")
    p_chat.add_argument("--limit", type=int, default=30)

    p_send = sub.add_parser("send", help="send a message")
    p_send.add_argument("--to", required=True, help="chat id, name, or phone number")
    p_send.add_argument("--text", required=True)
    _pacing_args(p_send)

    p_reply = sub.add_parser("reply", help="reply to a message")
    p_reply.add_argument("--message", required=True, help="message id")
    p_reply.add_argument("--text", required=True)
    _pacing_args(p_reply)

    p_react = sub.add_parser("react", help="react to a message")
    p_react.add_argument("--message", required=True)
    p_react.add_argument("--emoji", default=None, help="emoji to react with (omit or --emoji '' to clear)")

    sub.add_parser("demo", help="pointers for the offline simulator")

    p_schedule = sub.add_parser("schedule", help="queued / recurring messages")
    p_schedule.add_argument("schedule_action", choices=["add", "list", "remove", "run"], help=argparse.SUPPRESS)
    p_schedule.add_argument("--to", default=None, help="chat id, name, group, or number (add)")
    p_schedule.add_argument("--text", default=None, help="message body (add)")
    p_schedule.add_argument("--at", default=None, help="fire time, ISO 'YYYY-MM-DDTHH:MM:SS' (add)")
    p_schedule.add_argument("--repeat", default=None, choices=["hourly", "daily", "weekly"], help="recurrence (add)")
    p_schedule.add_argument("--id", default=None, help="entry id (remove)")
    p_schedule.add_argument("--once", action="store_true", help="fire all due messages and exit (run)")
    p_schedule.add_argument("--interval", type=float, default=1.0, help="seconds between checks (run)")
    _pacing_args(p_schedule)

    p_server = sub.add_parser("server", help="run the local HTTP API")
    p_server.add_argument("--host", default="127.0.0.1")
    p_server.add_argument("--port", type=int, default=8300, dest="http_port")
    p_server.add_argument("--token", default=None, help="optional Bearer token for the local API")

    sub.add_parser("tui", help="terminal UI (needs `parley[tui]`)")

    return parser


def _pacing_args(p) -> None:
    p.add_argument("--typing-per-char", type=float, default=None, help="seconds per typed char (human look)")
    p.add_argument("--typing-max", type=float, default=None)
    p.add_argument("--network", type=float, default=None, help="base network delay (s)")
    p.add_argument("--window-seconds", type=int, default=None)
    p.add_argument("--window-budget", type=int, default=None, help="max sends per window")


# ------------------------------------------------------------------- entry
def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy codepage; normalize so ✓–emoji in
    # message bodies never crash a pipe/repl.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.port is None:
        from .backends.webview import DEFAULT_PORT

        args.port = DEFAULT_PORT

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "setup": cmd_setup,
        "doctor": cmd_doctor,
        "status": cmd_status,
        "contacts": cmd_contacts,
        "chats": cmd_chats,
        "chat": cmd_chat,
        "send": cmd_send,
        "reply": cmd_reply,
        "react": cmd_react,
        "demo": cmd_demo,
        "schedule": cmd_schedule,
        "server": cmd_server,
        "tui": cmd_tui,
    }
    try:
        code = handlers[args.command](args)
        return int(code or 0)
    except Exception as exc:  # noqa: BLE001 - CLI prints friendly errors
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"parley: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
