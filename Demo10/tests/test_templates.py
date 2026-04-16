import unittest
import sys
from pathlib import Path

# Add Demo10 to path
sys.path.append(str(Path(__file__).parent.parent))

from templates.registry import TemplateRegistry
from templates.selector import TemplateSelector
from templates.fill import TemplateFiller
from templates.validator import TemplateValidator
from templates.models import MatchStrength

class TestTemplates(unittest.TestCase):
    def setUp(self):
        self.registry = TemplateRegistry()
        self.selector = TemplateSelector(self.registry)
        self.filler = TemplateFiller()
        self.validator = TemplateValidator()

    def test_exact_template_selection(self):
        result = self.selector.select_template("Build a small notes app with Tkinter and tests")
        self.assertEqual(result.template_id, "build_small_app")
        self.assertEqual(result.strength, MatchStrength.STRONG)
        self.assertEqual(result.inferred_parameters.get("ui_type"), "tkinter")
        self.assertEqual(result.inferred_parameters.get("app_name"), "notes")

    def test_template_fill_success(self):
        template = self.registry.get_template("build_small_app")
        params = {"app_name": "my_app", "ui_type": "cli"}
        fill = self.filler.fill(template, params)

        self.assertEqual(fill.template_id, "build_small_app")
        self.assertEqual(fill.parameters["app_name"], "my_app")
        self.assertEqual(fill.filled_spec["title"], "Build my_app")
        self.assertEqual(fill.filled_spec["intent"]["task_kind"], "build_app")

    def test_missing_required_parameter_validation(self):
        template = self.registry.get_template("add_tests")
        # Missing target_module and test_file
        is_valid, errors = self.validator.validate(template, {})
        self.assertFalse(is_valid)
        self.assertTrue(any("target_module" in e for e in errors))

    def test_contradictory_parameter_validation(self):
        template = self.registry.get_template("build_small_app")
        params = {"app_name": "cli_tool", "ui_type": "tkinter"}
        is_valid, errors = self.validator.validate(template, params)
        self.assertFalse(is_valid)
        self.assertTrue(any("contradictory" in e.lower() for e in errors))

    def test_no_template_match(self):
        result = self.selector.select_template("Refactor some code in random file")
        # Should be weak match or none depending on heuristics
        # My heuristic for "Refactor" was WEAK
        self.assertEqual(result.strength, MatchStrength.WEAK)
        self.assertEqual(result.template_id, "patch_existing_module")

if __name__ == "__main__":
    unittest.main()
