from .models import RCAIn, WorkItem, WorkItemStatus


class InvalidTransition(ValueError):
    pass


class IncompleteRCA(ValueError):
    pass


class WorkItemStateMachine:
    _allowed: dict[WorkItemStatus, set[WorkItemStatus]] = {
        WorkItemStatus.OPEN: {WorkItemStatus.INVESTIGATING, WorkItemStatus.RESOLVED},
        WorkItemStatus.INVESTIGATING: {WorkItemStatus.RESOLVED, WorkItemStatus.OPEN},
        WorkItemStatus.RESOLVED: {WorkItemStatus.CLOSED, WorkItemStatus.INVESTIGATING},
        WorkItemStatus.CLOSED: set(),
    }

    def validate(self, item: WorkItem, target: WorkItemStatus, rca: RCAIn | None = None) -> None:
        if target == item.status:
            return
        if target not in self._allowed[item.status]:
            raise InvalidTransition(f"{item.status.value} cannot transition to {target.value}")
        if target == WorkItemStatus.CLOSED:
            candidate = rca or item.rca
            if not candidate:
                raise IncompleteRCA("RCA is mandatory before closing an incident")
            if candidate.end_time < candidate.start_time:
                raise IncompleteRCA("RCA end_time must be after start_time")
