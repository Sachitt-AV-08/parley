"""HTTP API smoke tests (in-process on an ephemeral port)."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from parley.server import load_or_create_token, serve, token_path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ready(port: int, token: str | None = None) -> None:
    """Wait until the server answers (401 is "up", just not authed)."""
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(0.1)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PARLEY_DATA_DIR", str(tmp_path / "parley-data"))
    port = _free_port()
    thread = threading.Thread(
        target=serve,
        kwargs={"host": "127.0.0.1", "port": port, "demo": True, "no_token": True},
        daemon=True,
    )
    thread.start()
    _ready(port)
    yield f"http://127.0.0.1:{port}"
    # serve() blocks forever; the daemon thread dies with the test process


@pytest.fixture()
def secured(tmp_path, monkeypatch):
    monkeypatch.setenv("PARLEY_DATA_DIR", str(tmp_path / "secured-data"))
    port = _free_port()
    thread = threading.Thread(
        target=serve,
        kwargs={"host": "127.0.0.1", "port": port, "demo": True, "token": "sekret"},
        daemon=True,
    )
    thread.start()
    _ready(port)
    yield port


def _request(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # 4xx/5xx carry a JSON body too
        return exc.code, json.loads(exc.read())


def _raw(port: int, method: str, path: str, host: str, **headers) -> tuple[int, dict]:
    """Send an exact HTTP request; lets tests fabricate Host/Origin headers."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        req = f"{method} {path} HTTP/1.1\r\nHost: {host}\r\n"
        for k, v in headers.items():
            req += f"{k}: {v}\r\n"
        req += "\r\n"
        sock.sendall(req.encode())
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        status = int(head.split(b" ", 2)[1])
        length = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1].strip())
        while len(body) < length:
            chunk = sock.recv(4096)
            if not chunk:
                break
            body += chunk
        try:
            return status, json.loads(body or b"{}")
        except ValueError:
            return status, {}


def test_health_and_status(api):
    status, payload = _request("GET", f"{api}/health")
    assert status == 200 and payload["demo"] is True
    status, payload = _request("GET", f"{api}/status")
    assert payload["backend"] == "demo"
    assert payload["me"] == "Me"


def test_contacts_and_chats(api):
    status, payload = _request("GET", f"{api}/contacts")
    assert status == 200 and len(payload["contacts"]) == 4
    status, payload = _request("GET", f"{api}/chats")
    assert status == 200 and len(payload["chats"]) == 4


def test_send_round_trip(api):
    status, payload = _request("POST", f"{api}/send", {"to": "Ava", "text": "over http"})
    assert status == 200 and payload["ok"] is True
    assert payload["chat"] == "15551234567@c.us"
    status, payload = _request("GET", f"{api}/chats/15551234567@c.us")
    assert any(m["text"] == "over http" for m in payload["messages"])


def test_schedule_lifecycle(api):
    status, payload = _request(
        "POST", f"{api}/schedule", {"to": "Ava", "text": "later", "at": "2099-01-01T09:00:00", "repeat": "daily"}
    )
    assert status == 200 and payload["ok"] is True
    entry_id = payload["id"]

    status, payload = _request("GET", f"{api}/schedule")
    assert status == 200 and any(e["id"] == entry_id for e in payload["entries"])

    status, payload = _request("DELETE", f"{api}/schedule/{entry_id}")
    assert status == 200 and payload["removed"] == entry_id

    status, payload = _request("GET", f"{api}/schedule")
    assert all(e["id"] != entry_id for e in payload["entries"])


def test_schedule_run_fires_due(api):
    past = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 5))
    status, payload = _request("POST", f"{api}/schedule", {"to": "Ava", "text": "imminent", "at": past})
    assert status == 200
    status, payload = _request("POST", f"{api}/schedule/run", {})
    assert status == 200
    assert len(payload["fired"]) == 1
    assert payload["fired"][0]["text"] == "imminent"


def test_send_requires_to_and_text(api):
    status, payload = _request("POST", f"{api}/send", {"to": "Ava"})
    assert status == 400


def test_auth_required_when_token_set(secured):
    port = secured
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)
    status, payload = _request("GET", f"http://127.0.0.1:{port}/health", headers={"Authorization": "Bearer sekret"})
    assert status == 200 and payload["demo"] is True


def test_bad_token_rejected(secured):
    status, payload = _request(
        "GET", f"http://127.0.0.1:{secured}/health", headers={"Authorization": "Bearer wrong"}
    )
    assert status == 401 and payload["ok"] is False


def test_evil_host_header_rejected(secured):
    status, _ = _raw(secured, "GET", "/health", host="evil.example.com")
    assert status == 403


def test_foreign_origin_rejected(secured):
    status, _ = _raw(secured, "GET", "/health", host="127.0.0.1", Origin="http://evil.example")
    assert status == 403


def test_same_origin_allowed(secured):
    port = secured
    status, payload = _raw(
        port,
        "GET",
        "/health",
        host="127.0.0.1",
        Origin=f"http://127.0.0.1:{port}",
        Authorization="Bearer sekret",
    )
    assert status == 200 and payload["ok"] is True


def test_form_post_rejected(secured):
    port = secured
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/send",
        data=b"to=Ava&text=hi",
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Bearer sekret",
        },
    )
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=5)
    assert err.value.code == 400


def test_new_origin_vs_old_routing(api):
    # no-auth server (fixture): verify routing still works end to end
    status, payload = _request("GET", f"{api}/nope")
    assert status == 404


def test_token_persisted_and_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("PARLEY_DATA_DIR", str(tmp_path / "td"))
    t1 = load_or_create_token()
    t2 = load_or_create_token()
    assert t1 == t2 and len(t1) >= 32
    assert open(token_path(), encoding="utf-8").read().strip() == t1
    if os.name != "nt":
        assert os.stat(token_path()).st_mode & 0o777 == 0o600
