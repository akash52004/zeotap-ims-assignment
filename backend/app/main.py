import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from .models import DashboardState, IngestResponse, RCAIn, Signal, SignalIn, StatusUpdate, WorkItemStatus
from .processor import SignalProcessor
from .rate_limit import SlidingWindowRateLimiter
from .storage import IncidentStore
from .workflow import IncompleteRCA, InvalidTransition, WorkItemStateMachine


DATA_DIR = os.getenv("IMS_DATA_DIR", "/tmp/ims")
RATE_LIMIT = int(os.getenv("IMS_RATE_LIMIT_PER_MINUTE", "12000"))

store = IncidentStore(
    db_path=os.path.join(DATA_DIR, "source_of_truth.sqlite3"),
    raw_log_path=os.path.join(DATA_DIR, "raw_signals.jsonl"),
)
processor = SignalProcessor(store)
limiter = SlidingWindowRateLimiter(limit=RATE_LIMIT, window_seconds=60)
workflow = WorkItemStateMachine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await processor.start()
    yield
    await processor.stop()


app = FastAPI(title="Mission-Critical Incident Management System", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("IMS_CORS_ORIGINS", "http://localhost:5173,http://localhost:8080").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str | int]:
    return {"status": "ok", "queue_depth": processor.queue.qsize()}


@app.post("/api/signals", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest(signal: SignalIn, request: Request) -> IngestResponse:
    return await ingest_batch([signal], request)


@app.post("/api/signals/batch", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_batch(signals: list[SignalIn], request: Request) -> IngestResponse:
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client):
        raise HTTPException(status_code=429, detail="ingestion rate limit exceeded")
    materialized = [Signal(**signal.model_dump()) for signal in signals[:1000]]
    accepted = await processor.enqueue(materialized)
    return IngestResponse(accepted=accepted, queued=processor.queue.qsize(), rejected=len(materialized) - accepted)


@app.get("/api/incidents")
async def list_incidents():
    items = list(processor.dashboard_cache.values()) or await store.list_work_items()
    return sorted(items, key=lambda item: (item.severity.value, item.updated_at), reverse=False)


@app.get("/api/incidents/{work_item_id}")
async def incident_detail(work_item_id: str):
    item = await store.get_work_item(work_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"incident": item, "signals": await store.get_signals(work_item_id)}


@app.patch("/api/incidents/{work_item_id}/status")
async def update_status(work_item_id: str, update: StatusUpdate):
    item = await store.get_work_item(work_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        workflow.validate(item, update.status)
    except (InvalidTransition, IncompleteRCA) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = await store.update_status(item, update.status)
    processor.dashboard_cache[updated.id] = updated
    return updated


@app.post("/api/incidents/{work_item_id}/rca")
async def submit_rca(work_item_id: str, rca: RCAIn):
    item = await store.get_work_item(work_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        workflow.validate(item, WorkItemStatus.CLOSED, rca)
    except (InvalidTransition, IncompleteRCA) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = await store.save_rca_and_status(item, rca, WorkItemStatus.CLOSED)
    processor.dashboard_cache[updated.id] = updated
    return updated


@app.get("/api/dashboard", response_model=DashboardState)
async def dashboard() -> DashboardState:
    items = list(processor.dashboard_cache.values()) or await store.list_work_items()
    active = [item for item in items if item.status != WorkItemStatus.CLOSED]
    counts: dict[str, int] = {}
    for item in items:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1
    return DashboardState(
        active=sorted(active, key=lambda item: item.severity.value),
        counts_by_status=counts,
        signal_rate_per_sec=await processor.meter.rate(),
        queue_depth=processor.queue.qsize(),
    )
