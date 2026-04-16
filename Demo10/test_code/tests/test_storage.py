import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from notes.models import Note
from notes.storage import load_notes, save_notes


class StorageTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "notes.json"
            with patch("notes.storage.DATA_PATH", temp_path):
                save_notes([Note(id=1, title="A", content="B")])
                loaded = load_notes()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title, "A")
        self.assertEqual(loaded[0].content, "B")

    def test_empty_load_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "notes.json"
            with patch("notes.storage.DATA_PATH", temp_path):
                self.assertEqual(load_notes(), [])
                temp_path.write_text("", encoding="utf-8")
                self.assertEqual(load_notes(), [])


if __name__ == "__main__":
    unittest.main()
