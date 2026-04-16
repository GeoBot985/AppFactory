import unittest
import sys
import os

# Ensure Demo10 is in path and use the same import style as the services
sys.path.append(os.path.join(os.getcwd(), "Demo10"))

from services.compiler.compiler import DraftSpecCompiler
from services.draft_spec.models import DraftSpec, DraftTask, UncertaintyRecord, UncertaintySeverity, Certainty
from services.compiler.models import CompileStatus
from services.compiler.repair_models import RepairStatus

class TestCompileRepair(unittest.TestCase):
    def setUp(self):
        self.compiler = DraftSpecCompiler()

    def test_missing_title_repair(self):
        draft = DraftSpec(draft_id="d1", title="", tasks=[DraftTask(id="t1", type="RUN", path=".", summary="test")])
        plan, report, session, repaired_draft = self.compiler.compile_with_repair(draft)

        self.assertEqual(report.status, CompileStatus.SUCCESS)
        self.assertEqual(repaired_draft.title, "Untitled Draft")
        self.assertEqual(session.final_status, RepairStatus.SUCCESS)
        self.assertEqual(len(session.attempts), 1)
        self.assertEqual(session.attempts[0].errors_fixed, ["missing_title"])

    def test_duplicate_task_id_repair(self):
        tasks = [
            DraftTask(id="dup", type="RUN", path=".", summary="t1"),
            DraftTask(id="dup", type="RUN", path=".", summary="t2")
        ]
        draft = DraftSpec(draft_id="d2", title="Test Dup", tasks=tasks)
        plan, report, session, repaired_draft = self.compiler.compile_with_repair(draft)

        self.assertEqual(report.status, CompileStatus.SUCCESS)
        self.assertEqual(repaired_draft.tasks[1].id, "dup_dup_1")
        self.assertEqual(session.final_status, RepairStatus.SUCCESS)

    def test_unknown_task_type_repair(self):
        draft = DraftSpec(draft_id="d3", title="Test Type", tasks=[
            DraftTask(id="t1", type="make_file", path="foo.txt", summary="make foo")
        ])
        plan, report, session, repaired_draft = self.compiler.compile_with_repair(draft)

        self.assertEqual(report.status, CompileStatus.SUCCESS)
        self.assertEqual(repaired_draft.tasks[0].type, "generate_file")
        self.assertEqual(session.final_status, RepairStatus.SUCCESS)

    def test_invalid_dependency_repair(self):
        draft = DraftSpec(draft_id="d4", title="Test Dep", tasks=[
            DraftTask(id="t1", type="RUN", path=".", summary="t1", depends_on=["non_existent"])
        ])
        plan, report, session, repaired_draft = self.compiler.compile_with_repair(draft)

        self.assertEqual(report.status, CompileStatus.SUCCESS)
        self.assertEqual(repaired_draft.tasks[0].depends_on, [])
        self.assertEqual(session.final_status, RepairStatus.SUCCESS)

    def test_blocking_uncertainty_repair(self):
        uncertainties = [
            UncertaintyRecord(code="U1", message="Blocking!", severity=UncertaintySeverity.BLOCKING, field_path="uncertainties[0]")
        ]
        draft = DraftSpec(draft_id="d5", title="Test Uncertainty", tasks=[
            DraftTask(id="t1", type="RUN", path=".", summary="t1")
        ], uncertainties=uncertainties)

        plan, report, session, repaired_draft = self.compiler.compile_with_repair(draft)

        self.assertEqual(report.status, CompileStatus.SUCCESS)
        self.assertEqual(repaired_draft.uncertainties[0].severity, UncertaintySeverity.INFO)
        self.assertEqual(session.final_status, RepairStatus.SUCCESS)

    def test_max_attempts_reached(self):
        # To truly test max attempts, we need a repair that fixes something but the result still fails,
        # and it keeps happening.
        # For now, let's just verify it stops.
        draft = DraftSpec(draft_id="d6", title="Test Max", draft_spec_version=99)
        plan, report, session, repaired_draft = self.compiler.compile_with_repair(draft, max_attempts=2)

        self.assertEqual(report.status, CompileStatus.FAILED)
        self.assertEqual(session.final_status, RepairStatus.FAILED)
        self.assertTrue(len(session.attempts) <= 2)

if __name__ == '__main__':
    unittest.main()
