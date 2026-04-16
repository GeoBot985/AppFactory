from __future__ import annotations
import os
import sys
from typing import Dict, Optional, Any
from .models import (
    RuntimeProfile, InterpreterConfig, InterpreterMode,
    EnvConfig, EnvInheritMode, DependencyFingerprintConfig,
    CommandPolicy, DriftPolicy, DriftPolicyMode
)

class ProfileRegistry:
    def __init__(self):
        self._profiles: Dict[str, RuntimeProfile] = {}
        self._setup_default_profiles()

    def _setup_default_profiles(self):
        # Default Python profile using the current interpreter
        default_py = RuntimeProfile(
            profile_id="default",
            language="python",
            interpreter=InterpreterConfig(
                mode=InterpreterMode.PATH,
                value=sys.executable
            ),
            env=EnvConfig(inherit_mode=EnvInheritMode.MINIMAL),
            command_policy=CommandPolicy(shell=False, timeout_seconds_default=120)
        )
        self.register(default_py)

    def register(self, profile: RuntimeProfile):
        self._profiles[profile.profile_id] = profile

    def get_profile(self, profile_id: str) -> Optional[RuntimeProfile]:
        return self._profiles.get(profile_id)

    def list_profiles(self) -> Dict[str, RuntimeProfile]:
        return self._profiles.copy()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RuntimeProfile:
        # Helper to create profile from dictionary (e.g. from YAML)
        profile_id = data.get("profile_id", "unknown")

        interpreter = None
        if "interpreter" in data:
            int_data = data["interpreter"]
            interpreter = InterpreterConfig(
                mode=InterpreterMode(int_data["mode"]),
                value=int_data["value"]
            )

        env_data = data.get("env", {})
        env = EnvConfig(
            inherit_mode=EnvInheritMode(env_data.get("inherit_mode", "minimal")),
            allowlist=env_data.get("allowlist", ["PATH", "SYSTEMROOT", "TEMP", "TMP"]),
            blocklist=env_data.get("blocklist", []),
            inject=env_data.get("inject", {})
        )

        dep_data = data.get("dependency_fingerprint", {})
        dependency_fingerprint = DependencyFingerprintConfig(
            capture_pip_freeze=dep_data.get("capture_pip_freeze", True),
            capture_python_version=dep_data.get("capture_python_version", True),
            capture_platform=dep_data.get("capture_platform", True),
            required=dep_data.get("required", False)
        )

        cmd_data = data.get("command_policy", {})
        command_policy = CommandPolicy(
            shell=cmd_data.get("shell", False),
            timeout_seconds_default=cmd_data.get("timeout_seconds_default", 120),
            allow_commands=cmd_data.get("allow_commands"),
            deny_commands=cmd_data.get("deny_commands")
        )

        drift_data = data.get("drift_policy", {})
        drift_policy = DriftPolicy(
            on_python_version_mismatch=DriftPolicyMode(drift_data.get("on_python_version_mismatch", "fail")),
            on_dependency_mismatch=DriftPolicyMode(drift_data.get("on_dependency_mismatch", "warn"))
        )

        return RuntimeProfile(
            profile_id=profile_id,
            language=data.get("language", "python"),
            interpreter=interpreter,
            working_directory=data.get("working_directory", "execution_workspace"),
            env=env,
            dependency_fingerprint=dependency_fingerprint,
            command_policy=command_policy,
            drift_policy=drift_policy,
            python_version=data.get("python_version")
        )
