from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskType(Enum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    RUN = "RUN"
    VALIDATE = "VALIDATE"

    # Concrete types for Compiled Plan (Spec 028)
    READ_CONTEXT = "READ_CONTEXT"
    GENERATE_FILE = "GENERATE_FILE"
    GENERATE_PATCH = "GENERATE_PATCH"
    CREATE_FILE = "CREATE_FILE"
    REPLACE_FILE = "REPLACE_FILE"
    PATCH_FILE = "PATCH_FILE"
    RUN_PYTHON_PARSE_VALIDATION = "RUN_PYTHON_PARSE_VALIDATION"
    RUN_BATCH_COHERENCE_VALIDATION = "RUN_BATCH_COHERENCE_VALIDATION"
    RUN_TESTS = "RUN_TESTS"
    APPLY_MUTATIONS = "APPLY_MUTATIONS"


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
    details: dict[str, Any] = field(default_factory=dict)
