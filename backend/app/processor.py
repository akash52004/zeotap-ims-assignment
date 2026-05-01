import asyncio
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4

from .alerting import AlertRouter
from .models import Signal, WorkItem, WorkItemStatus
from .storage import IncidentStore


class ThroughputMeter:
    def __init__(self) -> None:
        self._events: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def mark(self, count: int = 1) -> None:
        now = asyncio.get_running_loop().time()
        async with self._lock:
            for _ in range(count):
                self._events.append(now)

    async def rate(self) -> float:
        now = asyncio.get_running_loop().time()
        async with self._lock:
            while self._events and now - self._events[0] > 5:
                self._events.popleft()
            return len(self._events) / 5


class SignalProcessor:
    def __init__(self, store: IncidentStore, queue_size: int = 50000, debounce_seconds: int = 10) -> None:
        self.store = store
        self.debounce_seconds = debounce_seconds
        self.queue: asyncio.Queue[Signal] = asyncio.Queue(maxsize=queue_size)
        self.alerts = AlertRouter()
        self.meter = ThroughputMeter()
        self._workers: list[asyncio.Task[None]] = []
        self.dashboard_cache: dict[str, WorkItem] = {}

    async def start(self, workers: int = 4) -> None:
        self.dashboard_cache = {item.id: item for item in await self.store.list_work_items()}
        self._workers = [asyncio.create_task(self._worker(), name=f"signal-worker-{i}") for i in range(workers)]
        self._workers.append(asyncio.create_task(self._log_metrics(), name="throughput-logger"))

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def enqueue(self, signals: list[Signal]) -> int:
        accepted = 0
        for signal in signals:
            try:
                self.queue.put_nowait(signal)
                accepted += 1
            except asyncio.QueueFull:
                break
        await self.meter.mark(accepted)
        return accepted

    async def _worker(self) -> None:
        while True:
            signal = await self.queue.get()
            try:
                await self.store.append_raw_signal(signal)
                severity, target = self.alerts.classify(signal)
                now = datetime.now(timezone.utc)
                candidate = WorkItem(
                    id=str(uuid4()),
                    component_id=signal.component_id,
                    component_type=signal.component_type,
                    severity=severity,
                    status=WorkItemStatus.OPEN,
                    title=f"{signal.component_type.value} failure on {signal.component_id}",
                    first_signal_at=signal.observed_at,
                    last_signal_at=signal.observed_at,
                    signal_count=1,
                    alert_target=target,
                    created_at=now,
                    updated_at=now,
                )
                item = await self._retry(lambda: self.store.upsert_debounced(signal, candidate, self.debounce_seconds))
                self.dashboard_cache[item.id] = item
            finally:
                self.queue.task_done()

    async def _retry(self, op, attempts: int = 3):
        delay = 0.05
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                return await op()
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(delay)
                delay *= 2
        raise last_error  # type: ignore[misc]

    async def _log_metrics(self) -> None:
        while True:
            await asyncio.sleep(5)
            print(f"ims_throughput signals_per_sec={await self.meter.rate():.2f} queue_depth={self.queue.qsize()}", flush=True)
