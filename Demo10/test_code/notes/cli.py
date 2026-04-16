from __future__ import annotations

from typing import Iterable, Optional

from notes.models import NoteStore


def execute_command(store: NoteStore, command_line: str) -> str:
    parts = command_line.strip().split(maxsplit=1)
    if not parts:
        return "No command provided."

    command = parts[0].lower()
    argument_text = parts[1] if len(parts) > 1 else ""

    if command == "add":
        title, content = _parse_title_content(argument_text)
        note = store.add_note(title, content)
        return f"Added note {note.id}: {note.title}"

    if command == "list":
        return format_note_list(store.list_notes())

    if command == "view":
        note_id = _parse_note_id(argument_text)
        if note_id is None:
            return "Usage: view <id>"
        note = store.get_note(note_id)
        if note is None:
            return f"Note {note_id} not found."
        return f"[{note.id}] {note.title}\n{note.content}"

    if command == "delete":
        note_id = _parse_note_id(argument_text)
        if note_id is None:
            return "Usage: delete <id>"
        deleted = store.delete_note(note_id)
        if not deleted:
            return f"Note {note_id} not found."
        return f"Deleted note {note_id}."

    if command == "search":
        keyword = argument_text.strip()
        if not keyword:
            return "Usage: search <keyword>"
        return format_note_list(store.search_notes(keyword))

    if command in {"quit", "exit"}:
        return "EXIT"

    return f"Unknown command: {command}"


def run_cli(store: Optional[NoteStore] = None) -> None:
    store = store or NoteStore()
    print("Simple Notes CLI. Commands: add, list, view <id>, delete <id>, search <keyword>, quit")
    while True:
        command_line = input("> ")
        result = execute_command(store, command_line)
        if result == "EXIT":
            print("Goodbye.")
            break
        print(result)


def format_note_list(notes: Iterable) -> str:
    rows = [f"[{note.id}] {note.title}" for note in notes]
    if not rows:
        return "No notes found."
    return "\n".join(rows)


def _parse_note_id(text: str) -> Optional[int]:
    value = text.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_title_content(text: str) -> tuple[str, str]:
    if "|" in text:
        title, content = text.split("|", 1)
        return title.strip(), content.strip()
    return text.strip(), ""
