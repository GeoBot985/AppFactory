from __future__ import annotations

import pytest

from conftest import load_diagram


def test_diagram1_regression_metrics() -> None:
    data = load_diagram("Diagram1")
    verification = data.get("verification", {})

    edge_overlap_score = verification.get("edge_overlap_score")
    pixel_difference_score = verification.get("pixel_difference_score")

    assert edge_overlap_score is not None, "Diagram1 missing verification.edge_overlap_score"
    assert pixel_difference_score is not None, "Diagram1 missing verification.pixel_difference_score"
    assert edge_overlap_score >= 0.60, f"Diagram1 edge_overlap_score={edge_overlap_score}, expected >= 0.60"
    assert pixel_difference_score <= 0.08, f"Diagram1 pixel_difference_score={pixel_difference_score}, expected <= 0.08"


def test_diagram2_regression_metrics_todo() -> None:
    pytest.skip("TODO: add Diagram2 regression thresholds once stable baseline metrics are confirmed")
