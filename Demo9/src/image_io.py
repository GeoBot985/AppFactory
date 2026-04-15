from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_image(image_path: Path) -> tuple[np.ndarray, np.ndarray]:
    color = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if color is None or color.size == 0:
        raise ValueError(f"Unable to load image: {image_path}")

    grayscale = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    return color, grayscale
