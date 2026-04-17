import pytest
import json
from pathlib import Path
from datetime import datetime
from diagnostics.signature import generate_signature
from diagnostics.classifier import classify_failure
from diagnostics.patterns import PatternManager
from telemetry.models import TelemetryEvent

def test_signature_determinism():
    sig1 = generate_signature("INVALID_PATH", "read_file", "test.txt")
    sig2 = generate_signature("INVALID_PATH", "read_file", "test.txt")
    sig3 = generate_signature("FILE_NOT_FOUND", "read_file", "test.txt")

    assert sig1.signature_id == sig2.signature_id
    assert sig1.signature_id != sig3.signature_id
    assert sig1.context_hash == sig2.context_hash

def test_signature_normalization():
    sig1 = generate_signature("invalid_path", "READ_FILE", "/path/to/test.txt")
    sig2 = generate_signature("INVALID_PATH", "read_file", "test.txt")

    assert sig1.signature_id == sig2.signature_id

def test_classification():
    event = TelemetryEvent(
        event_type="step_failed",
        payload={"error_code": "INVALID_PATH", "step_type": "read_file", "is_terminal": True}
    )
    rc = classify_failure(event)
    assert rc.category == "execution_error"
    assert rc.subcategory == "invalid_path"

def test_retry_exhausted_classification():
    # Terminal retryable failure after attempts
    event = TelemetryEvent(
        event_type="step_failed",
        payload={
            "error_code": "COMMAND_FAILED",
            "step_type": "run_command",
            "is_terminal": True,
            "classification": "retryable",
            "attempt_index": 3
        }
    )
    rc = classify_failure(event)
    assert rc.category == "transient_error"
    assert rc.subcategory == "exhausted"

def test_pattern_grouping(tmp_path):
    mgr = PatternManager(tmp_path)

    event1 = TelemetryEvent(
        event_type="step_failed",
        payload={"run_id": "run_1", "error_code": "INVALID_PATH", "step_type": "read_file", "target": "missing.txt", "is_terminal": True}
    )
    event2 = TelemetryEvent(
        event_type="step_failed",
        payload={"run_id": "run_2", "error_code": "INVALID_PATH", "step_type": "read_file", "target": "missing.txt", "is_terminal": True}
    )

    mgr.process_failure(event1)
    mgr.process_failure(event2)

    patterns = mgr.get_patterns()
    assert len(patterns) == 1
    assert patterns[0].occurrences == 2
    assert "run_1" in patterns[0].affected_runs
    assert "run_2" in patterns[0].affected_runs

def test_impact_scoring(tmp_path):
    mgr = PatternManager(tmp_path)

    event = TelemetryEvent(
        event_type="step_failed",
        payload={"run_id": "run_1", "error_code": "INVALID_PATH", "step_type": "read_file", "is_terminal": True}
    )

    mgr.process_failure(event)
    p1 = mgr.get_patterns()[0]
    score1 = p1.impact_score

    mgr.process_failure(event)
    p2 = mgr.get_patterns()[0]
    score2 = p2.impact_score

    assert score2 > score1
    # Check impact score formula: 1.0 * occurrences + 5.0
    assert score1 == 6.0
    assert score2 == 7.0

def test_alert_triggering(tmp_path):
    mgr = PatternManager(tmp_path)

    # Trigger new root cause alert
    event = TelemetryEvent(
        event_type="step_failed",
        payload={"run_id": "run_1", "error_code": "INVALID_PATH", "step_type": "read_file", "is_terminal": True}
    )
    mgr.process_failure(event)

    alerts_dir = tmp_path / "runtime_data" / "telemetry" / "alerts"
    assert alerts_dir.exists()

    date_str = datetime.now().strftime("%Y-%m-%d")
    alert_file = alerts_dir / f"{date_str}.jsonl"
    assert alert_file.exists()

    with open(alert_file, "r") as f:
        alert_data = [json.loads(line) for line in f]

    assert any(a["rule"] == "new_failure_root_cause" for a in alert_data)

def test_standalone_storage(tmp_path):
    mgr = PatternManager(tmp_path)
    event = TelemetryEvent(
        event_type="step_failed",
        payload={"run_id": "run_1", "error_code": "INVALID_PATH", "step_type": "read_file", "is_terminal": True}
    )
    mgr.process_failure(event)

    assert (tmp_path / "runtime_data" / "diagnostics" / "signatures.json").exists()
    assert (tmp_path / "runtime_data" / "diagnostics" / "root_causes.json").exists()
