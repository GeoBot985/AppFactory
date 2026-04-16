import unittest
from pathlib import Path
import tempfile
import os
import json
from Demo10.verification.checks import VerificationExecutor
from Demo10.verification.models import CheckStatus, Severity

class TestVerificationChecks(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.test_dir.name)
        self.executor = VerificationExecutor(self.project_root)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_file_exists(self):
        file_path = "test.txt"
        (self.project_root / file_path).write_text("hello")

        check_def = {"type": "file_exists", "path": file_path}
        result = self.executor.execute_check(check_def)
        self.assertEqual(result.status, CheckStatus.PASS)

        check_def_fail = {"type": "file_exists", "path": "missing.txt"}
        result_fail = self.executor.execute_check(check_def_fail)
        self.assertEqual(result_fail.status, CheckStatus.FAIL)

    def test_contains_text(self):
        file_path = "test.txt"
        (self.project_root / file_path).write_text("hello world")

        check_def = {"type": "contains_text", "path": file_path, "text": "hello"}
        result = self.executor.execute_check(check_def)
        self.assertEqual(result.status, CheckStatus.PASS)

        check_def_fail = {"type": "contains_text", "path": file_path, "text": "missing"}
        result_fail = self.executor.execute_check(check_def_fail)
        self.assertEqual(result_fail.status, CheckStatus.FAIL)

    def test_symbol_exists(self):
        file_path = "test.py"
        content = "def my_func():\n    pass\n\nclass MyClass:\n    pass"
        (self.project_root / file_path).write_text(content)

        # Function check
        check_def_fn = {"type": "symbol_exists", "path": file_path, "symbol_type": "function", "symbol_name": "my_func"}
        result_fn = self.executor.execute_check(check_def_fn)
        self.assertEqual(result_fn.status, CheckStatus.PASS)

        # Class check
        check_def_cl = {"type": "symbol_exists", "path": file_path, "symbol_type": "class", "symbol_name": "MyClass"}
        result_cl = self.executor.execute_check(check_def_cl)
        self.assertEqual(result_cl.status, CheckStatus.PASS)

        # Fail check
        check_def_fail = {"type": "symbol_exists", "path": file_path, "symbol_type": "function", "symbol_name": "missing_fn"}
        result_fail = self.executor.execute_check(check_def_fail)
        self.assertEqual(result_fail.status, CheckStatus.FAIL)

    def test_import_exists_exactly_once(self):
        file_path = "test.py"
        content = "import os\nimport sys\nimport os"
        (self.project_root / file_path).write_text(content)

        # Should fail if expected 1 but found 2
        check_def = {"type": "import_exists", "path": file_path, "import": "import os"}
        result = self.executor.execute_check(check_def)
        self.assertEqual(result.status, CheckStatus.FAIL)
        self.assertIn("found 2 times, expected 1", result.message)

        # Should pass if expected 2 and found 2
        check_def_2 = {"type": "import_exists", "path": file_path, "import": "import os", "expected_count": 2}
        result_2 = self.executor.execute_check(check_def_2)
        self.assertEqual(result_2.status, CheckStatus.PASS)

    def test_json_value_equals(self):
        file_path = "data.json"
        data = {"status": "ok", "metadata": {"version": "1.0"}}
        (self.project_root / file_path).write_text(json.dumps(data))

        # Shallow path
        check_def = {"type": "json_value_equals", "path": file_path, "json_path": "status", "expected": "ok"}
        result = self.executor.execute_check(check_def)
        self.assertEqual(result.status, CheckStatus.PASS)

        # Dotted path
        check_def_dotted = {"type": "json_value_equals", "path": file_path, "json_path": "metadata.version", "expected": "1.0"}
        result_dotted = self.executor.execute_check(check_def_dotted)
        self.assertEqual(result_dotted.status, CheckStatus.PASS)

if __name__ == "__main__":
    unittest.main()
