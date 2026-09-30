"""Scheduled sends — parley's gentle alarm clock.

Entries live in a JSON store (``~/.parley/schedules.json``, or
``PARLEY_DATA_DIR``) so ``parley schedule add`` survives server restarts. A
background thread started by ``parley server`` — or ``parley schedule run
--watch`` — wakes once a second, fires due entries through the same paced
:class:`Session` used interactively, and rolls repeating entries forward. A
scheduled blast obeys the same human budget as a manual send.

``repeat`` is ``None`` (fire once), ``"hourly"``, ``"daily"`` or ``"weekly"``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session import Session

DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".parley")

REPEATS = ("hourly", "daily", "weekly")

ISO = "%Y-%m-%dT%H:%M:%S"


def data_dir() -> str:
    return os.environ.get("PARLEY_DATA_DIR", DEFAULT_DATA_DIR)


def default_store_path() -> str:
    return os.path.join(data_dir(), "schedules.json")


def audit_log_path() -> str:
    return os.path.join(data_dir(), "audit.jsonl")


def _ensure_data_dir() -> None:
    """Create the data directory with owner-only permissions (POSIX)."""
    os.makedirs(data_dir(), mode=0o700, exist_ok=True)


def audit_send(chat_id: str, recipient: str, text: str, source: str = "send") -> None:
    """Append a single audit line for a sent message.

    Stored as ``~/.parley/audit.jsonl`` (0600 on POSIX). Each line is a JSON
    object: ``ts, chat_id, recipient, text_preview, source``.
    """
    _ensure_data_dir()
    import datetime as _dt
    preview = (text[:80] + "…") if len(text) > 80 else text
    line = json.dumps(
        {
            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
            "chat_id": chat_id,
            "recipient": recipient,
            "text_preview": preview,
            "source": source,
        },
        ensure_ascii=False,
    )
    path = audit_log_path()
    tmp = f"{path}.tmp"
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        content = ""
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
        if content and not content.endswith("\n"):
            fh.write("\n")
        fh.write(line + "\n")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)

@dataclass
class ScheduleEntry:
    """One queued message: it stays pending until its time, then fires."""

    id: str
    to: str  # chat id, contact name, group subject, or number — resolved at fire time
    text: str
    at: str  # ISO 8601 local time
    repeat: str | None = None  # None | hourly | daily | weekly
    status: str = "pending"  # pending | sent | failed
    last_fired: str | None = None
    last_error: str | None = None
    created: str = field(default_factory=lambda: datetime.now().strftime(ISO))

    def due(self, now: datetime) -> bool:
        if self.status != "pending":
            return False
        try:
            return now >= datetime.strptime(self.at, ISO) or now >= datetime.fromisoformat(self.at)
        except ValueError:
            return False

    def _then_datetime(self) -> datetime:
        try:
            return datetime.fromisoformat(self.at)
        except ValueError:
            return datetime.strptime(self.at, ISO)


class Scheduler:
    """A JSON-persisted queue of scheduled messages. Thread-safe."""

    def __init__(self, path: str | None = None, session: Session | None = None) -> None:
        self.path = path or default_store_path()
        self.session = session
        self._lock = threading.RLock()
        self._entries: dict[str, ScheduleEntry] = {}
        self._load()

    # ------------------------------------------------------------- storage
    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            for row in data:
                e = ScheduleEntry(**{k: row[k] for k in row if k in ScheduleEntry.__dataclass_fields__})
                self._entries[e.id] = e
        except (OSError, ValueError):
            self._entries = {}

    def _save(self) -> None:
        _ensure_data_dir()
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump([asdict(e) for e in self._entries.values()], fh, ensure_ascii=False, indent=2)
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    # ----------------------------------------------------------------- api
    def add(
        self,
        to: str,
        text: str,
        at: str,
        repeat: str | None = None,
        entry_id: str | None = None,
    ) -> ScheduleEntry:
        if repeat not in (None,) + REPEATS:
            raise ValueError(f"--repeat must be one of {', '.join(REPEATS)} (or omitted)")
        next_at = at
        if repeat:
            try:
                nxt = datetime.fromisoformat(at)
            except ValueError:
                raise ValueError(f"--at must be ISO time, got {at!r}") from None
            if nxt < datetime.now() - timedelta(seconds=30):
                raise ValueError(
                    "--at is in the past; repeating entries must start in the future "
                    f"(parse: {next_at})"
                )
        entry = ScheduleEntry(
            id=entry_id or f"s{int(time.time() * 1000)}",
            to=to,
            text=text,
            at=next_at,
            repeat=repeat,
        )
        with self._lock:
            self._entries[entry.id] = entry
            self._save()
        return entry

    def remove(self, entry_id: str) -> bool:
        with self._lock:
            gone = self._entries.pop(entry_id, None)
            if gone:
                self._save()
        return gone is not None

    def list(self) -> list[ScheduleEntry]:
        with self._lock:
            return sorted(self._entries.values(), key=lambda e: e.at)

    def get(self, entry_id: str) -> ScheduleEntry | None:
        with self._lock:
            return self._entries.get(entry_id)

    def clear(self) -> int:
        with self._lock:
            n = len(self._entries)
            self._entries = {}
            self._save()
        return n

    # ---------------------------------------------------------------- fire
    def fire_due(self, now: datetime | None = None) -> list[ScheduleEntry]:
        """Fire every due entry through the session; roll repeats forward.

        Returns the entries that fired (sent or failed). A bad recipient marks
        that entry failed and continues; but a budget-exhaustion aborts the
        whole batch (loud failure — caller must handle).
        """
        from .pacing import BudgetExceeded

        now = now or datetime.now()
        if self.session is None:
            raise RuntimeError("scheduler has no session; create it with a Session so sends can fire")
        due = [e for e in self.list() if e.due(now)]
        fired: list[ScheduleEntry] = []
        for entry in due:
            with self._lock:
                try:
                    self.session.send(entry.to, entry.text)
                    entry.status = "sent"
                    entry.last_error = None
                    audit_send(entry.to, entry.to, entry.text, source="scheduler")
                except BudgetExceeded as exc:
                    entry.status = "failed"
                    entry.last_error = f"budget_exceeded: {exc}"
                    audit_send(entry.to, entry.to, entry.text, source="budget_exceeded")
                    entry.last_fired = now.strftime(ISO)
                    fired.append(entry)
                    self._save()
                    raise  # loud: abort the batch, caller sees it
                except Exception as exc:  # noqa: BLE001 - one failure must not stall the queue
                    entry.status = "failed"
                    entry.last_error = str(exc)
                entry.last_fired = now.strftime(ISO)
                if entry.repeat:
                    entry.at = self._next_time(entry, now).strftime(ISO)
                    entry.status = "pending"
                fired.append(entry)
            self._save()
        return fired

    @staticmethod
    def _next_time(entry: ScheduleEntry, now: datetime) -> datetime:
        base = entry._then_datetime()
        if entry.repeat == "hourly":
            return base + timedelta(hours=1)
        if entry.repeat == "daily":
            return base + timedelta(days=1)
        return base + timedelta(weeks=1)


def run_loop(scheduler: Scheduler, interval: float = 1.0, stop: threading.Event | None = None) -> None:
    """Blocking pump: fire due entries until the stop event is set."""
    stop = stop or threading.Event()
    while not stop.is_set():
        start = time.monotonic()
        try:
            scheduler.fire_due()
        except RuntimeError:
            raise
        stop.wait(max(0.05, interval - (time.monotonic() - start)))


class SchedulerThread(threading.Thread):
    """Background thread that keeps firing due entries."""

    def __init__(self, scheduler: Scheduler, interval: float = 1.0, daemon: bool = True) -> None:
        super().__init__(name="parley-scheduler", daemon=daemon)
        self._scheduler = scheduler
        self._interval = interval
        self._stop = threading.Event()

    def run(self) -> None:
        run_loop(self._scheduler, interval=self._interval, stop=self._stop)

    def stop(self) -> None:
        self._stop.set()
