from __future__ import annotations

import cv2
import numpy as np


def detect_edges(
    normalized_grayscale: np.ndarray,
    canny_low: int,
    canny_high: int,
    aperture_size: int,
) -> np.ndarray:
    return cv2.Canny(
        normalized_grayscale,
        canny_low,
        canny_high,
        apertureSize=aperture_size,
        L2gradient=True,
    )
