import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from notes.cli import execute_command
from notes.models import NoteStore


class CliTests(unittest.TestCase):
    def _store(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_path = Path(self.temp_dir.name) / "notes.json"
        patcher = patch("notes.storage.DATA_PATH", data_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp_dir.cleanup)
        return NoteStore()

    def test_basic_cli_logic(self):
        store = self._store()
        add_result = execute_command(store, "add Shopping|Buy milk")
        self.assertIn("Added note 1", add_result)

        list_result = execute_command(store, "list")
        self.assertIn("[1] Shopping", list_result)

        view_result = execute_command(store, "view 1")
        self.assertIn("Buy milk", view_result)

        search_result = execute_command(store, "search milk")
        self.assertIn("[1] Shopping", search_result)

        delete_result = execute_command(store, "delete 1")
        self.assertEqual(delete_result, "Deleted note 1.")


if __name__ == "__main__":
    unittest.main()
