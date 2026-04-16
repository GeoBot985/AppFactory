from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, List

if TYPE_CHECKING:
    from notes.models import Note


DATA_PATH = Path("data") / "notes.json"


def save_notes(note_list: Iterable[Note]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": note.id,
            "title": note.title,
            "content": note.content,
        }
        for note in note_list
    ]
    DATA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_notes() -> List[Note]:
    if not DATA_PATH.exists():
        return []

    raw_text = DATA_PATH.read_text(encoding="utf-8").strip()
    if not raw_text:
        return []

    data = json.loads(raw_text)
    from notes.models import Note

    return [
        Note(
            id=int(item["id"]),
            title=str(item["title"]),
            content=str(item["content"]),
        )
        for item in data
    ]
