import unittest
import shutil
import json
import os
from pathlib import Path
from services.run_ledger.models import RunState, RunMetadata, LedgerEvent, QueueDefinition, QueueState
from services.run_ledger.ledger import LedgerService
from services.run_ledger.queue_store import QueueStore
from services.run_ledger.recovery import RecoveryService, InterruptionCategory, RecoveryAction
from services.run_ledger.consistency import ConsistencyChecker

class TestDurability(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("./test_durability")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()

        self.ledger_service = LedgerService(self.test_dir)
        self.queue_store = QueueStore(self.test_dir)
        self.recovery_service = RecoveryService(self.test_dir, self.ledger_service)
        self.consistency_checker = ConsistencyChecker(self.test_dir, self.ledger_service)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_ledger_record_event(self):
        event = self.ledger_service.record_event(
            entity_type="run",
            entity_id="run_1",
            event_type="state_transition",
            new_state=RunState.EXECUTING.value,
            run_id="run_1"
        )
        self.assertEqual(event.seq_no, 1)
        self.assertTrue(self.test_dir.joinpath("runtime_data/run_ledger/events.jsonl").exists())

    def test_run_metadata_persistence(self):
        metadata = RunMetadata(
            run_id="run_1",
            spec_id="spec_1",
            queue_id="q_1",
            slot_id="0",
            state=RunState.CREATED,
            execution_mode="promote_on_success",
            runtime_profile="default",
            source_policy="promoted_head"
        )
        self.ledger_service.update_run_metadata(metadata)

        loaded = self.ledger_service.get_run_metadata("run_1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.run_id, "run_1")
        self.assertEqual(loaded.state, RunState.CREATED)

    def test_recovery_scan(self):
        # Create an interrupted run
        metadata = RunMetadata(
            run_id="run_interrupted",
            spec_id="spec_1",
            queue_id="q_1",
            slot_id="0",
            state=RunState.EXECUTING,
            execution_mode="promote_on_success",
            runtime_profile="default",
            source_policy="promoted_head",
            execution_workspace=str(self.test_dir / "workspace_1"),
            source_snapshot_manifest=str(self.test_dir / "manifest_1")
        )
        # Mock workspace and manifest
        (self.test_dir / "workspace_1").mkdir()
        (self.test_dir / "manifest_1").touch()

        self.ledger_service.update_run_metadata(metadata)

        plan = self.recovery_service.scan_for_interrupted_runs()
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].run_id, "run_interrupted")
        self.assertEqual(plan[0].category, InterruptionCategory.RESUMABLE_AT_PHASE_BOUNDARY)

    def test_consistency_check(self):
        # Run in ledger but workspace missing
        metadata = RunMetadata(
            run_id="run_missing_ws",
            spec_id="spec_1",
            queue_id="q_1",
            slot_id="0",
            state=RunState.EXECUTING,
            execution_mode="promote_on_success",
            runtime_profile="default",
            source_policy="promoted_head",
            execution_workspace=str(self.test_dir / "workspace_missing")
        )
        self.ledger_service.update_run_metadata(metadata)

        issues = self.consistency_checker.check_consistency()
        self.assertTrue(any(i.issue_type == "MISSING_RUN_ARTIFACT_DIR" for i in issues))

if __name__ == "__main__":
    unittest.main()
