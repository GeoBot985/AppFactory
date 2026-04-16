from __future__ import annotations
from typing import List, Dict, Any
from services.draft_spec.models import DraftTask
from services.task_service import Task, TaskType

class TaskLowerer:
    def lower(self, draft_task: DraftTask) -> List[Task]:
        """Lowers a high-level DraftTask into one or more executable Tasks."""
        # Simple mapping for now
        t_type_map = {
            "generate_file": TaskType.MODIFY,
            "patch_file": TaskType.MODIFY,
            "create_file": TaskType.CREATE,
            "run_tests": TaskType.RUN,
            "run_command": TaskType.RUN
        }

        # Specialized lowering
        if draft_task.type == "build_app":
            # This would be expanded into multiple tasks in a real implementation
            return [
                Task(
                    id=f"{draft_task.id}_init",
                    type=TaskType.CREATE,
                    target=draft_task.path,
                    content=f"# Generated from {draft_task.id}\n"
                ),
                Task(
                    id=f"{draft_task.id}_tests",
                    type=TaskType.RUN,
                    target="pytest", # Example
                    depends_on=[f"{draft_task.id}_init"]
                )
            ]

        t_type = t_type_map.get(draft_task.type, TaskType.MODIFY)

        return [
            Task(
                id=draft_task.id,
                type=t_type,
                target=draft_task.path if t_type != TaskType.RUN else draft_task.summary,
                depends_on=draft_task.depends_on
            )
        ]
