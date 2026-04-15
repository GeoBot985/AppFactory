from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def write_image(output_dir: Path, filename: str, image: np.ndarray) -> None:
    ensure_output_dir(output_dir)
    cv2.imwrite(str(output_dir / filename), image)


def write_text(output_dir: Path, filename: str, text: str) -> None:
    ensure_output_dir(output_dir)
    (output_dir / filename).write_text(text, encoding="utf-8")


def write_json(output_dir: Path, filename: str, payload: dict) -> None:
    ensure_output_dir(output_dir)
    (output_dir / filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")
