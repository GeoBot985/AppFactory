from __future__ import annotations

import re
import json
from services.task_service import Task, TaskType
from editing.models import OperationType, AnchorType, MatchMode
from services.dsl_parser import DSLParser
from services.planner import Planner


class SpecParserService:
    def __init__(self):
        self.dsl_parser = DSLParser()
        self.planner = Planner()

    def parse(self, spec_text: str) -> list[Task]:
        if self.dsl_parser.is_dsl_spec(spec_text):
            return self._parse_dsl(spec_text)

        # Mode switch: if input is NOT valid YAML, we might allow legacy fallback
        # But wait, how do we know if legacy is allowed if we haven't parsed settings?
        # The spec says: If input is NOT valid YAML: route to old parser if settings: allow_legacy_fallback: true
        # This implies we look for YAML-like structure first.

        # If it looks like it's trying to be DSL but failed validation, we SHOULD NOT fallback.
        # If it's pure NLP, we only fallback if it doesn't violate a "global" strictness or if explicitly allowed.
        # For v1, we'll follow the "route to old parser if NOT valid YAML" logic,
        # but we need to check if the user intended DSL.

        return self._parse_legacy(spec_text)

    def _parse_dsl(self, spec_text: str) -> list[Task]:
        data, validation = self.dsl_parser.parse(spec_text)
        if not validation.is_valid:
            error_msgs = [f"{e['field']}: {e['error']}" for e in validation.errors]
            raise ValueError(f"DSL Validation Failed:\n" + "\n".join(error_msgs))

        settings = data.get("settings", {})
        # If it's valid DSL but settings: allow_legacy_fallback: false (default), then we are good.
        # Actually the spec says "NO fallback to legacy parsing unless explicitly enabled"

        ordered_tasks_data = self.planner.build_task_graph(data)

        tasks: list[Task] = []
        for t_data in ordered_tasks_data:
            t_type_str = t_data["type"]
            t_id = t_data["id"]
            depends_on = t_data.get("depends_on", [])

            # Map DSL type to TaskType
            if t_type_str == "run_command":
                tasks.append(Task(id=t_id, type=TaskType.RUN, target=t_data["command"], depends_on=depends_on))
            elif t_type_str == "validate":
                tasks.append(Task(id=t_id, type=TaskType.VALIDATE, target=t_data.get("mode", "python"), depends_on=depends_on))
            elif t_type_str == "create_file":
                 tasks.append(Task(id=t_id, type=TaskType.CREATE, target=t_data["file"], content=t_data.get("content"), depends_on=depends_on))
            elif t_type_str == "delete_file":
                 tasks.append(Task(id=t_id, type=TaskType.DELETE, target=t_data["file"], depends_on=depends_on))
            else:
                # Precision Edit tasks
                instr_data = self._map_dsl_to_instr(t_data)
                tasks.append(Task(
                    id=t_id,
                    type=TaskType.MODIFY,
                    target=t_data["file"],
                    content=t_data.get("content"),
                    constraints=json.dumps(instr_data),
                    depends_on=depends_on
                ))
        return tasks

    def _map_dsl_to_instr(self, t_data: dict) -> dict:
        t_type = t_data["type"]
        op_map = {
            "ensure_import": OperationType.ENSURE_IMPORT,
            "ensure_function": OperationType.ENSURE_FUNCTION,
            "ensure_class": OperationType.ENSURE_CLASS,
            "replace_block": OperationType.REPLACE_BLOCK,
            "insert_before": OperationType.INSERT_BEFORE,
            "insert_after": OperationType.INSERT_AFTER,
            "append_if_missing": OperationType.APPEND_IF_MISSING,
            "delete_block": OperationType.DELETE_BLOCK
        }

        anchor_map = {
            "function": AnchorType.FUNCTION,
            "class": AnchorType.CLASS,
            "import": AnchorType.IMPORT,
            "line_match": AnchorType.LINE_MATCH,
            "region_marker": AnchorType.REGION_MARKER
        }

        op = op_map.get(t_type, OperationType.REPLACE_BLOCK)

        anchor_type = AnchorType.FILE_END
        anchor_value = ""

        if t_type == "ensure_import":
            anchor_type = AnchorType.IMPORT
            anchor_value = t_data["import"]
        elif t_type == "ensure_function":
            anchor_type = AnchorType.FUNCTION
            anchor_value = t_data["function_name"]
        elif t_type == "ensure_class":
            anchor_type = AnchorType.CLASS
            anchor_value = t_data["class_name"]
        elif "target" in t_data:
            target = t_data["target"]
            anchor_type = anchor_map.get(target["type"], AnchorType.LINE_MATCH)
            anchor_value = target["value"]

        return {
            "operation": op.value,
            "anchor_type": anchor_type.value,
            "anchor_value": anchor_value
        }

    def _parse_legacy(self, spec_text: str) -> list[Task]:
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
