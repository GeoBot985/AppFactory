from __future__ import annotations
import unittest
from pathlib import Path
from Demo10.services.preview.diff_builder import DiffBuilder
from Demo10.services.preview.risk_analyzer import RiskAnalyzer
from Demo10.services.preview.impact_model import ImpactPreview, ImpactSummary, FileDiff, RiskLevel

class TestPreviewSystem(unittest.TestCase):
    def test_diff_builder_modify(self):
        # Create a temp file
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            f_path = tmp_path / "test.py"
            f_path.write_text("line1\nline2\n", encoding="utf-8")

            builder = DiffBuilder(tmp_path)
            diff = builder.build_file_diff("test.py", "modify", "line1\nline3\n")

            self.assertEqual(diff.path, "test.py")
            self.assertEqual(diff.change_type, "modify")
            self.assertIn("-line2", diff.diff_preview)
            self.assertIn("+line3", diff.diff_preview)

    def test_risk_analyzer_low(self):
        preview = ImpactPreview(preview_id="p1", compiled_plan_id="c1", workspace_hash="h1")
        preview.summary = ImpactSummary(total_files=1, files_modified=1)
        preview.file_diffs = [FileDiff(path="util.py", change_type="modify")]

        analyzer = RiskAnalyzer()
        analyzer.analyze(preview)

        self.assertEqual(preview.risk_level, RiskLevel.LOW)
        self.assertEqual(len(preview.risk_reasons), 0)

    def test_risk_analyzer_high_critical(self):
        preview = ImpactPreview(preview_id="p1", compiled_plan_id="c1", workspace_hash="h1")
        preview.summary = ImpactSummary(total_files=1, files_modified=1)
        preview.file_diffs = [FileDiff(path="main.py", change_type="modify")]

        analyzer = RiskAnalyzer()
        analyzer.analyze(preview)

        self.assertEqual(preview.risk_level, RiskLevel.HIGH)
        self.assertIn("Modifying critical entrypoint", preview.risk_reasons[0])

    def test_risk_analyzer_high_delete(self):
        preview = ImpactPreview(preview_id="p1", compiled_plan_id="c1", workspace_hash="h1")
        preview.summary = ImpactSummary(total_files=1, files_deleted=1)
        preview.file_diffs = [FileDiff(path="old.py", change_type="delete_file")]

        analyzer = RiskAnalyzer()
        analyzer.analyze(preview)

        self.assertEqual(preview.risk_level, RiskLevel.HIGH)
        self.assertIn("Deleting", preview.risk_reasons[0])

if __name__ == "__main__":
    unittest.main()
