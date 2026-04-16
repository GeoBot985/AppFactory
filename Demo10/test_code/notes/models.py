from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from notes.storage import load_notes, save_notes


@dataclass
class Note:
    id: int
    title: str
    content: str


class NoteStore:
    def __init__(self) -> None:
        self._notes: List[Note] = load_notes()
        self._next_id = self._compute_next_id()

    def _compute_next_id(self) -> int:
        if not self._notes:
            return 1
        return max(note.id for note in self._notes) + 1

    def _save(self) -> None:
        save_notes(self._notes)

    def add_note(self, title: str, content: str) -> Note:
        note = Note(id=self._next_id, title=title, content=content)
        self._notes.append(note)
        self._next_id += 1
        self._save()
        return note

    def list_notes(self) -> List[Note]:
        return list(self._notes)

    def get_note(self, note_id: int) -> Optional[Note]:
        for note in self._notes:
            if note.id == note_id:
                return note
        return None

    def delete_note(self, note_id: int) -> bool:
        for index, note in enumerate(self._notes):
            if note.id == note_id:
                del self._notes[index]
                self._save()
                return True
        return False

    def search_notes(self, keyword: str) -> List[Note]:
        query = keyword.lower()
        return [
            note
            for note in self._notes
            if query in note.title.lower() or query in note.content.lower()
        ]
