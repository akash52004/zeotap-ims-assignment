import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import RCAIn, Signal, WorkItem, WorkItemStatus


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _dump_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value)!r} is not JSON serializable")


class IncidentStore:
    def __init__(self, db_path: str, raw_log_path: str) -> None:
        self.db_path = Path(db_path)
        self.raw_log_path = Path(raw_log_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS work_items (
                    id TEXT PRIMARY KEY,
                    component_id TEXT NOT NULL,
                    component_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    first_signal_at TEXT NOT NULL,
                    last_signal_at TEXT NOT NULL,
                    signal_count INTEGER NOT NULL,
                    alert_target TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    mttr_seconds INTEGER
                );
                CREATE TABLE IF NOT EXISTS rcas (
                    work_item_id TEXT PRIMARY KEY REFERENCES work_items(id),
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    root_cause_category TEXT NOT NULL,
                    fix_applied TEXT NOT NULL,
                    prevention_steps TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    work_item_id TEXT NOT NULL REFERENCES work_items(id),
                    component_id TEXT NOT NULL,
                    component_type TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signal_aggregates (
                    bucket_minute TEXT NOT NULL,
                    component_type TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY (bucket_minute, component_type)
                );
                """
            )

    async def append_raw_signal(self, signal: Signal) -> None:
        line = json.dumps(signal.model_dump(), default=_dump_dt, separators=(",", ":"))
        async with self._lock:
            await asyncio.to_thread(self._append_raw_signal_sync, line)

    def _append_raw_signal_sync(self, line: str) -> None:
        with self.raw_log_path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")

    async def upsert_debounced(self, signal: Signal, item: WorkItem, debounce_seconds: int = 10) -> WorkItem:
        async with self._lock:
            return await asyncio.to_thread(self._upsert_debounced_sync, signal, item, debounce_seconds)

    def _upsert_debounced_sync(self, signal: Signal, item: WorkItem, debounce_seconds: int) -> WorkItem:
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM work_items
                WHERE component_id = ? AND status != 'CLOSED'
                ORDER BY created_at DESC LIMIT 1
                """,
                (signal.component_id,),
            ).fetchone()
            now = datetime.now(timezone.utc)
            within_debounce_window = False
            if existing:
                last_signal_at = _dt(existing["last_signal_at"])
                within_debounce_window = abs((signal.observed_at - last_signal_at).total_seconds()) <= debounce_seconds
            if existing and within_debounce_window:
                work_item_id = existing["id"]
                conn.execute(
                    """
                    UPDATE work_items
                    SET last_signal_at = ?, signal_count = signal_count + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (signal.observed_at.isoformat(), now.isoformat(), work_item_id),
                )
            else:
                work_item_id = item.id
                conn.execute(
                    """
                    INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.component_id,
                        item.component_type.value,
                        item.severity.value,
                        item.status.value,
                        item.title,
                        item.first_signal_at.isoformat(),
                        item.last_signal_at.isoformat(),
                        item.signal_count,
                        item.alert_target,
                        item.created_at.isoformat(),
                        item.updated_at.isoformat(),
                        item.mttr_seconds,
                    ),
                )
            signal.work_item_id = work_item_id
            conn.execute(
                """
                INSERT OR IGNORE INTO signals VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.id,
                    work_item_id,
                    signal.component_id,
                    signal.component_type.value,
                    signal.observed_at.isoformat(),
                    signal.received_at.isoformat(),
                    json.dumps(signal.model_dump(), default=_dump_dt),
                ),
            )
            bucket = signal.observed_at.replace(second=0, microsecond=0).isoformat()
            conn.execute(
                """
                INSERT INTO signal_aggregates VALUES (?, ?, 1)
                ON CONFLICT(bucket_minute, component_type)
                DO UPDATE SET count = count + 1
                """,
                (bucket, signal.component_type.value),
            )
            row = conn.execute("SELECT * FROM work_items WHERE id = ?", (work_item_id,)).fetchone()
            return self._row_to_work_item(row, None)

    async def list_work_items(self) -> list[WorkItem]:
        async with self._lock:
            return await asyncio.to_thread(self._list_work_items_sync)

    def _list_work_items_sync(self) -> list[WorkItem]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM work_items
                ORDER BY CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
                         updated_at DESC
                """
            ).fetchall()
            return [self._row_to_work_item(row, self._load_rca(conn, row["id"])) for row in rows]

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_work_item_sync, work_item_id)

    def _get_work_item_sync(self, work_item_id: str) -> WorkItem | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM work_items WHERE id = ?", (work_item_id,)).fetchone()
            if not row:
                return None
            return self._row_to_work_item(row, self._load_rca(conn, work_item_id))

    async def get_signals(self, work_item_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._get_signals_sync, work_item_id)

    def _get_signals_sync(self, work_item_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM signals WHERE work_item_id = ? ORDER BY received_at DESC LIMIT 250",
                (work_item_id,),
            ).fetchall()
            return [json.loads(row["payload_json"]) for row in rows]

    async def save_rca_and_status(self, item: WorkItem, rca: RCAIn, status: WorkItemStatus) -> WorkItem:
        async with self._lock:
            return await asyncio.to_thread(self._save_rca_and_status_sync, item, rca, status)

    def _save_rca_and_status_sync(self, item: WorkItem, rca: RCAIn, status: WorkItemStatus) -> WorkItem:
        mttr = int((rca.end_time - rca.start_time).total_seconds())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rcas VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_item_id) DO UPDATE SET
                  start_time=excluded.start_time,
                  end_time=excluded.end_time,
                  root_cause_category=excluded.root_cause_category,
                  fix_applied=excluded.fix_applied,
                  prevention_steps=excluded.prevention_steps
                """,
                (
                    item.id,
                    rca.start_time.isoformat(),
                    rca.end_time.isoformat(),
                    rca.root_cause_category,
                    rca.fix_applied,
                    rca.prevention_steps,
                ),
            )
            conn.execute(
                "UPDATE work_items SET status = ?, mttr_seconds = ?, updated_at = ? WHERE id = ?",
                (status.value, mttr, now, item.id),
            )
            row = conn.execute("SELECT * FROM work_items WHERE id = ?", (item.id,)).fetchone()
            return self._row_to_work_item(row, rca)

    async def update_status(self, item: WorkItem, status: WorkItemStatus) -> WorkItem:
        async with self._lock:
            return await asyncio.to_thread(self._update_status_sync, item.id, status)

    def _update_status_sync(self, work_item_id: str, status: WorkItemStatus) -> WorkItem:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("UPDATE work_items SET status = ?, updated_at = ? WHERE id = ?", (status.value, now, work_item_id))
            row = conn.execute("SELECT * FROM work_items WHERE id = ?", (work_item_id,)).fetchone()
            return self._row_to_work_item(row, self._load_rca(conn, work_item_id))

    def _load_rca(self, conn: sqlite3.Connection, work_item_id: str) -> RCAIn | None:
        row = conn.execute("SELECT * FROM rcas WHERE work_item_id = ?", (work_item_id,)).fetchone()
        if not row:
            return None
        return RCAIn(
            start_time=_dt(row["start_time"]),
            end_time=_dt(row["end_time"]),
            root_cause_category=row["root_cause_category"],
            fix_applied=row["fix_applied"],
            prevention_steps=row["prevention_steps"],
        )

    def _row_to_work_item(self, row: sqlite3.Row, rca: RCAIn | None) -> WorkItem:
        return WorkItem(
            id=row["id"],
            component_id=row["component_id"],
            component_type=row["component_type"],
            severity=row["severity"],
            status=row["status"],
            title=row["title"],
            first_signal_at=_dt(row["first_signal_at"]),
            last_signal_at=_dt(row["last_signal_at"]),
            signal_count=row["signal_count"],
            alert_target=row["alert_target"],
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
            mttr_seconds=row["mttr_seconds"],
            rca=rca,
        )
