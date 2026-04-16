from __future__ import annotations
import os
import re
from typing import Dict, List, Optional
from .models import RuntimeProfile, EnvInheritMode

class EnvironmentBuilder:
    def __init__(self):
        self.minimal_allowlist = ["PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOME"]

    def build(self, profile: RuntimeProfile) -> Dict[str, str]:
        env_config = profile.env
        base_env = {}

        if env_config.inherit_mode == EnvInheritMode.FULL:
            base_env = os.environ.copy()
        elif env_config.inherit_mode == EnvInheritMode.MINIMAL:
            allowlist = set(env_config.allowlist) | set(self.minimal_allowlist)
            for key in allowlist:
                if key in os.environ:
                    base_env[key] = os.environ[key]
        elif env_config.inherit_mode == EnvInheritMode.NONE:
            base_env = {}

        # Apply blocklist
        for key in env_config.blocklist:
            if key in base_env:
                del base_env[key]

        # Apply injections
        for key, value in env_config.inject.items():
            base_env[key] = value

        return base_env

class EnvironmentMasker:
    def __init__(self):
        self.secret_patterns = [
            re.compile(r"KEY", re.IGNORECASE),
            re.compile(r"TOKEN", re.IGNORECASE),
            re.compile(r"SECRET", re.IGNORECASE),
            re.compile(r"PASSWORD", re.IGNORECASE),
            re.compile(r"AUTH", re.IGNORECASE),
        ]

    def mask_env(self, env: Dict[str, str]) -> Dict[str, str]:
        masked = {}
        for key, value in env.items():
            if any(pattern.search(key) for pattern in self.secret_patterns):
                masked[key] = "***MASKED***"
            else:
                masked[key] = value
        return masked
