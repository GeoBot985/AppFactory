import datetime
from typing import Literal, Optional, Any, Dict, List
from pydantic import BaseModel, Field
import uuid

TelemetryEventType = Literal[
    "run_started",
    "run_completed",
    "step_started",
    "step_completed",
    "step_failed",
    "retry_attempt",
    "rollback_started",
    "rollback_completed",
    "verification_run",
    "verification_result",
    "promotion_decision"
]

class TelemetryEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    event_type: TelemetryEventType
    payload: Dict[str, Any]

MetricType = Literal["counter", "gauge", "histogram"]

class Metric(BaseModel):
    metric_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = Field(default_factory=dict)
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)

class AlertRule(BaseModel):
    rule_id: str
    condition: str
    threshold: float
    severity: Literal["info", "warning", "critical"]

class Alert(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    rule: str
    severity: Literal["info", "warning", "critical"]
    value: float
    message: Optional[str] = None

class DailyAggregate(BaseModel):
    date: str  # YYYY-MM-DD
    runs_total: int = 0
    runs_completed: int = 0
    runs_failed: int = 0
    runs_partial_failure: int = 0
    failure_rate: float = 0.0
    steps_total: int = 0
    steps_failed: int = 0
    steps_recovered_via_retry: int = 0
    retries_total: int = 0
    retry_success_rate: float = 0.0
    rollback_invocations: int = 0
    rollback_success_rate: float = 0.0
    verification_runs_total: int = 0
    verification_pass: int = 0
    verification_warn: int = 0
    verification_fail: int = 0
    drift_events_total: int = 0
    promotions_attempted: int = 0
    promotions_approved: int = 0
    promotions_rejected: int = 0
    promotions_overridden: int = 0
    run_duration_p50_ms: float = 0.0
    run_duration_p95_ms: float = 0.0
    step_duration_p50_ms: float = 0.0
    step_duration_p95_ms: float = 0.0
    stability_score: float = 0.0
    drift_rate: float = 0.0
    reliability_index: float = 0.0
