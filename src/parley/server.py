"""Local HTTP API — so any agent, webhook or script can drive WhatsApp.

Deliberately boring: stdlib only, JSON in/out, permissive loopback CORS, an
optional bearer token. Run with ``parley server --port 8300``.

Endpoints (all JSON):

* ``GET  /health``        — server + session state
* ``GET  /status``        — attached host, login, account
* ``GET  /chats``         — ``?limit=`` ``?unread=1``
* ``GET  /chats/<chat>``  — messages, ``?limit=``
* ``GET  /contacts``
* ``POST /send``          — ``{"to": "...", "text": "..."}``
* ``POST /reply``         — ``{"message": "<id>", "text": "..."}``
* ``POST /react``         — ``{"message": "<id>", "emoji": "..."}``
* ``GET  /schedule``      — pending + fired entries
* ``POST /schedule``      — ``{"to": "...", "text": "...", "at": "2026-10-01T09:00:00", "repeat": "daily"}``
* ``DELETE /schedule/<id>`` — drop an entry
* ``POST /schedule/run``  — fire every due entry right now
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .session import Session


class ParleyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


def _jsonable(o):
    return o.__dict__ if hasattr(o, "__dict__") else str(o)


class Handler(BaseHTTPRequestHandler):
    server_version = "parley/0.1"
    session: Session
    scheduler: object
    token: str | None

    # ------------------------------------------------------------- helpers
    def _send(self, code: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_jsonable).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")  # loopback-friendly, see docs
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _authed(self) -> bool:
        if not self.token:
            return True
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {self.token}"

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _query(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    # ------------------------------------------------------------- routing
    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {})

    def do_GET(self) -> None:  # noqa: N802
        if not self._authed():
            return self._send(401, {"ok": False, "error": "invalid bearer token"})
        path = urlparse(self.path).path
        q = self._query()
        try:
            if path in ("/", "/health"):
                demo = self.session.backend.status().get("backend") == "demo"
                return self._send(200, {"ok": True, "service": "parley", "demo": demo})
            if path == "/status":
                return self._send(200, self.session.status())
            if path == "/chats":
                chats = self.session.chats(limit=int(q.get("limit", 25)), unread_only=q.get("unread") == "1")
                return self._send(200, {"ok": True, "chats": chats})
            if path == "/contacts":
                return self._send(200, {"ok": True, "contacts": self.session.contacts()})
            if path.startswith("/chats/"):
                chat_id = path[len("/chats/"):]
                msgs = self.session.messages(chat_id, limit=int(q.get("limit", 30)))
                return self._send(200, {"ok": True, "chat": chat_id, "messages": msgs})
            if path == "/schedule":
                entries = getattr(self.scheduler, "list", lambda: [])()
                return self._send(200, {"ok": True, "entries": [e.__dict__ for e in entries]})
            if path.startswith("/schedule/"):
                entry_id = path[len("/schedule/"):]
                return self._send(200, {"ok": True, "entry": self._entry(entry_id)})
            return self._send(404, {"ok": False, "error": "not found"})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"ok": False, "error": str(exc)})

    def _entry(self, entry_id: str):
        entry = getattr(self.scheduler, "get", lambda _id: None)(entry_id)
        if entry is None:
            raise KeyError(entry_id)
        return entry.__dict__

    def do_POST(self) -> None:  # noqa: N802
        if not self._authed():
            return self._send(401, {"ok": False, "error": "invalid bearer token"})
        path = urlparse(self.path).path
        body = self._body()
        try:
            if path == "/send":
                to, text = body.get("to"), body.get("text")
                if not to or not text:
                    return self._send(400, {"ok": False, "error": "need 'to' and 'text'"})
                msg = self.session.send(str(to), str(text))
                return self._send(200, {"ok": True, "id": msg.id, "chat": msg.chat, "text": msg.text})
            if path == "/reply":
                mid, text = body.get("message"), body.get("text")
                if not mid or not text:
                    return self._send(400, {"ok": False, "error": "need 'message' and 'text'"})
                msg = self.session.reply(str(mid), str(text))
                return self._send(200, {"ok": True, "chat": msg.chat, "text": msg.text})
            if path == "/react":
                mid = body.get("message")
                if not mid:
                    return self._send(400, {"ok": False, "error": "need 'message'"})
                msg = self.session.react(str(mid), str(body.get("emoji") or None))
                return self._send(200, {"ok": True, "message": mid, "emoji": msg.text or None})
            if path == "/schedule":
                to, text, at = body.get("to"), body.get("text", ""), body.get("at")
                if not to or not at:
                    return self._send(400, {"ok": False, "error": "need 'to' and 'at'"})
                entry = self.scheduler.add(to=str(to), text=str(text), at=str(at), repeat=body.get("repeat"))
                return self._send(200, {"ok": True, "id": entry.id, "at": entry.at})
            if path == "/schedule/run":
                fired = self.scheduler.fire_due()
                return self._send(200, {"ok": True, "fired": [e.__dict__ for e in fired]})
            if path.startswith("/schedule/"):
                entry_id = path[len("/schedule/"):]
                gone = self.scheduler.remove(entry_id)
                if not gone:
                    raise KeyError(entry_id)
                return self._send(200, {"ok": True, "removed": entry_id})
            return self._send(404, {"ok": False, "error": "not found"})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"ok": False, "error": str(exc)})

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._authed():
            return self._send(401, {"ok": False, "error": "invalid bearer token"})
        path = urlparse(self.path).path
        try:
            if path.startswith("/schedule/"):
                entry_id = path[len("/schedule/"):]
                gone = self.scheduler.remove(entry_id)
                if not gone:
                    raise KeyError(entry_id)
                return self._send(200, {"ok": True, "removed": entry_id})
            return self._send(404, {"ok": False, "error": "not found"})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[parley-server] {self.address_string()} {fmt % args}")


def serve(
    host: str = "127.0.0.1",
    port: int = 8300,
    demo: bool | None = None,
    token: str | None = None,
    poll: float = 1.0,
) -> None:
    from .scheduler import Scheduler, SchedulerThread

    session = Session(demo=demo)
    scheduler = Scheduler(session=session)
    thread = SchedulerThread(scheduler, interval=poll)
    thread.start()
    Handler.session = session
    Handler.scheduler = scheduler
    Handler.token = token
    httpd = ParleyHTTPServer((host, port), Handler)
    print(f"parley HTTP API listening on http://{host}:{port}" + (" (bearer token required)" if token else ""))
    print(f"parley scheduler watching {scheduler.path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        thread.stop()
        session.close()
        httpd.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8300)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    serve(host=args.host, port=args.port, demo=args.demo, token=args.token)
