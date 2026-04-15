from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProcessResult:
    command: str
    return_code: int
    stdout: str
    stderr: str


class ProcessService:
    def run_powershell(
        self,
        command: str,
        on_complete: Callable[[ProcessResult], None],
        on_error: Callable[[Exception], None],
    ) -> threading.Thread:
        def worker() -> None:
            try:
                completed = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        command,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                )
                on_complete(
                    ProcessResult(
                        command=command,
                        return_code=completed.returncode,
                        stdout=completed.stdout,
                        stderr=completed.stderr,
                    )
                )
            except Exception as exc:
                on_error(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread
