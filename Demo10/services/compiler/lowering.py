from __future__ import annotations
from typing import List, Dict, Any
from services.draft_spec.models import DraftTask
from services.task_service import Task, TaskType

class TaskLowerer:
    def lower(self, draft_task: DraftTask) -> List[Task]:
        """Lowers a high-level DraftTask into one or more executable Tasks."""
        # Mapping to concrete types (Spec 028)
        t_type_map = {
            "generate_file": TaskType.GENERATE_FILE,
            "patch_file": TaskType.GENERATE_PATCH,
            "create_file": TaskType.CREATE_FILE,
            "replace_file": TaskType.REPLACE_FILE,
            "patch_file_op": TaskType.PATCH_FILE,
            "run_tests": TaskType.RUN_TESTS,
            "run_command": TaskType.RUN,
            "read_context": TaskType.READ_CONTEXT,
            "python_parse": TaskType.RUN_PYTHON_PARSE_VALIDATION,
            "batch_coherence": TaskType.RUN_BATCH_COHERENCE_VALIDATION,
            "apply": TaskType.APPLY_MUTATIONS
        }

        # Specialized lowering
        if draft_task.type == "build_app":
            # Example of expansion into multiple concrete steps
            return [
                Task(
                    id=f"{draft_task.id}_context",
                    type=TaskType.READ_CONTEXT,
                    target="."
                ),
                Task(
                    id=f"{draft_task.id}_init",
                    type=TaskType.CREATE_FILE,
                    target=draft_task.path,
                    content=f"# Generated from {draft_task.id}\n",
                    depends_on=[f"{draft_task.id}_context"]
                ),
                Task(
                    id=f"{draft_task.id}_val",
                    type=TaskType.RUN_PYTHON_PARSE_VALIDATION,
                    target=draft_task.path,
                    depends_on=[f"{draft_task.id}_init"]
                ),
                Task(
                    id=f"{draft_task.id}_tests",
                    type=TaskType.RUN_TESTS,
                    target="pytest",
                    depends_on=[f"{draft_task.id}_val"]
                ),
                Task(
                    id=f"{draft_task.id}_apply",
                    type=TaskType.APPLY_MUTATIONS,
                    target=".",
                    depends_on=[f"{draft_task.id}_tests"]
                )
            ]

        t_type = t_type_map.get(draft_task.type, TaskType.MODIFY)

        return [
            Task(
                id=draft_task.id,
                type=t_type,
                target=draft_task.path if t_type not in (TaskType.RUN, TaskType.RUN_TESTS) else draft_task.summary,
                depends_on=draft_task.depends_on
            )
        ]
