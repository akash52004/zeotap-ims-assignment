from datetime import datetime, timedelta, timezone

import pytest

from app.models import ComponentType, RCAIn, Severity, WorkItem, WorkItemStatus
from app.workflow import IncompleteRCA, InvalidTransition, WorkItemStateMachine


def make_item(status: WorkItemStatus = WorkItemStatus.RESOLVED) -> WorkItem:
    now = datetime.now(timezone.utc)
    return WorkItem(
        id="wi-1",
        component_id="RDBMS_PRIMARY_01",
        component_type=ComponentType.RDBMS,
        severity=Severity.P0,
        status=status,
        title="RDBMS failure",
        first_signal_at=now,
        last_signal_at=now,
        signal_count=100,
        alert_target="pagerduty:database-primary",
        created_at=now,
        updated_at=now,
    )


def make_rca() -> RCAIn:
    now = datetime.now(timezone.utc)
    return RCAIn(
        start_time=now - timedelta(minutes=12),
        end_time=now,
        root_cause_category="Capacity",
        fix_applied="Increased connection pool and restarted saturated primary node.",
        prevention_steps="Add connection pool saturation alerts and weekly load tests.",
    )


def test_rejects_close_without_rca() -> None:
    machine = WorkItemStateMachine()

    with pytest.raises(IncompleteRCA):
        machine.validate(make_item(), WorkItemStatus.CLOSED)


def test_rejects_close_with_invalid_rca_window() -> None:
    machine = WorkItemStateMachine()
    rca = make_rca()
    rca.end_time = rca.start_time - timedelta(seconds=1)

    with pytest.raises(IncompleteRCA):
        machine.validate(make_item(), WorkItemStatus.CLOSED, rca)


def test_allows_close_when_resolved_and_rca_complete() -> None:
    machine = WorkItemStateMachine()

    machine.validate(make_item(), WorkItemStatus.CLOSED, make_rca())


def test_rejects_invalid_state_jump() -> None:
    machine = WorkItemStateMachine()

    with pytest.raises(InvalidTransition):
        machine.validate(make_item(WorkItemStatus.OPEN), WorkItemStatus.CLOSED, make_rca())
