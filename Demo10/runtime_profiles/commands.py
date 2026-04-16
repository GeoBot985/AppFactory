from __future__ import annotations
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
from .models import RuntimeProfile

@dataclass
class CommandResult:
    command: List[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    profile_id: str
    interpreter: str
    cwd: str
    timeout_reached: bool = False

class CommandExecutor:
    def __init__(self, profile: RuntimeProfile, interpreter: str, env: Dict[str, str], cwd: Path):
        self.profile = profile
        self.interpreter = interpreter
        self.env = env
        self.cwd = cwd

    def run(self, command: Union[str, List[str]], timeout_seconds: Optional[int] = None) -> CommandResult:
        if timeout_seconds is None:
            timeout_seconds = self.profile.command_policy.timeout_seconds_default

        # Validate command against allow/deny policy
        cmd_list = self._prepare_command(command)
        first_token = cmd_list[0] if cmd_list else ""

        if not self._is_allowed(first_token):
             return CommandResult(
                command=cmd_list,
                exit_code=-1,
                stdout="",
                stderr=f"COMMAND_NOT_ALLOWED: '{first_token}' is not in allowlist or is in denylist",
                duration_ms=0,
                profile_id=self.profile.profile_id,
                interpreter=self.interpreter,
                cwd=str(self.cwd)
            )

        start_time = time.time()
        timeout_reached = False
        try:
            process = subprocess.run(
                cmd_list,
                env=self.env,
                cwd=str(self.cwd),
                capture_output=True,
                text=True,
                shell=self.profile.command_policy.shell,
                timeout=timeout_seconds
            )
            duration_ms = int((time.time() - start_time) * 1000)
            return CommandResult(
                command=cmd_list,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                duration_ms=duration_ms,
                profile_id=self.profile.profile_id,
                interpreter=self.interpreter,
                cwd=str(self.cwd)
            )
        except subprocess.TimeoutExpired as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return CommandResult(
                command=cmd_list,
                exit_code=-1,
                stdout=e.stdout if e.stdout else "",
                stderr=e.stderr if e.stderr else "COMMAND_TIMEOUT",
                duration_ms=duration_ms,
                profile_id=self.profile.profile_id,
                interpreter=self.interpreter,
                cwd=str(self.cwd),
                timeout_reached=True
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return CommandResult(
                command=cmd_list,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                profile_id=self.profile.profile_id,
                interpreter=self.interpreter,
                cwd=str(self.cwd)
            )

    def _prepare_command(self, command: Union[str, List[str]]) -> List[str]:
        if isinstance(command, list):
            return command
        # If it's a string, we might need to split it if shell=False
        if not self.profile.command_policy.shell:
            import shlex
            return shlex.split(command)
        return [command]

    def _is_allowed(self, executable: str) -> bool:
        policy = self.profile.command_policy

        # Deny list wins
        if policy.deny_commands and executable in policy.deny_commands:
            return False

        # If allow list exists, it must be in it
        if policy.allow_commands and executable not in policy.allow_commands:
            return False

        return True
