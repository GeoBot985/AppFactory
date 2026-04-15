from __future__ import annotations

import re
from services.task_service import Task, TaskType


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

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

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
