from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from notes.models import NoteStore


class NotesApp:
    def __init__(self, store: NoteStore | None = None) -> None:
        self.store = store or NoteStore()
        self.root = tk.Tk()
        self.root.title("Notes")
        self.root.geometry("900x520")

        self.search_var = tk.StringVar()
        self.title_var = tk.StringVar()

        self._build_layout()
        self._refresh_notes()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        top_bar = ttk.Frame(self.root, padding=8)
        top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        top_bar.columnconfigure(1, weight=1)

        ttk.Label(top_bar, text="Search").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(top_bar, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        search_entry.bind("<KeyRelease>", lambda _event: self._refresh_notes())
        ttk.Button(top_bar, text="Clear", command=self._clear_search).grid(row=0, column=2, sticky="e")

        list_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.notes_list = tk.Listbox(list_frame)
        self.notes_list.grid(row=0, column=0, sticky="nsew")
        self.notes_list.bind("<<ListboxSelect>>", lambda _event: self._show_selected_note())

        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.notes_list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.notes_list.configure(yscrollcommand=list_scroll.set)

        detail_frame = ttk.Frame(self.root, padding=(0, 0, 8, 8))
        detail_frame.grid(row=1, column=1, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(3, weight=1)

        ttk.Label(detail_frame, text="Title").grid(row=0, column=0, sticky="w")
        ttk.Entry(detail_frame, textvariable=self.title_var).grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(detail_frame, text="Content").grid(row=2, column=0, sticky="w")
        self.content_text = tk.Text(detail_frame, wrap="word")
        self.content_text.grid(row=3, column=0, sticky="nsew")

        button_row = ttk.Frame(detail_frame)
        button_row.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(button_row, text="Add Note", command=self._add_note).pack(side="left")
        ttk.Button(button_row, text="Delete Note", command=self._delete_selected_note).pack(side="left", padx=(8, 0))

    def _notes_for_display(self):
        keyword = self.search_var.get().strip()
        if keyword:
            return self.store.search_notes(keyword)
        return self.store.list_notes()

    def _refresh_notes(self) -> None:
        self.notes_list.delete(0, tk.END)
        self._display_notes = self._notes_for_display()
        for note in self._display_notes:
            self.notes_list.insert(tk.END, f"[{note.id}] {note.title}")
        if self._display_notes:
            self.notes_list.selection_set(0)
            self._show_selected_note()
        else:
            self.title_var.set("")
            self.content_text.delete("1.0", tk.END)

    def _show_selected_note(self) -> None:
        selection = self.notes_list.curselection()
        if not selection:
            return
        note = self._display_notes[selection[0]]
        self.title_var.set(note.title)
        self.content_text.delete("1.0", tk.END)
        self.content_text.insert("1.0", note.content)

    def _add_note(self) -> None:
        title = self.title_var.get().strip()
        content = self.content_text.get("1.0", tk.END).rstrip("\n")
        if not title:
            messagebox.showerror("Missing title", "Please enter a title.")
            return
        self.store.add_note(title, content)
        self.title_var.set("")
        self.content_text.delete("1.0", tk.END)
        self._refresh_notes()

    def _delete_selected_note(self) -> None:
        selection = self.notes_list.curselection()
        if not selection:
            messagebox.showerror("No selection", "Select a note to delete.")
            return
        note = self._display_notes[selection[0]]
        self.store.delete_note(note.id)
        self._refresh_notes()

    def _clear_search(self) -> None:
        self.search_var.set("")
        self._refresh_notes()

    def run(self) -> None:
        self.root.mainloop()
