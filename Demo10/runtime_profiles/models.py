from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class InterpreterMode(Enum):
    PATH = "path"
    EXECUTABLE = "executable"
    WORKSPACE_RELATIVE = "workspace_relative"

class EnvInheritMode(Enum):
    NONE = "none"
    MINIMAL = "minimal"
    FULL = "full"

class DriftPolicyMode(Enum):
    FAIL = "fail"
    WARN = "warn"
    IGNORE = "ignore"

@dataclass
class InterpreterConfig:
    mode: InterpreterMode
    value: str

@dataclass
class EnvConfig:
    inherit_mode: EnvInheritMode = EnvInheritMode.MINIMAL
    allowlist: List[str] = field(default_factory=lambda: ["PATH", "SYSTEMROOT", "TEMP", "TMP"])
    blocklist: List[str] = field(default_factory=list)
    inject: Dict[str, str] = field(default_factory=dict)

@dataclass
class DependencyFingerprintConfig:
    capture_pip_freeze: bool = True
    capture_python_version: bool = True
    capture_platform: bool = True
    required: bool = False

@dataclass
class CommandPolicy:
    shell: bool = False
    timeout_seconds_default: int = 120
    allow_commands: Optional[List[str]] = None
    deny_commands: Optional[List[str]] = None

@dataclass
class DriftPolicy:
    on_python_version_mismatch: DriftPolicyMode = DriftPolicyMode.FAIL
    on_dependency_mismatch: DriftPolicyMode = DriftPolicyMode.WARN

@dataclass
class RuntimeProfile:
    profile_id: str
    language: str = "python"
    interpreter: Optional[InterpreterConfig] = None
    working_directory: str = "execution_workspace"
    env: EnvConfig = field(default_factory=EnvConfig)
    dependency_fingerprint: DependencyFingerprintConfig = field(default_factory=DependencyFingerprintConfig)
    command_policy: CommandPolicy = field(default_factory=CommandPolicy)
    drift_policy: DriftPolicy = field(default_factory=DriftPolicy)
    python_version: Optional[Dict[str, str]] = None # min, max keys
