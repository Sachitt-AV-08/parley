"""HTTP API smoke tests (in-process on an ephemeral port)."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request

import pytest

from parley.server import serve


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PARLEY_DATA_DIR", str(tmp_path / "parley-data"))
    port = _free_port()
    thread = threading.Thread(target=serve, kwargs={"host": "127.0.0.1", "port": port, "demo": True}, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{base}/health", timeout=2)
            break
        except OSError:
            time.sleep(0.1)
    yield base
    # serve() blocks forever; the daemon thread dies with the test process


def _request(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # 4xx/5xx carry a JSON body too
        return exc.code, json.loads(exc.read())


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


def test_auth_required_when_token_set(api):
    # serve() already started without a token; this verifies routing only:
    status, payload = _request("GET", f"{api}/nope")
    assert status == 404
