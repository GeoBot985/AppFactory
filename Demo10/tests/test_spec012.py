import unittest
import sys
import os

# Add Demo10 to path
sys.path.append(os.path.join(os.getcwd(), "Demo10"))

from services.dsl_parser import DSLParser
from services.planner import Planner
from services.spec_parser_service import SpecParserService

class TestSpec012(unittest.TestCase):
    def setUp(self):
        self.parser = DSLParser()
        self.planner = Planner()
        self.spec_service = SpecParserService()

    def test_valid_dsl(self):
        spec = """
spec_version: 1
spec_id: test_spec
tasks:
  - id: t1
    type: create_file
    file: test.py
    content: "print('hello')"
  - id: t2
    type: run_command
    command: "python test.py"
    depends_on: [t1]
"""
        self.assertTrue(self.parser.is_dsl_spec(spec))
        data, validation = self.parser.parse(spec)
        self.assertTrue(validation.is_valid)

        ordered = self.planner.build_task_graph(data)
        self.assertEqual(len(ordered), 2)
        self.assertEqual(ordered[0]["id"], "t1")
        self.assertEqual(ordered[1]["id"], "t2")

    def test_cycle_detection(self):
        spec = """
spec_version: 1
spec_id: cycle
tasks:
  - id: t1
    type: run_command
    command: "ls"
    depends_on: [t2]
  - id: t2
    type: run_command
    command: "ls"
    depends_on: [t1]
"""
        data, validation = self.parser.parse(spec)
        self.assertTrue(validation.is_valid)
        with self.assertRaises(ValueError):
            self.planner.build_task_graph(data)

    def test_invalid_task_type(self):
        spec = """
spec_version: 1
spec_id: invalid
tasks:
  - id: t1
    type: unknown_type
    file: foo.py
"""
        data, validation = self.parser.parse(spec)
        self.assertFalse(validation.is_valid)
        self.assertEqual(validation.errors[0]["field"], "tasks[0].type")

    def test_spec_service_integration(self):
        spec = """
spec_version: 1
spec_id: integration
tasks:
  - id: b
    type: run_command
    command: "echo b"
    depends_on: [a]
  - id: a
    type: run_command
    command: "echo a"
"""
        tasks, _ = self.spec_service.parse(spec)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].id, "a")
        self.assertEqual(tasks[1].id, "b")

if __name__ == "__main__":
    unittest.main()
