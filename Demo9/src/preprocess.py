from __future__ import annotations

import cv2
import numpy as np


def normalize_image(
    grayscale: np.ndarray,
    blur_kernel_size: int,
    clahe_clip_limit: float,
    clahe_grid_size: int,
    adaptive_block_size: int,
    adaptive_c: int,
) -> dict[str, np.ndarray]:
    blurred = cv2.GaussianBlur(grayscale, (blur_kernel_size, blur_kernel_size), 0)
    clahe = cv2.createCLAHE(
        clipLimit=clahe_clip_limit,
        tileGridSize=(clahe_grid_size, clahe_grid_size),
    )
    normalized = clahe.apply(blurred)
    binary = cv2.adaptiveThreshold(
        normalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        adaptive_block_size,
        adaptive_c,
    )
    return {
        "normalized_grayscale": normalized,
        "binary": binary,
    }
