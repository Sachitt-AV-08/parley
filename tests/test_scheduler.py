"""Scheduler: the JSON-persisted queue, due-time firing and repeat roll-forward."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from parley.scheduler import Scheduler
from parley.session import Session


@pytest.fixture()
def scheduler(tmp_path):
    s = Session(demo=True)
    sch = Scheduler(path=tmp_path / "schedules.json", session=s)
    yield sch
    s.close()


def test_add_list_remove(scheduler, tmp_path):
    e = scheduler.add(to="Ava", text="hi", at="2099-01-01T09:00:00")
    assert e.status == "pending"
    assert [x.id for x in scheduler.list()] == [e.id]

    again = Scheduler(path=tmp_path / "schedules.json", session=scheduler.session)
    assert [x.id for x in again.list()] == [e.id], "store must survive reload"

    assert scheduler.remove(e.id) is True
    assert scheduler.list() == []


def test_repeat_must_start_in_future(scheduler):
    past = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    with pytest.raises(ValueError):
        scheduler.add(to="Ava", text="x", at=past, repeat="daily")


def test_once_in_the_past_fires(scheduler):
    past = (datetime.now() - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%S")
    e = scheduler.add(to="Ava", text="catch-up", at=past)
    fired = scheduler.fire_due()
    assert [f.id for f in fired] == [e.id]
    assert e.status == "sent"
    session_msgs = scheduler.session.messages("15551234567@c.us")
    assert session_msgs[-1].text == "catch-up"


def test_not_due_yet_does_nothing(scheduler, tmp_path):
    scheduler.add(to="Ava", text="future", at="2099-01-01T09:00:00")
    assert scheduler.fire_due() == []


def test_daily_repeat_rolls_forward(scheduler):
    e = scheduler.add(to="Omar", text="daily ping", at="2099-01-01T09:00:00", repeat="daily")
    e.at = "2000-01-01T09:00:00"
    fired = scheduler.fire_due()
    assert len(fired) == 1
    assert e.status == "pending", "repeating entry goes back to pending"
    assert e.at == "2000-01-02T09:00:00", "daily rolls forward exactly one day"


def test_failed_recipient_is_marked_not_fatal(scheduler):
    scheduler.add(to="no-such-recipient-here", text="boom", at="2000-01-01T09:00:00")
    fired = scheduler.fire_due()
    assert fired[0].status == "failed"
    assert fired[0].last_error


def test_fire_requires_session(tmp_path):
    sch = Scheduler(path=tmp_path / "s.json")
    sch.add(to="Ava", text="x", at="2000-01-01T09:00:00")
    with pytest.raises(RuntimeError):
        sch.fire_due()
