from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def demo9_root() -> Path:
    return project_root() / "Demo9"


def outputs_dir() -> Path:
    return demo9_root() / "outputs"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_diagram(diagram_id: str) -> dict:
    path = outputs_dir() / diagram_id / "diagram.json"
    assert path.exists(), f"Missing output JSON: {path}"
    return load_json(path)


def load_metrics(diagram_id: str) -> dict:
    path = outputs_dir() / diagram_id / "metrics.json"
    assert path.exists(), f"Missing metrics JSON: {path}"
    return load_json(path)


def route_pairs(data: dict) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in data.get("routes", []):
        src = route.get("src_node_id")
        dst = route.get("dst_node_id")
        if not src or not dst:
            continue
        pairs.add(tuple(sorted((src, dst))))
    return pairs


@pytest.fixture(scope="session", autouse=True)
def ensure_demo9_outputs() -> None:
    required = [
        outputs_dir() / "Diagram1" / "diagram.json",
        outputs_dir() / "Diagram2" / "diagram.json",
    ]
    if all(path.exists() for path in required):
        return
    subprocess.run([sys.executable, "Demo9/app.py"], cwd=project_root(), check=True)
