from __future__ import annotations

import re
from services.task_service import Task, TaskType
from editing.models import OperationType, AnchorType, MatchMode


class SpecParserService:
    def parse(self, spec_text: str) -> list[Task]:
        tasks: list[Task] = []
        lines = spec_text.splitlines()

        # Simple heuristic patterns
        create_pattern = re.compile(r"create file\s+([\w\./-]+)", re.IGNORECASE)
        update_pattern = re.compile(r"update file\s+([\w\./-]+)", re.IGNORECASE)
        delete_pattern = re.compile(r"delete file\s+([\w\./-]+)", re.IGNORECASE)
        run_pattern = re.compile(r"run command\s+(.+)", re.IGNORECASE)
        validate_pattern = re.compile(r"validate\s+(.+)", re.IGNORECASE)

        # SPEC 011 Precision patterns
        # Form A: Modify src/foo.py by replacing function build_index with the following implementation...
        modify_replace_fn_pattern = re.compile(r"Modify ([\w\./-]+) by replacing function (\w+)", re.IGNORECASE)
        # Form B: Ensure import "from pathlib import Path" exists in src/foo.py
        ensure_import_pattern = re.compile(r"Ensure import \"(.+)\" exists in ([\w\./-]+)", re.IGNORECASE)
        # Form C: Add function summarize_run to src/logging.py
        add_fn_pattern = re.compile(r"Add function (\w+) to ([\w\./-]+)", re.IGNORECASE)
        # Form D: Insert the following block after class QueueRunner in src/queue.py
        insert_after_class_pattern = re.compile(r"Insert .+ after class (\w+) in ([\w\./-]+)", re.IGNORECASE)
        # Form E: Delete function old_handler from src/legacy.py
        delete_fn_pattern = re.compile(r"Delete function (\w+) from ([\w\./-]+)", re.IGNORECASE)

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Check precision patterns first
            match = modify_replace_fn_pattern.search(line)
            if match:
                tasks.append(self._create_modify_task(tasks, match.group(1), OperationType.REPLACE_BLOCK, AnchorType.FUNCTION, match.group(2)))
                continue

            match = ensure_import_pattern.search(line)
            if match:
                tasks.append(self._create_modify_task(tasks, match.group(2), OperationType.ENSURE_IMPORT, AnchorType.IMPORT, match.group(1)))
                continue

            match = add_fn_pattern.search(line)
            if match:
                tasks.append(self._create_modify_task(tasks, match.group(2), OperationType.ENSURE_FUNCTION, AnchorType.FUNCTION, match.group(1)))
                continue

            match = insert_after_class_pattern.search(line)
            if match:
                tasks.append(self._create_modify_task(tasks, match.group(2), OperationType.INSERT_AFTER, AnchorType.CLASS, match.group(1)))
                continue

            match = delete_fn_pattern.search(line)
            if match:
                tasks.append(self._create_modify_task(tasks, match.group(2), OperationType.DELETE_BLOCK, AnchorType.FUNCTION, match.group(1)))
                continue

            # Fallback to generic patterns
            match = create_pattern.search(line)
            if match:
                tasks.append(Task(id=f"task_{len(tasks)+1}", type=TaskType.CREATE, target=match.group(1)))
                continue

            match = update_pattern.search(line)
            if match:
                tasks.append(Task(id=f"task_{len(tasks)+1}", type=TaskType.MODIFY, target=match.group(1)))
                continue

            match = delete_pattern.search(line)
            if match:
                tasks.append(Task(id=f"task_{len(tasks)+1}", type=TaskType.DELETE, target=match.group(1)))
                continue

            match = run_pattern.search(line)
            if match:
                tasks.append(Task(id=f"task_{len(tasks)+1}", type=TaskType.RUN, target=match.group(1)))
                continue

            match = validate_pattern.search(line)
            if match:
                tasks.append(Task(id=f"task_{len(tasks)+1}", type=TaskType.VALIDATE, target=match.group(1)))
                continue

        return tasks

    def _create_modify_task(self, tasks, target, op, anchor_type, anchor_value):
        # We store precision info in metadata or constraints for now,
        # but Task object might need expansion.
        # For simplicity, let's use a structured string in 'constraints' or a new field.
        # SPEC 011 says Task Executor must use EditInstruction.
        # Let's use a JSON-like string in constraints for internal passing.
        import json
        instr_data = {
            "operation": op.value,
            "anchor_type": anchor_type.value,
            "anchor_value": anchor_value
        }
        return Task(
            id=f"task_{len(tasks)+1}",
            type=TaskType.MODIFY,
            target=target,
            constraints=json.dumps(instr_data)
        )
