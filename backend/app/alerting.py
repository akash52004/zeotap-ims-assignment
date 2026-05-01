from abc import ABC, abstractmethod

from .models import ComponentType, Severity, Signal


class AlertStrategy(ABC):
    @abstractmethod
    def classify(self, signal: Signal) -> tuple[Severity, str]:
        raise NotImplementedError


class DatabaseAlertStrategy(AlertStrategy):
    def classify(self, signal: Signal) -> tuple[Severity, str]:
        return Severity.P0, "pagerduty:database-primary"


class CacheAlertStrategy(AlertStrategy):
    def classify(self, signal: Signal) -> tuple[Severity, str]:
        return Severity.P2, "slack:#cache-ops"


class QueueAlertStrategy(AlertStrategy):
    def classify(self, signal: Signal) -> tuple[Severity, str]:
        return Severity.P1, "pagerduty:streaming"


class DefaultAlertStrategy(AlertStrategy):
    def classify(self, signal: Signal) -> tuple[Severity, str]:
        if signal.latency_ms and signal.latency_ms > 2000:
            return Severity.P1, "slack:#platform-oncall"
        return Severity.P3, "slack:#service-owners"


class AlertRouter:
    def __init__(self) -> None:
        self._strategies: dict[ComponentType, AlertStrategy] = {
            ComponentType.RDBMS: DatabaseAlertStrategy(),
            ComponentType.NOSQL: DatabaseAlertStrategy(),
            ComponentType.CACHE: CacheAlertStrategy(),
            ComponentType.QUEUE: QueueAlertStrategy(),
        }
        self._default = DefaultAlertStrategy()

    def classify(self, signal: Signal) -> tuple[Severity, str]:
        return self._strategies.get(signal.component_type, self._default).classify(signal)
