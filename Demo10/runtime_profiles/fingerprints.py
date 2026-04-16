from __future__ import annotations
import hashlib
import json
import platform
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
from .models import RuntimeProfile

class RuntimeFingerprintService:
    def capture(self, profile: RuntimeProfile, interpreter_path: str) -> Dict[str, str]:
        fingerprint = {}
        config = profile.dependency_fingerprint

        if config.capture_python_version:
            try:
                result = subprocess.run(
                    [interpreter_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                fingerprint["python_version"] = result.stdout.strip() or result.stderr.strip()
            except:
                fingerprint["python_version"] = "unknown"

        if config.capture_platform:
            fingerprint["platform"] = platform.platform()
            fingerprint["architecture"] = platform.machine()

        fingerprint["interpreter_path"] = interpreter_path

        return fingerprint

    def capture_pip_freeze(self, interpreter_path: str) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                [interpreter_path, "-m", "pip", "freeze"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return True, result.stdout
            return False, f"pip freeze failed with exit code {result.returncode}: {result.stderr}"
        except Exception as e:
            return False, f"pip freeze execution failed: {str(e)}"

    def compute_hash(self, fingerprint: Dict[str, str], pip_freeze: Optional[str] = None) -> str:
        data = fingerprint.copy()
        if pip_freeze:
            # Normalize pip freeze for hashing (sort lines)
            lines = sorted(pip_freeze.strip().splitlines())
            data["pip_freeze_normalized"] = "\n".join(lines)

        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
