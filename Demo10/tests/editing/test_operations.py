import unittest
from Demo10.editing.operations import EditEngine
from Demo10.editing.anchor_resolver import AnchorResolver
from Demo10.editing.models import EditInstruction, OperationType, AnchorType, EditStatus, EditConstraints

class TestEditEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EditEngine(AnchorResolver())
        self.sample_python = [
            "import os\n",
            "\n",
            "def foo():\n",
            "    pass\n"
        ]

    def test_ensure_import_idempotency(self):
        inst = EditInstruction(
            task_id="t1",
            file_path="test.py",
            operation=OperationType.ENSURE_IMPORT,
            anchor_type=AnchorType.IMPORT,
            anchor_value="import os",
            payload="import os"
        )
        # First run: should be NO_OP because it exists
        new_lines, res = self.engine.apply(self.sample_python, inst)
        self.assertEqual(res.status, EditStatus.NO_OP)
        self.assertEqual(len(new_lines), len(self.sample_python))

    def test_ensure_import_new(self):
        inst = EditInstruction(
            task_id="t1",
            file_path="test.py",
            operation=OperationType.ENSURE_IMPORT,
            anchor_type=AnchorType.IMPORT,
            anchor_value="import sys",
            payload="import sys"
        )
        new_lines, res = self.engine.apply(self.sample_python, inst)
        self.assertEqual(res.status, EditStatus.APPLIED)
        self.assertIn("import sys\n", new_lines)

    def test_replace_block(self):
        inst = EditInstruction(
            task_id="t1",
            file_path="test.py",
            operation=OperationType.REPLACE_BLOCK,
            anchor_type=AnchorType.FUNCTION,
            anchor_value="foo",
            payload="def foo():\n    print('hello')\n"
        )
        new_lines, res = self.engine.apply(self.sample_python, inst)
        self.assertEqual(res.status, EditStatus.APPLIED)
        self.assertIn("    print('hello')\n", new_lines)

    def test_delete_block(self):
        inst = EditInstruction(
            task_id="t1",
            file_path="test.py",
            operation=OperationType.DELETE_BLOCK,
            anchor_type=AnchorType.FUNCTION,
            anchor_value="foo",
            payload=""
        )
        new_lines, res = self.engine.apply(self.sample_python, inst)
        self.assertEqual(res.status, EditStatus.APPLIED)
        self.assertEqual(len(new_lines), 2) # import os and blank line

if __name__ == "__main__":
    unittest.main()
