from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ComponentType(str, Enum):
    API = "API"
    MCP_HOST = "MCP_HOST"
    CACHE = "CACHE"
    QUEUE = "QUEUE"
    RDBMS = "RDBMS"
    NOSQL = "NOSQL"


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class WorkItemStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SignalIn(BaseModel):
    component_id: str = Field(min_length=2, max_length=80)
    component_type: ComponentType
    message: str = Field(min_length=3, max_length=500)
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=80)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


class Signal(SignalIn):
    id: str = Field(default_factory=lambda: str(uuid4()))
    work_item_id: str | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RCAIn(BaseModel):
    start_time: datetime
    end_time: datetime
    root_cause_category: str = Field(min_length=2, max_length=80)
    fix_applied: str = Field(min_length=10, max_length=4000)
    prevention_steps: str = Field(min_length=10, max_length=4000)


class WorkItem(BaseModel):
    id: str
    component_id: str
    component_type: ComponentType
    severity: Severity
    status: WorkItemStatus
    title: str
    first_signal_at: datetime
    last_signal_at: datetime
    signal_count: int
    alert_target: str
    created_at: datetime
    updated_at: datetime
    mttr_seconds: int | None = None
    rca: RCAIn | None = None


class StatusUpdate(BaseModel):
    status: WorkItemStatus


class IngestResponse(BaseModel):
    accepted: int
    queued: int
    rejected: int


class DashboardState(BaseModel):
    active: list[WorkItem]
    counts_by_status: dict[str, int]
    signal_rate_per_sec: float
    queue_depth: int
