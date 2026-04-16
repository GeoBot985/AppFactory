import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from notes.models import NoteStore


class NoteStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.data_path = Path(self.temp_dir.name) / "notes.json"
        patcher = patch("notes.storage.DATA_PATH", self.data_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def test_add_note_increases_count(self):
        store = NoteStore()
        store.add_note("First", "Body")
        self.assertEqual(len(store.list_notes()), 1)

    def test_get_note_returns_correct_note(self):
        store = NoteStore()
        note = store.add_note("Title", "Body")
        loaded = store.get_note(note.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, "Title")
        self.assertEqual(loaded.content, "Body")

    def test_delete_note_removes_note(self):
        store = NoteStore()
        note = store.add_note("Delete", "Me")
        deleted = store.delete_note(note.id)
        self.assertTrue(deleted)
        self.assertIsNone(store.get_note(note.id))
        self.assertEqual(len(store.list_notes()), 0)

    def test_search_returns_correct_subset(self):
        store = NoteStore()
        store.add_note("Alpha", "First body")
        store.add_note("Beta", "Contains SearchWord")
        store.add_note("Gamma SearchWord", "Third body")
        results = store.search_notes("searchword")
        self.assertEqual([note.title for note in results], ["Beta", "Gamma SearchWord"])

    def test_search_is_case_insensitive(self):
        store = NoteStore()
        store.add_note("Case", "MiXeD")
        results = store.search_notes("mixed")
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
