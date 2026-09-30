"""CLI smoke tests: parse, run against the demo backend, emit JSON."""

from __future__ import annotations

import json
import time

import pytest

from parley.cli import main


@pytest.fixture()
def iso_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("PARLEY_DATA_DIR", str(tmp_path))
    return tmp_path


def test_status_json(capsys, iso_tmp):
    code = main(["--demo", "--json", "status"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["backend"] == "demo"


def test_chats_and_contacts(capsys, iso_tmp):
    main(["--demo", "--json", "chats"])
    chats = json.loads(capsys.readouterr().out)
    assert len(chats) == 4
    main(["--demo", "--json", "contacts"])
    contacts = json.loads(capsys.readouterr().out)
    assert any(c["name"] == "Ava" for c in contacts)


def test_send_by_name(capsys, iso_tmp):
    code = main(
        ["--demo", "--json", "send", "--to", "Weekend Hikers", "--text", "hi",
         "--network", "0", "--typing-per-char", "0.1"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["chat"] == "e9f0a9c8d711b4a2b8002@g.us"


def test_schedule_lifecycle(capsys, iso_tmp):
    code = main(
        ["--demo", "--json", "schedule", "add", "--to", "Ava", "--text", "soc",
         "--at", "2099-01-01T09:00:00"]
    )
    assert code == 0
    added = json.loads(capsys.readouterr().out)
    assert added["status"] == "pending"

    main(["--demo", "--json", "schedule", "list"])
    entries = json.loads(capsys.readouterr().out)
    assert any(e["id"] == added["id"] for e in entries)

    code = main(["--demo", "--json", "schedule", "remove", "--id", added["id"]])
    assert code == 0


def test_schedule_run_fires_due(capsys, iso_tmp):
    past = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 5))
    main(["--demo", "--json", "schedule", "add", "--to", "Ava", "--text", "fireme", "--at", past])
    capsys.readouterr()
    code = main(["--demo", "--json", "schedule", "run", "--once", "--network", "0"])
    assert code == 0
    fired = json.loads(capsys.readouterr().out)
    assert fired["ok"] is True
    assert [e["text"] for e in fired["fired"]] == ["fireme"]


def test_unknown_recipient_fails_cleanly(capsys, iso_tmp):
    code = main(["--demo", "--json", "send", "--to", "nobody-here", "--text", "x"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and "could not resolve" in payload["error"]


def test_missing_text_exits_2(capsys, iso_tmp):
    with pytest.raises(SystemExit) as exc:
        main(["--demo", "--json", "send", "--to", "Ava"])
    assert exc.value.code == 2


def test_setup_dry_run(capsys, iso_tmp):
    code = main(["--json", "setup", "--dry-run"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["dry_run"] is True
