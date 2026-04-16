from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskType(Enum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    RUN = "RUN"
    VALIDATE = "VALIDATE"


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    id: str
    type: TaskType
    target: str  # file_path or command
    content: Optional[str] = None
    constraints: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    result: Optional[TaskResult] = None


@dataclass
class TaskResult:
    success: bool
    message: str
    output: str = ""
    error: str = ""
    changes: list[str] = field(default_factory=list)
