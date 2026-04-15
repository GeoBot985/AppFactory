from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from services.file_service import FileService, TreeNode
from services.log_service import LogService
from services.bundle_service import BundleBuilder, WorkingSetBundle
from services.bundle_edit_service import BundleEditRun, BundleOutputParser, BundleValidator, CandidateBundle
from services.index_service import ArchitectureIndex, IndexBuilder
from services.ollama_service import OllamaRunSnapshot, OllamaService
from services.process_service import ProcessResult, ProcessService
from services.prompt_service import PromptBuilder, PromptRequest, BundleEditPromptBuilder
from services.queue_service import QueueService
from services.restore_service import RestoreResult, RestoreService
from services.run_state_service import RunStateService
from services.selection_service import FileSelector, SelectionResult
from services.task_service import Task, TaskType, TaskStatus, TaskResult
from services.file_ops_service import FileOpsService
from services.spec_parser_service import SpecParserService
from services.task_executor_service import TaskExecutorService
from services.validation_service import ValidationService
from services.audit_log_service import AuditLogService


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, _event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#2d2d30",
            foreground="#d4d4d4",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=5,
            pady=3
        )
        label.pack(ipadx=1)

    def hide_tip(self, _event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


class AgentWorkbenchApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("AgentWorkbench")
        self.root.geometry("1600x950")
        self.root.minsize(1200, 760)

        self.file_service = FileService()
        self.process_service = ProcessService()
        self.ollama_service = OllamaService()
        self.index_builder = IndexBuilder()
        self.file_selector = FileSelector()
        self.bundle_builder = BundleBuilder()
        self.queue_service = QueueService()
        self.restore_service = RestoreService()
        self.log_service = LogService()
        self.prompt_builder = PromptBuilder()
        self.bundle_prompt_builder = BundleEditPromptBuilder()
        self.bundle_parser = BundleOutputParser()
        self.bundle_validator = BundleValidator()
        self.spec_parser = SpecParserService()
        self.validation_service = ValidationService()
        self.audit_log_service = AuditLogService(Path.cwd())
        self.run_state_service = RunStateService()
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.current_folder: Path | None = None
        self.selected_file: Path | None = None
        self.tree_paths: dict[str, Path] = {}
        self.tree_build_thread: threading.Thread | None = None
        self.model_load_thread: threading.Thread | None = None
        self.llm_run_thread: threading.Thread | None = None
        self.bundle_edit_thread: threading.Thread | None = None
        self.index_build_thread: threading.Thread | None = None
        self.selection_thread: threading.Thread | None = None
        self.queue_thread: threading.Thread | None = None
        self.restore_thread: threading.Thread | None = None
        self.llm_run_active = False
        self.bundle_edit_active = False
        self.index_build_active = False
        self.selection_active = False
        self.queue_active = False
        self.restore_active = False
        self.pending_restore_type: str = "none"  # "none", "bundle", "candidate"
        self.llm_run_started_at = 0.0
        self.llm_chunk_count = 0
        self.llm_output_chars = 0
        self.active_run_snapshot: OllamaRunSnapshot | None = None

        self.folder_var = tk.StringVar(value="No folder selected")
        self.model_var = tk.StringVar(value="")
        self.selected_file_var = tk.StringVar(value="No file selected")
        self.status_folder_var = tk.StringVar(value="Folder: none")
        self.status_file_var = tk.StringVar(value="File: none")
        self.status_model_var = tk.StringVar(value="Model: unavailable")
        self.status_action_var = tk.StringVar(value="LLM: idle")
        self.command_var = tk.StringVar()
        self.active_slot_var = tk.StringVar(value="Active Slot: none")
        self.status_selected_slot_var = tk.StringVar(value="Selected Slot: 1")
        self.selected_slot_index = 0

        self.spec_queue = self.queue_service.create_state()
        self.run_state_service.set_queue_state(self.spec_queue)
        self.queue_slot_widgets: list[tk.Text] = []
        self.queue_slot_status_vars: list[tk.StringVar] = [tk.StringVar(value="empty") for _ in range(10)]

        self._configure_style()
        self._build_layout()
        self.root.after(100, self._process_ui_queue)
        self.root.after(150, self.refresh_models)

    def run(self) -> None:
        self.root.mainloop()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        bg = "#1e1e1e"
        panel = "#252526"
        border = "#3c3c3c"
        fg = "#d4d4d4"
        accent = "#0e639c"
        self.root.configure(bg=bg)

        style.configure(".", background=bg, foreground=fg, fieldbackground=panel)
        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel, relief="flat")
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("Panel.TLabel", background=panel, foreground=fg)
        style.configure("TButton", background=accent, foreground="white", padding=6)
        style.map("TButton", background=[("active", "#1177bb")])
        style.configure("Treeview", background=panel, foreground=fg, fieldbackground=panel, bordercolor=border)
        style.configure("Treeview.Heading", background="#2d2d30", foreground=fg)
        style.configure("TCombobox", fieldbackground=panel, background=panel, foreground=fg)
        style.map("TCombobox", fieldbackground=[("readonly", panel)], foreground=[("readonly", fg)])

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=8)
        container.pack(fill="both", expand=True)
        container.rowconfigure(1, weight=1)
        container.columnconfigure(0, weight=1)

        self._build_top_section(container)
        self._build_main_section(container)
        self._build_bottom_section(container)
        self._build_status_bar(container)
        self._refresh_prompt_preview()
        self._refresh_response_view()
        self._refresh_index_view()
        self._refresh_selection_view()
        self._refresh_bundle_view()
        self._refresh_candidate_view()
        self._refresh_queue_view()
        self._refresh_restore_view()
        self._refresh_restore_preview()
        self._refresh_pipeline_view()

    def _build_top_section(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        top.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        top.columnconfigure(1, weight=1)
        top.columnconfigure(5, weight=1)
        top.rowconfigure(1, weight=1)

        ttk.Label(top, text="Project", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.folder_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 8))
        open_btn = ttk.Button(top, text="Open Folder", command=self.open_folder)
        open_btn.grid(row=0, column=3, padx=(0, 8))
        Tooltip(open_btn, "Select the project folder to work on. All indexing and file operations use this root.")

        refresh_tree_btn = ttk.Button(top, text="Refresh Tree", command=self.refresh_tree)
        refresh_tree_btn.grid(row=0, column=4, padx=(0, 16))
        Tooltip(refresh_tree_btn, "Reload the project file tree from disk.")

        ttk.Label(top, text="Model", style="Panel.TLabel").grid(row=0, column=5, sticky="w")
        self.model_combo = ttk.Combobox(top, textvariable=self.model_var, state="readonly", values=[])
        self.model_combo.grid(row=0, column=6, sticky="ew", padx=(8, 8))
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_selected)
        Tooltip(self.model_combo, "Select the local Ollama model used for LLM operations.")

        refresh_models_btn = ttk.Button(top, text="Refresh Models", command=self.refresh_models)
        refresh_models_btn.grid(row=0, column=7)
        Tooltip(refresh_models_btn, "Query the local Ollama instance for available models.")

        ttk.Label(top, text="Spec Editor", style="Panel.TLabel").grid(row=1, column=0, sticky="nw", pady=(10, 0))
        spec_frame = ttk.Frame(top, style="Panel.TFrame")
        spec_frame.grid(row=1, column=1, columnspan=5, sticky="nsew", pady=(10, 0))
        spec_frame.rowconfigure(0, weight=1)
        spec_frame.columnconfigure(0, weight=1)

        self.spec_text = tk.Text(
            spec_frame,
            wrap="word",
            height=8,
            bg="#1b1b1c",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        spec_scroll = ttk.Scrollbar(spec_frame, orient="vertical", command=self.spec_text.yview)
        self.spec_text.configure(yscrollcommand=spec_scroll.set)
        self.spec_text.grid(row=0, column=0, sticky="nsew")
        spec_scroll.grid(row=0, column=1, sticky="ns")
        self.spec_text.bind("<KeyRelease>", self._on_spec_changed)
        queue_frame = ttk.Frame(top, style="Panel.TFrame")
        queue_frame.grid(row=1, column=6, columnspan=2, sticky="nsew", pady=(10, 0), padx=(10, 0))
        queue_frame.rowconfigure(1, weight=1)
        queue_frame.columnconfigure(0, weight=1)
        ttk.Label(queue_frame, text="Execution Queue", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.queue_status_label = ttk.Label(queue_frame, textvariable=self.active_slot_var, style="Panel.TLabel")
        self.queue_status_label.grid(row=0, column=1, sticky="e")
        ttk.Label(queue_frame, text="Queue Mode: AUTO-RESTORE", style="Panel.TLabel", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="e", padx=(0, 150))
        queue_slots_frame = ttk.Frame(queue_frame, style="Panel.TFrame")
        queue_slots_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        for idx in range(10):
            queue_slots_frame.rowconfigure(idx, weight=1)
        queue_slots_frame.columnconfigure(2, weight=1)
        for idx in range(10):
            slot_label = ttk.Label(queue_slots_frame, text=f"{idx + 1}.", style="Panel.TLabel")
            slot_label.grid(row=idx, column=0, sticky="nw", padx=(0, 4))
            status_label = ttk.Label(queue_slots_frame, textvariable=self.queue_slot_status_vars[idx], style="Panel.TLabel")
            status_label.grid(row=idx, column=1, sticky="nw", padx=(0, 6))
            slot_text = tk.Text(
                queue_slots_frame,
                height=2,
                wrap="word",
                bg="#1b1b1c",
                fg="#d4d4d4",
                insertbackground="#d4d4d4",
                font=("Consolas", 9),
                relief="flat",
                state="disabled",
            )
            slot_text.grid(row=idx, column=2, sticky="ew", pady=(0, 4))
            self.queue_slot_widgets.append(slot_text)

            slot_label.bind("<Button-1>", lambda e, i=idx: self.select_slot(i))
            status_label.bind("<Button-1>", lambda e, i=idx: self.select_slot(i))
            slot_text.bind("<Button-1>", lambda e, i=idx: self.select_slot(i))
        action_row = ttk.Frame(top, style="Panel.TFrame")
        action_row.grid(row=2, column=6, columnspan=2, sticky="e", pady=(8, 0))
        self.run_llm_button = ttk.Button(action_row, text="Run LLM", command=self.run_llm)
        self.run_llm_button.pack(side="left", padx=(0, 8))
        Tooltip(self.run_llm_button, "Send the current spec to the selected model for analysis or response (no file changes).")

        self.edit_bundle_button = ttk.Button(action_row, text="Edit Bundle with LLM", command=self.run_bundle_edit)
        self.edit_bundle_button.pack(side="left", padx=(0, 8))
        Tooltip(self.edit_bundle_button, "Request the model to propose edits for files in the current bundle based on the spec.")

        self.build_index_button = ttk.Button(action_row, text="Build Index", command=self.build_index)
        self.build_index_button.pack(side="left", padx=(0, 8))
        Tooltip(self.build_index_button, "Scan the project and build a structural index used for deterministic selection.")

        self.select_files_button = ttk.Button(action_row, text="Select Files", command=self.select_files)
        self.select_files_button.pack(side="left", padx=(0, 8))
        Tooltip(self.select_files_button, "Select relevant files for the current spec using deterministic rules and the architecture index.")

        self.restore_bundle_button = ttk.Button(action_row, text="Restore Bundle", command=self.restore_bundle)
        self.restore_bundle_button.pack(side="left", padx=(0, 8))
        Tooltip(self.restore_bundle_button, "Write the current bundle to the project folder. Preview changes before confirming.")

        self.restore_candidate_button = ttk.Button(action_row, text="Restore Candidate", command=self.restore_candidate)
        self.restore_candidate_button.pack(side="left", padx=(0, 8))
        Tooltip(self.restore_candidate_button, "Write the candidate bundle (model output) to the project folder. Preview changes before confirming.")

        self.start_queue_button = ttk.Button(action_row, text="Start Queue", command=self.start_queue)
        self.start_queue_button.pack(side="left", padx=(0, 8))
        Tooltip(self.start_queue_button, "Execute queued specs sequentially (selection → bundle → optional edit → restore).")

        self.stop_queue_button = ttk.Button(action_row, text="Stop Queue", command=self.stop_queue)
        self.stop_queue_button.pack(side="left", padx=(0, 8))
        self.stop_queue_button.state(["disabled"])
        Tooltip(self.stop_queue_button, "Stop execution after the current slot finishes or reaches a safe boundary.")

        self.submit_spec_button = ttk.Button(action_row, text="Submit to Selected Slot", command=self.submit_spec)
        self.submit_spec_button.pack(side="left", padx=(0, 8))
        Tooltip(self.submit_spec_button, "Copy the current spec into the selected queue slot.")

        load_to_editor_btn = ttk.Button(action_row, text="Load Slot to Editor", command=self.load_slot_to_editor)
        load_to_editor_btn.pack(side="left", padx=(0, 8))
        Tooltip(load_to_editor_btn, "Load the spec and state from the selected queue slot back into the editor.")

        clear_slot_btn = ttk.Button(action_row, text="Clear Slot", command=self.clear_slot)
        clear_slot_btn.pack(side="left")
        Tooltip(clear_slot_btn, "Remove the spec and all associated results from the selected queue slot.")

    def _build_main_section(self, parent: ttk.Frame) -> None:
        main = ttk.PanedWindow(parent, orient="horizontal")
        main.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        left = ttk.Frame(main, style="Panel.TFrame", padding=8)
        center = ttk.Frame(main, style="Panel.TFrame", padding=8)
        right = ttk.Frame(main, style="Panel.TFrame", padding=8)

        for panel in (left, center):
            panel.rowconfigure(1, weight=1)
            panel.columnconfigure(0, weight=1)

        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=0)  # Active Pipeline
        right.rowconfigure(3, weight=1)  # Activity Log

        main.add(left, weight=1)
        main.add(center, weight=3)
        main.add(right, weight=2)

        ttk.Label(left, text="Project Tree", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        tree_frame = ttk.Frame(left, style="Panel.TFrame")
        tree_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_frame, show="tree")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_selected)
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")

        ttk.Label(center, text="Workspace Views", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        notebook = ttk.Notebook(center)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        viewer_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        prompt_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        response_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        index_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        selection_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        bundle_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        candidate_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        restore_preview_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        restore_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        slot_detail_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        notebook.add(viewer_frame, text="File Viewer")
        notebook.add(prompt_frame, text="Prompt Preview")
        notebook.add(response_frame, text="Latest Response")
        notebook.add(index_frame, text="Architecture Index")
        notebook.add(selection_frame, text="File Selection")
        notebook.add(bundle_frame, text="Bundle Preview")
        notebook.add(candidate_frame, text="Candidate Bundle")
        notebook.add(restore_preview_frame, text="Restore Preview")
        notebook.add(restore_frame, text="Restore Result")
        notebook.add(slot_detail_frame, text="Slot Detail")
        self.notebook = notebook

        for frame in (viewer_frame, prompt_frame, response_frame, index_frame, selection_frame, bundle_frame, candidate_frame, restore_preview_frame, restore_frame, slot_detail_frame):
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)

        self.viewer = tk.Text(
            viewer_frame,
            wrap="none",
            bg="#1b1b1c",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        viewer_y = ttk.Scrollbar(viewer_frame, orient="vertical", command=self.viewer.yview)
        viewer_x = ttk.Scrollbar(viewer_frame, orient="horizontal", command=self.viewer.xview)
        self.viewer.configure(yscrollcommand=viewer_y.set, xscrollcommand=viewer_x.set)
        self.viewer.grid(row=0, column=0, sticky="nsew")
        viewer_y.grid(row=0, column=1, sticky="ns")
        viewer_x.grid(row=1, column=0, sticky="ew")
        self.viewer.insert("1.0", "Select a text file to preview it here.")
        self.viewer.configure(state="disabled")

        self.prompt_preview = tk.Text(
            prompt_frame,
            wrap="word",
            bg="#1b1b1c",
            fg="#4ec9b0",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        prompt_scroll = ttk.Scrollbar(prompt_frame, orient="vertical", command=self.prompt_preview.yview)
        self.prompt_preview.configure(yscrollcommand=prompt_scroll.set)
        self.prompt_preview.grid(row=0, column=0, sticky="nsew")
        prompt_scroll.grid(row=0, column=1, sticky="ns")
        self.prompt_preview.configure(state="disabled")

        self.response_view = tk.Text(
            response_frame,
            wrap="word",
            bg="#1b1b1c",
            fg="#ce9178",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        response_scroll = ttk.Scrollbar(response_frame, orient="vertical", command=self.response_view.yview)
        self.response_view.configure(yscrollcommand=response_scroll.set)
        self.response_view.grid(row=0, column=0, sticky="nsew")
        response_scroll.grid(row=0, column=1, sticky="ns")
        self.response_view.configure(state="disabled")

        self.index_view = tk.Text(
            index_frame,
            wrap="none",
            bg="#1b1b1c",
            fg="#dcdcaa",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        index_y = ttk.Scrollbar(index_frame, orient="vertical", command=self.index_view.yview)
        index_x = ttk.Scrollbar(index_frame, orient="horizontal", command=self.index_view.xview)
        self.index_view.configure(yscrollcommand=index_y.set, xscrollcommand=index_x.set)
        self.index_view.grid(row=0, column=0, sticky="nsew")
        index_y.grid(row=0, column=1, sticky="ns")
        index_x.grid(row=1, column=0, sticky="ew")
        self.index_view.configure(state="disabled")

        self.selection_view = tk.Text(
            selection_frame,
            wrap="none",
            bg="#1b1b1c",
            fg="#c586c0",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        selection_y = ttk.Scrollbar(selection_frame, orient="vertical", command=self.selection_view.yview)
        selection_x = ttk.Scrollbar(selection_frame, orient="horizontal", command=self.selection_view.xview)
        self.selection_view.configure(yscrollcommand=selection_y.set, xscrollcommand=selection_x.set)
        self.selection_view.grid(row=0, column=0, sticky="nsew")
        selection_y.grid(row=0, column=1, sticky="ns")
        selection_x.grid(row=1, column=0, sticky="ew")
        self.selection_view.configure(state="disabled")

        self.bundle_view = tk.Text(
            bundle_frame,
            wrap="none",
            bg="#1b1b1c",
            fg="#9cdcfe",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        bundle_y = ttk.Scrollbar(bundle_frame, orient="vertical", command=self.bundle_view.yview)
        bundle_x = ttk.Scrollbar(bundle_frame, orient="horizontal", command=self.bundle_view.xview)
        self.bundle_view.configure(yscrollcommand=bundle_y.set, xscrollcommand=bundle_x.set)
        self.bundle_view.grid(row=0, column=0, sticky="nsew")
        bundle_y.grid(row=0, column=1, sticky="ns")
        bundle_x.grid(row=1, column=0, sticky="ew")
        self.bundle_view.configure(state="disabled")

        self.candidate_view = tk.Text(
            candidate_frame,
            wrap="none",
            bg="#1b1b1c",
            fg="#9cdcfe",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        candidate_y = ttk.Scrollbar(candidate_frame, orient="vertical", command=self.candidate_view.yview)
        candidate_x = ttk.Scrollbar(candidate_frame, orient="horizontal", command=self.candidate_view.xview)
        self.candidate_view.configure(yscrollcommand=candidate_y.set, xscrollcommand=candidate_x.set)
        self.candidate_view.grid(row=0, column=0, sticky="nsew")
        candidate_y.grid(row=0, column=1, sticky="ns")
        candidate_x.grid(row=1, column=0, sticky="ew")
        self.candidate_view.configure(state="disabled")

        # Restore Preview Tab
        restore_preview_frame.rowconfigure(0, weight=1)
        restore_preview_frame.rowconfigure(1, weight=0)

        self.restore_preview_view = tk.Text(
            restore_preview_frame,
            wrap="none",
            bg="#1b1b1c",
            fg="#d7ba7d",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        preview_y = ttk.Scrollbar(restore_preview_frame, orient="vertical", command=self.restore_preview_view.yview)
        preview_x = ttk.Scrollbar(restore_preview_frame, orient="horizontal", command=self.restore_preview_view.xview)
        self.restore_preview_view.configure(yscrollcommand=preview_y.set, xscrollcommand=preview_x.set)
        self.restore_preview_view.grid(row=0, column=0, sticky="nsew")
        preview_y.grid(row=0, column=1, sticky="ns")
        preview_x.grid(row=2, column=0, sticky="ew")
        self.restore_preview_view.configure(state="disabled")

        self.restore_preview_view.tag_configure("new", foreground="#6a9955")
        self.restore_preview_view.tag_configure("modified", foreground="#d7ba7d")
        self.restore_preview_view.tag_configure("unchanged", foreground="#808080")
        self.restore_preview_view.tag_configure("skipped", foreground="#f44747")
        self.restore_preview_view.tag_configure("header", foreground="#569cd6", font=("Consolas", 10, "bold"))

        confirm_frame = ttk.Frame(restore_preview_frame, style="Panel.TFrame")
        confirm_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.confirm_restore_button = ttk.Button(confirm_frame, text="Confirm Restore", command=self.confirm_restore, state="disabled")
        self.confirm_restore_button.pack(side="right")

        self.restore_view = tk.Text(
            restore_frame,
            wrap="none",
            bg="#1b1b1c",
            fg="#d7ba7d",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        restore_y = ttk.Scrollbar(restore_frame, orient="vertical", command=self.restore_view.yview)
        restore_x = ttk.Scrollbar(restore_frame, orient="horizontal", command=self.restore_view.xview)
        self.restore_view.configure(yscrollcommand=restore_y.set, xscrollcommand=restore_x.set)
        self.restore_view.grid(row=0, column=0, sticky="nsew")
        restore_y.grid(row=0, column=1, sticky="ns")
        restore_x.grid(row=1, column=0, sticky="ew")
        self.restore_view.configure(state="disabled")

        # Slot Detail Tab
        slot_detail_frame.rowconfigure(0, weight=0)
        slot_detail_frame.rowconfigure(1, weight=1)

        self.slot_detail_header = ttk.Frame(slot_detail_frame, style="Panel.TFrame")
        self.slot_detail_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.slot_detail_title_var = tk.StringVar(value="Slot: none")
        ttk.Label(self.slot_detail_header, textvariable=self.slot_detail_title_var, font=("Segoe UI", 11, "bold"), style="Panel.TLabel").pack(side="left", padx=(0, 20))

        self.slot_detail_status_var = tk.StringVar(value="Status: -")
        ttk.Label(self.slot_detail_header, textvariable=self.slot_detail_status_var, style="Panel.TLabel").pack(side="left", padx=(0, 20))

        load_spec_btn = ttk.Button(self.slot_detail_header, text="Load Spec to Editor", command=self.load_slot_to_editor)
        load_spec_btn.pack(side="right")
        Tooltip(load_spec_btn, "Load the spec from this slot back into the editor for refinement.")

        self.slot_detail_view = tk.Text(
            slot_detail_frame,
            wrap="word",
            bg="#1b1b1c",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        slot_detail_scroll = ttk.Scrollbar(slot_detail_frame, orient="vertical", command=self.slot_detail_view.yview)
        self.slot_detail_view.configure(yscrollcommand=slot_detail_scroll.set)
        self.slot_detail_view.grid(row=1, column=0, sticky="nsew")
        slot_detail_scroll.grid(row=1, column=1, sticky="ns")
        self.slot_detail_view.configure(state="disabled")

        self.slot_detail_view.tag_configure("header", foreground="#569cd6", font=("Consolas", 11, "bold"))
        self.slot_detail_view.tag_configure("label", foreground="#9cdcfe")
        self.slot_detail_view.tag_configure("value", foreground="#d4d4d4")
        self.slot_detail_view.tag_configure("error", foreground="#f44747")
        self.slot_detail_view.tag_configure("success", foreground="#6a9955")
        self.slot_detail_view.tag_configure("dim", foreground="#808080")

        # Active Pipeline
        ttk.Label(right, text="Active Pipeline", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        pipeline_frame = ttk.Frame(right, style="Panel.TFrame")
        pipeline_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 16))
        pipeline_frame.rowconfigure(0, weight=1)
        pipeline_frame.columnconfigure(0, weight=1)

        self.pipeline_view = tk.Text(
            pipeline_frame,
            wrap="word",
            height=10,
            bg="#1b1b1c",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            font=("Consolas", 10, "bold"),
            relief="flat",
        )
        self.pipeline_view.grid(row=0, column=0, sticky="nsew")
        self.pipeline_view.configure(state="disabled")
        self.pipeline_view.tag_configure("pending", foreground="#808080")
        self.pipeline_view.tag_configure("running", foreground="#569cd6")
        self.pipeline_view.tag_configure("completed", foreground="#6a9955")
        self.pipeline_view.tag_configure("failed", foreground="#f44747")
        self.pipeline_view.tag_configure("skipped", foreground="#d7ba7d")

        ttk.Label(right, text="Activity Log", style="Panel.TLabel").grid(row=2, column=0, sticky="w")
        log_frame = ttk.Frame(right, style="Panel.TFrame")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            bg="#1b1b1c",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set, state="disabled")
        self.log_text.tag_configure("system", foreground="#9cdcfe")
        self.log_text.tag_configure("model", foreground="#ce9178")
        self.log_text.tag_configure("separator", foreground="#6a9955")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")

    def _build_bottom_section(self, parent: ttk.Frame) -> None:
        bottom = ttk.Frame(parent, style="Panel.TFrame", padding=8)
        bottom.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(1, weight=1)

        ttk.Label(bottom, text="PowerShell", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(bottom, textvariable=self.command_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        entry.bind("<Return>", lambda _event: self.run_command())
        ps_run_btn = ttk.Button(bottom, text="Run", command=self.run_command)
        ps_run_btn.grid(row=0, column=2)
        Tooltip(ps_run_btn, "Execute the entered PowerShell command in the project root.")

        output_frame = ttk.Frame(bottom, style="Panel.TFrame")
        output_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        self.output_text = tk.Text(
            output_frame,
            wrap="word",
            height=10,
            bg="#111214",
            fg="#ce9178",
            insertbackground="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        output_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=output_scroll.set, state="disabled")
        self.output_text.grid(row=0, column=0, sticky="nsew")
        output_scroll.grid(row=0, column=1, sticky="ns")

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        status = ttk.Frame(parent, style="Panel.TFrame", padding=(8, 6))
        status.grid(row=3, column=0, sticky="ew")
        for idx in range(6):
            status.columnconfigure(idx, weight=1)

        ttk.Label(status, textvariable=self.status_folder_var, style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status, textvariable=self.status_file_var, style="Panel.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(status, textvariable=self.status_model_var, style="Panel.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(status, textvariable=self.status_selected_slot_var, style="Panel.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Label(status, textvariable=self.active_slot_var, style="Panel.TLabel").grid(row=0, column=4, sticky="w")
        ttk.Label(status, textvariable=self.status_action_var, style="Panel.TLabel").grid(row=0, column=5, sticky="w")

    def log_event(self, message: str) -> None:
        entry = self.log_service.create_entry(message)
        line = f"[{entry.timestamp}] {entry.message}\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, ("system",))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def append_model_output(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text, ("model",))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def append_log_separator(self, title: str) -> None:
        entry = self.log_service.create_entry(title)
        line = f"\n[{entry.timestamp}] ===== {title} =====\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, ("separator",))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_status_action(self, message: str) -> None:
        self.status_action_var.set(f"State: {message}")

    def _on_spec_changed(self, _event: object) -> None:
        self._refresh_prompt_preview()

    def _current_project_folder_text(self) -> str:
        return str(self.current_folder) if self.current_folder else "not selected"

    def _build_prompt_from_ui(self) -> str:
        request = PromptRequest(
            model_name=self.model_var.get().strip() or "not selected",
            project_folder=self._current_project_folder_text(),
            spec_text=self.spec_text.get("1.0", "end-1c"),
        )
        return self.prompt_builder.build(request)

    def _set_text_widget_content(self, widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def _refresh_prompt_preview(self) -> None:
        try:
            prompt = self._build_prompt_from_ui()
        except Exception as exc:
            prompt = f"Prompt preview unavailable: {exc}"
        self._set_text_widget_content(self.prompt_preview, prompt)

    def _refresh_response_view(self) -> None:
        run = self.run_state_service.latest_run
        if run.status == "idle" and not run.final_response_text:
            content = "No captured response yet."
        else:
            content = (
                f"Status: {run.status}\n"
                f"Model: {run.model_name or 'not selected'}\n"
                f"Project folder: {run.project_folder}\n"
                f"Started: {run.started_at or '-'}\n"
                f"Completed: {run.completed_at or '-'}\n"
                f"Failure: {run.failure_reason or '-'}\n\n"
                "[FINAL RESPONSE]\n"
                f"{run.final_response_text or '(no response captured)'}"
            )
        self._set_text_widget_content(self.response_view, content)

    def _refresh_index_view(self) -> None:
        index_state = self.run_state_service.index_state
        architecture_index = index_state.latest_index
        if architecture_index is None:
            if index_state.status == "failed":
                content = f"Index build failed.\nReason: {index_state.failure_reason or '-'}"
            elif index_state.status == "building":
                content = "Architecture index build in progress..."
            else:
                content = "No architecture index built yet."
        else:
            content = architecture_index.to_preview_text()
        self._set_text_widget_content(self.index_view, content)

    def _refresh_selection_view(self) -> None:
        selection_state = self.run_state_service.selection_state
        selection_result = selection_state.latest_selection
        if selection_result is None:
            if selection_state.status == "failed":
                content = f"File selection failed.\nReason: {selection_state.failure_reason or '-'}"
            elif selection_state.status == "selecting":
                content = "Deterministic file selection in progress..."
            else:
                content = "No file selection result yet."
        else:
            content = selection_result.to_preview_text()
        self._set_text_widget_content(self.selection_view, content)

    def _refresh_bundle_view(self) -> None:
        bundle_state = self.run_state_service.bundle_state
        bundle = bundle_state.latest_bundle
        if bundle is None:
            if bundle_state.status == "failed":
                content = f"Bundle build failed.\nReason: {bundle_state.failure_reason or '-'}"
            elif bundle_state.status == "building":
                content = "Bundle build in progress..."
            else:
                content = "No working-set bundle built yet."
        else:
            content = self.restore_service.preview_bundle(bundle) + "\n\n" + bundle.to_preview_text()
        self._set_text_widget_content(self.bundle_view, content)

    def _refresh_candidate_view(self) -> None:
        edit_state = self.run_state_service.bundle_edit_state
        run = edit_state.latest_edit_run
        if run is None:
            if edit_state.status == "failed":
                content = f"Bundle edit failed.\nReason: {edit_state.failure_reason or '-'}"
            elif edit_state.status == "running":
                content = "Bundle edit in progress..."
            else:
                content = "No bundle edit run yet."
        else:
            lines = [
                f"Run ID: {run.run_id}",
                f"Status: {run.status}",
                f"Validation: {run.validation_status}",
                f"Restore: {run.restore_status}",
                f"Started: {run.started_at}",
                f"Completed: {run.completed_at}",
            ]
            if run.validation_errors:
                lines.append("\n[VALIDATION ERRORS]")
                lines.extend(f"- {err}" for err in run.validation_errors)

            if run.candidate_bundle:
                lines.append("\n[CANDIDATE FILES]")
                for f in run.candidate_bundle.files:
                    lines.append(f"--- {f.relative_path} ({f.selection_kind}) ---")
                    lines.append(f.file_content)
                    lines.append("-" * 40)
            elif run.raw_model_output:
                lines.append("\n[RAW MODEL OUTPUT (PARSING FAILED)]")
                lines.append(run.raw_model_output)

            content = "\n".join(lines)
        self._set_text_widget_content(self.candidate_view, content)

    def _refresh_restore_view(self) -> None:
        restore_state = self.run_state_service.restore_state
        restore = restore_state.latest_restore
        if restore is None:
            if restore_state.status == "failed":
                content = f"Restore failed.\nReason: {restore_state.failure_reason or '-'}"
            elif restore_state.status == "restoring":
                content = "Restore in progress..."
            else:
                content = "No restore result yet."
        else:
            content = restore.to_preview_text()
        self._set_text_widget_content(self.restore_view, content)

    def _refresh_restore_preview(self) -> None:
        preview = self.run_state_service.restore_state.latest_preview
        if preview is None:
            content = "No restore preview available. Trigger a restore to see changes here."
            self._set_text_widget_content(self.restore_preview_view, content)
            self.confirm_restore_button.state(["disabled"])
            return

        self.restore_preview_view.configure(state="normal")
        self.restore_preview_view.delete("1.0", "end")

        self.restore_preview_view.insert("end", f"Project: {preview.project_root}\n", "header")
        self.restore_preview_view.insert("end", f"Generated: {preview.generated_at}\n", "header")
        self.restore_preview_view.insert("end", f"Summary: total={preview.total_files}, new={preview.new_count}, modified={preview.modified_count}, unchanged={preview.unchanged_count}, skipped={preview.skipped_count}\n\n", "header")

        self.restore_preview_view.insert("end", f"{'PATH':<60} | {'CHANGE':<12} | {'SIZE (OLD -> NEW)':<20} | {'LINES':<10}\n", "header")
        self.restore_preview_view.insert("end", "-" * 110 + "\n", "header")

        for f in preview.files:
            size_str = f"{f.old_size} -> {f.new_size}"
            line = f"{f.relative_path[:60]:<60} | {f.change_type:<12} | {size_str:<20} | {f.new_line_count:<10}\n"
            self.restore_preview_view.insert("end", line, f.change_type)

        self.restore_preview_view.configure(state="disabled")
        self.confirm_restore_button.state(["!disabled"])

    def _refresh_pipeline_view(self) -> None:
        queue_state = self.spec_queue
        active_idx = queue_state.active_slot_index

        self.pipeline_view.configure(state="normal")
        self.pipeline_view.delete("1.0", "end")

        if active_idx < 0:
            if queue_state.queue_status == "idle":
                self.pipeline_view.insert("end", "\n  [ Queue Idle ]", "pending")
            else:
                self.pipeline_view.insert("end", "\n  [ No Active Slot ]", "pending")
            self.pipeline_view.configure(state="disabled")
            return

        slot = queue_state.queue_slots[active_idx]
        self.pipeline_view.insert("end", f" Slot {active_idx + 1} Pipeline:\n\n", "completed")

        for stage in slot.pipeline_stages:
            status_sym = "[ ]"
            if stage.status == "running":
                status_sym = "[→]"
            elif stage.status == "completed":
                status_sym = "[✔]"
            elif stage.status == "failed":
                status_sym = "[✘]"
            elif stage.status == "skipped":
                status_sym = "[-]"

            self.pipeline_view.insert("end", f"  {status_sym} {stage.name}\n", stage.status)
            if stage.last_message:
                self.pipeline_view.insert("end", f"      > {stage.last_message}\n", "pending")

        self.pipeline_view.configure(state="disabled")

    def _refresh_slot_detail_view(self) -> None:
        idx = self.selected_slot_index
        slot = self.spec_queue.queue_slots[idx]

        self.slot_detail_title_var.set(f"Slot: {idx + 1}")
        status_text = f"Status: {slot.status}"
        if self.spec_queue.active_slot_index == idx:
            status_text += " (ACTIVE)"
        self.slot_detail_status_var.set(status_text)

        self.slot_detail_view.configure(state="normal")
        self.slot_detail_view.delete("1.0", "end")

        def add_section(title: str):
            self.slot_detail_view.insert("end", f"\n=== {title} ===\n", "header")

        def add_field(label: str, value: str, tag: str = "value"):
            self.slot_detail_view.insert("end", f"{label}: ", "label")
            self.slot_detail_view.insert("end", f"{value}\n", tag)

        if slot.status == "empty":
            self.slot_detail_view.insert("end", "\n[ Slot is empty ]\n", "dim")
            self.slot_detail_view.configure(state="disabled")
            return

        # 1. Spec
        add_section("SPEC")
        if slot.spec_text.strip():
            self.slot_detail_view.insert("end", slot.spec_text + "\n")
        else:
            self.slot_detail_view.insert("end", "(no spec text)\n", "dim")

        # 2. Selection
        add_section("SELECTION")
        if slot.selection_result:
            res = slot.selection_result
            add_field("Total Selected", str(res.total_selected_count))
            add_field("Primary", str(res.selected_primary_count))
            add_field("Context", str(res.selected_context_count))
            if res.unmatched_terms:
                add_field("Unmatched Terms", ", ".join(res.unmatched_terms), "error")

            self.slot_detail_view.insert("end", "\nSelected Files:\n", "label")
            for file_path in res.primary_files:
                self.slot_detail_view.insert("end", f"  [P] {file_path}\n", "value")
            for file_path in res.context_files:
                self.slot_detail_view.insert("end", f"  [C] {file_path}\n", "dim")
        else:
            self.slot_detail_view.insert("end", "No selection result available.\n", "dim")

        # 3. Bundle
        add_section("BUNDLE")
        if slot.bundle_result:
            b = slot.bundle_result
            add_field("Total Files", str(b.total_files))
            add_field("Characters", f"{b.total_chars:,}")

            self.slot_detail_view.insert("end", "\nBundle Files:\n", "label")
            for f in b.files:
                self.slot_detail_view.insert("end", f"  {f.relative_path} ({f.selection_kind})\n", "value")
        else:
            self.slot_detail_view.insert("end", "No bundle result available.\n", "dim")

        # 4. Restore
        add_section("RESTORE")
        if slot.restore_result:
            r = slot.restore_result
            add_field("Status", r.status, "success" if r.status == "completed" else "error")
            add_field("Written", str(r.written_file_count))
            add_field("Skipped", str(r.skipped_file_count))
            add_field("Failed", str(r.failed_file_count), "error" if r.failed_file_count > 0 else "value")

            if r.failures:
                self.slot_detail_view.insert("end", "\nFailures:\n", "error")
                for f, msg in r.failures.items():
                    self.slot_detail_view.insert("end", f"  {f}: {msg}\n", "error")
        else:
            self.slot_detail_view.insert("end", "No restore result available.\n", "dim")

        # 5. LLM / Edit Result
        add_section("LLM EDIT RESULT")
        if slot.llm_edit_run:
            run = slot.llm_edit_run
            add_field("Run ID", run.run_id)
            add_field("Status", run.status)
            add_field("Validation", run.validation_status, "success" if run.validation_status == "passed" else "error")
            add_field("Restore", run.restore_status)

            if run.validation_errors:
                self.slot_detail_view.insert("end", "\nValidation Errors:\n", "error")
                for err in run.validation_errors:
                    self.slot_detail_view.insert("end", f"  - {err}\n", "error")
        else:
            self.slot_detail_view.insert("end", "No LLM edit result available.\n", "dim")

        # 6. Failure Info
        if slot.status == "failed" or slot.failure_reason:
            add_section("FAILURE INFO")
            add_field("Status", slot.status, "error")
            add_field("Reason", slot.failure_reason or "unknown", "error")

        self.slot_detail_view.configure(state="disabled")

    def select_slot(self, index: int) -> None:
        self.selected_slot_index = index
        self.status_selected_slot_var.set(f"Selected Slot: {index + 1}")
        self.log_event(f"Selected queue slot: {index + 1}")
        self._refresh_queue_view()
        self._refresh_slot_detail_view()

    def _refresh_queue_view(self) -> None:
        queue_state = self.spec_queue
        active = queue_state.active_slot_index + 1 if queue_state.active_slot_index >= 0 else "none"
        self.active_slot_var.set(f"Active Slot: {active} [{queue_state.queue_status}]")
        for idx, (slot, widget) in enumerate(zip(queue_state.queue_slots, self.queue_slot_widgets)):
            self.queue_slot_status_vars[idx].set(slot.status)
            widget.configure(state="normal")
            current = widget.get("1.0", "end-1c")
            if current != slot.spec_text:
                widget.delete("1.0", "end")
                widget.insert("1.0", slot.spec_text)

            if slot.status == "running":
                bg = "#263238"
            elif slot.status == "completed":
                bg = "#1f3b2d"
            elif slot.status == "failed":
                bg = "#4b1f1f"
            elif slot.status == "stopped":
                bg = "#4a3b1f"
            elif slot.status == "ready":
                bg = "#2d2d30"
            else:
                bg = "#1b1b1c"

            highlight = "#ffffff" if idx == self.selected_slot_index else "#3c3c3c"
            widget.configure(bg=bg, fg="#d4d4d4", insertbackground="#d4d4d4", highlightbackground=highlight, highlightthickness=1)
            widget.configure(state="disabled")
        self._refresh_slot_detail_view()

    def _capture_queue_specs(self) -> list[str]:
        return [widget.get("1.0", "end-1c") for widget in self.queue_slot_widgets]

    def open_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=str(self.current_folder or Path.cwd()))
        if not folder:
            return
        self.current_folder = Path(folder)
        self.folder_var.set(str(self.current_folder))
        self.status_folder_var.set(f"Folder: {self.current_folder}")
        self.log_event(f"Project folder selected: {self.current_folder}")
        self._refresh_prompt_preview()
        self.refresh_tree()

    def refresh_tree(self) -> None:
        if not self.current_folder:
            self.log_event("Refresh tree skipped: no project folder selected.")
            return
        self.log_event(f"Refreshing tree for {self.current_folder}")
        self.tree.delete(*self.tree.get_children())
        self.tree_paths.clear()
        thread = threading.Thread(target=self._load_tree_worker, args=(self.current_folder,), daemon=True)
        self.tree_build_thread = thread
        thread.start()

    def _load_tree_worker(self, folder: Path) -> None:
        try:
            tree_data = self.file_service.build_tree(folder)
            self.ui_queue.put(("tree_loaded", tree_data))
        except Exception as exc:
            self.ui_queue.put(("tree_error", str(exc)))

    def _render_tree(self, node: TreeNode) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree_paths.clear()
        root_id = self.tree.insert("", "end", text=node.name, open=True)
        self.tree_paths[root_id] = node.path
        self._insert_tree_children(root_id, node)

    def _insert_tree_children(self, parent_id: str, node: TreeNode) -> None:
        for child in node.children:
            child_id = self.tree.insert(parent_id, "end", text=child.name, open=False)
            self.tree_paths[child_id] = child.path
            if child.is_dir:
                self._insert_tree_children(child_id, child)

    def _on_tree_selected(self, _event: object) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        path = self.tree_paths.get(selected[0])
        if not path or path.is_dir():
            return
        self.selected_file = path
        self.selected_file_var.set(str(path))
        self.status_file_var.set(f"File: {path.name}")
        success, content = self.file_service.read_text_file(path)
        self.viewer.configure(state="normal")
        self.viewer.delete("1.0", "end")
        self.viewer.insert("1.0", content)
        self.viewer.configure(state="disabled")
        if success:
            self.log_event(f"Loaded file preview: {path}")
        else:
            self.log_event(f"Preview fallback for {path}: {content}")

    def refresh_models(self) -> None:
        self.log_event("Refreshing Ollama model list")
        thread = threading.Thread(target=self._load_models_worker, daemon=True)
        self.model_load_thread = thread
        thread.start()

    def _load_models_worker(self) -> None:
        try:
            models = self.ollama_service.list_models()
            self.ui_queue.put(("models_loaded", models))
        except Exception as exc:
            self.ui_queue.put(("models_error", str(exc)))

    def _on_model_selected(self, _event: object) -> None:
        model = self.model_var.get().strip() or "none"
        self.status_model_var.set(f"Model: {model}")
        self.log_event(f"Model selected: {model}")
        self._refresh_prompt_preview()

    def submit_spec(self) -> None:
        spec = self.spec_text.get("1.0", "end-1c")
        idx = self.selected_slot_index
        slot = self.spec_queue.queue_slots[idx]
        slot.spec_text = spec
        slot.status = "ready" if spec.strip() else "empty"
        self.log_event(f"Spec submitted to slot {idx + 1}")
        self._refresh_queue_view()

    def load_slot_to_editor(self) -> None:
        idx = self.selected_slot_index
        slot = self.spec_queue.queue_slots[idx]
        self.spec_text.delete("1.0", "end")
        self.spec_text.insert("1.0", slot.spec_text)
        self.log_event(f"Loaded slot {idx + 1} into editor")
        self._refresh_prompt_preview()

    def clear_slot(self) -> None:
        idx = self.selected_slot_index
        slot = self.spec_queue.queue_slots[idx]
        slot.spec_text = ""
        slot.status = "empty"
        self.log_event(f"Cleared slot {idx + 1}")
        self._refresh_queue_view()

    def run_command(self) -> None:
        command = self.command_var.get().strip()
        if not command:
            self.log_event("PowerShell run skipped: no command entered.")
            return
        self.log_event(f"Running PowerShell command: {command}")
        self.process_service.run_powershell(
            command=command,
            on_complete=lambda result: self.ui_queue.put(("command_done", result)),
            on_error=lambda exc: self.ui_queue.put(("command_error", str(exc))),
        )

    def build_index(self) -> None:
        if self.index_build_active:
            self.log_event("Build Index blocked: an index build is already in progress.")
            return
        if not self.current_folder:
            self.log_event("Build Index blocked: no project folder selected.")
            self.set_status_action("index failed")
            return

        self.index_build_active = True
        self.build_index_button.state(["disabled"])
        self.run_state_service.begin_index_build()
        self._refresh_index_view()
        self.log_event("index build started")
        self.log_event(f"project root used: {self.current_folder}")
        self.set_status_action("index building")
        thread = threading.Thread(target=self._build_index_worker, args=(self.current_folder,), daemon=True)
        self.index_build_thread = thread
        thread.start()

    def _build_index_worker(self, folder: Path) -> None:
        try:
            architecture_index = self.index_builder.build(folder)
            self.ui_queue.put(("index_done", architecture_index))
        except Exception as exc:
            self.ui_queue.put(("index_failed", str(exc)))

    def build_bundle(self, selection_result: SelectionResult) -> WorkingSetBundle:
        self.run_state_service.begin_bundle_build()
        bundle = self.bundle_builder.build(selection_result)
        if self.selected_slot_index >= 0:
            self.spec_queue.queue_slots[self.selected_slot_index].bundle_result = bundle
        self.run_state_service.complete_bundle_build(bundle)
        self._refresh_bundle_view()
        self._refresh_queue_view()
        return bundle

    def _set_active_artifacts(self, selection_result: SelectionResult | None, bundle: WorkingSetBundle | None) -> None:
        if selection_result is not None:
            self.run_state_service.complete_selection(selection_result)
            self._refresh_selection_view()
        if bundle is not None:
            self.run_state_service.complete_bundle_build(bundle)
            self._refresh_bundle_view()

    def _active_bundle(self) -> WorkingSetBundle | None:
        queue_state = self.spec_queue
        if queue_state.active_slot_index >= 0:
            active_slot = queue_state.queue_slots[queue_state.active_slot_index]
            if active_slot.bundle_result is not None:
                return active_slot.bundle_result

        if self.selected_slot_index >= 0:
            selected_slot = queue_state.queue_slots[self.selected_slot_index]
            if selected_slot.bundle_result is not None:
                return selected_slot.bundle_result

        return self.run_state_service.bundle_state.latest_bundle

    def select_files(self) -> None:
        if self.selection_active:
            self.log_event("Select Files blocked: a selection is already in progress.")
            return
        architecture_index = self.run_state_service.index_state.latest_index
        if architecture_index is None:
            self.log_event("Select Files blocked: no architecture index available.")
            self.set_status_action("selection failed")
            return
        spec = self.spec_text.get("1.0", "end-1c").strip()
        if not spec:
            self.log_event("Select Files blocked: spec textbox is empty.")
            self.set_status_action("selection failed")
            return

        self.selection_active = True
        self.select_files_button.state(["disabled"])
        self.run_state_service.begin_selection()
        self._refresh_selection_view()
        term_count = len(self.file_selector._tokenize(spec))
        self.log_event("selection started")
        self.log_event(f"spec length: {len(spec)}")
        self.log_event(f"normalized term count: {term_count}")
        self.log_event("index availability confirmed")
        self.set_status_action("selection running")
        thread = threading.Thread(target=self._select_files_worker, args=(spec, architecture_index, self.selected_slot_index), daemon=True)
        self.selection_thread = thread
        thread.start()

    def _select_files_worker(self, spec: str, architecture_index: ArchitectureIndex, slot_index: int) -> None:
        try:
            selection_result = self.file_selector.select(spec, architecture_index)
            self.ui_queue.put(("selection_done", (slot_index, selection_result)))
        except Exception as exc:
            self.ui_queue.put(("selection_failed", str(exc)))

    def start_queue(self) -> None:
        if self.queue_active:
            self.log_event("Start Queue blocked: queue execution already in progress.")
            return
        specs = self._capture_queue_specs()
        self.queue_service.load_specs(self.spec_queue, specs)
        self.queue_service.start(self.spec_queue)
        self.run_state_service.set_queue_state(self.spec_queue, status="running")
        self.queue_active = True
        self.start_queue_button.state(["disabled"])
        self.stop_queue_button.state(["!disabled"])
        self._refresh_queue_view()
        self.log_event("queue started")
        self.set_status_action("queue running")
        thread = threading.Thread(target=self._run_queue_worker, daemon=True)
        self.queue_thread = thread
        thread.start()

    def stop_queue(self) -> None:
        self.queue_service.request_stop(self.spec_queue)
        self.log_event("queue stop requested")
        self.set_status_action("queue stopping")

    def _run_queue_worker(self) -> None:
        self.ui_queue.put(("queue_log", "Queue started"))
        model_name = self.model_var.get().strip()

        for slot in self.spec_queue.queue_slots:
            if self.spec_queue.stop_requested:
                if slot.status == "ready":
                    self.queue_service.mark_slot_stopped(slot, "stop requested before slot start")
                    self.ui_queue.put(("queue_slot_stopped", (slot.slot_index, slot.failure_reason)))
                continue
            if not slot.spec_text.strip():
                slot.status = "empty"
                continue

            self.queue_service.mark_slot_running(self.spec_queue, slot)
            self.ui_queue.put(("queue_slot_state", slot.slot_index))
            self.ui_queue.put(("queue_log", f"Active slot changed to {slot.slot_index + 1}"))
            self.ui_queue.put(("queue_log", f"Slot {slot.slot_index + 1} started"))

            stages = [
                "Spec Intake",
                "Spec Parsing",
                "Task Execution",
                "Validation",
                "Logging / Audit",
            ]
            current_stage_idx = -1

            def update_stage(name: str, status: str, message: str = ""):
                nonlocal current_stage_idx
                self.queue_service.update_stage_status(slot, name, status, message)
                if status == "running":
                    current_stage_idx = stages.index(name)
                self.ui_queue.put(("pipeline_update", None))

            def check_stop():
                if self.spec_queue.stop_requested:
                    raise InterruptedError("stop requested")

            try:
                # 1. Spec Intake
                update_stage("Spec Intake", "running")
                if not slot.spec_text.strip():
                    raise RuntimeError("no spec")
                update_stage("Spec Intake", "completed")
                check_stop()

                # 2. Spec Parsing
                update_stage("Spec Parsing", "running")
                tasks = self.spec_parser.parse(slot.spec_text)
                if not tasks:
                    self.ui_queue.put(("queue_log", "No tasks found in spec"))
                else:
                    self.ui_queue.put(("queue_log", f"Parsed {len(tasks)} tasks"))
                update_stage("Spec Parsing", "completed", f"tasks={len(tasks)}")
                check_stop()

                # 3. Task Execution
                update_stage("Task Execution", "running")
                if not self.current_folder:
                    raise RuntimeError("no project folder")

                file_ops = FileOpsService(self.current_folder)
                executor = TaskExecutorService(file_ops, self.ollama_service, self.process_service, model_name)

                all_changes = []
                for task in tasks:
                    self.ui_queue.put(("queue_log", f"Executing task: {task.type.value} {task.target}"))
                    result = executor.execute(task)
                    if not result.success:
                        raise RuntimeError(f"Task failed: {result.message}")
                    all_changes.extend(result.changes)

                update_stage("Task Execution", "completed", f"changes={len(all_changes)}")
                check_stop()

                # 4. Validation
                update_stage("Validation", "running")
                for change in all_changes:
                    # Skip validation for files that were deleted
                    target_path = self.current_folder / change
                    if not target_path.exists():
                        continue

                    if change.endswith(".py"):
                        ok, msg = self.validation_service.validate_python_syntax(target_path)
                        if not ok:
                            raise RuntimeError(f"Validation failed for {change}: {msg}")
                update_stage("Validation", "completed")
                check_stop()

                # 5. Logging / Audit
                update_stage("Logging / Audit", "running")
                run_folder = self.audit_log_service.create_run_folder(slot.slot_index + 1)
                self.audit_log_service.log_artifact(run_folder, "spec.txt", slot.spec_text)
                self.audit_log_service.log_artifact(run_folder, "tasks.json", [{"id": t.id, "type": t.type.value, "target": t.target, "status": t.status.value} for t in tasks])

                # Simplified log for audit
                execution_log = [f"{t.type.value} {t.target}: {t.status.value}" for t in tasks]
                self.audit_log_service.log_artifact(run_folder, "execution.log", "\n".join(execution_log))

                for change in all_changes:
                    self.audit_log_service.capture_file_change(run_folder, self.current_folder, change)

                self.ui_queue.put(("queue_log", f"Audit logs saved to: {run_folder}"))
                update_stage("Logging / Audit", "completed")
                check_stop()

                self.queue_service.mark_slot_completed(self.spec_queue, slot)
                self.ui_queue.put(("queue_slot_completed", slot.slot_index))
                self.ui_queue.put(("queue_log", f"Slot {slot.slot_index + 1} completed"))

            except InterruptedError:
                self.queue_service.mark_slot_stopped(slot, "stop requested")
                self.ui_queue.put(("queue_slot_stopped", (slot.slot_index, "stop requested")))
                self.ui_queue.put(("queue_log", f"Slot {slot.slot_index + 1} stopped"))
            except Exception as exc:
                if current_stage_idx >= 0:
                    failed_stage = stages[current_stage_idx]
                    update_stage(failed_stage, "failed", str(exc))
                    for s_name in stages[current_stage_idx + 1:]:
                        update_stage(s_name, "skipped", "upstream failure")

                self.queue_service.mark_slot_failed(self.spec_queue, slot, str(exc))
                self.ui_queue.put(("queue_slot_failed", (slot.slot_index, str(exc))))
                self.ui_queue.put(("queue_log", f"Slot {slot.slot_index + 1} failed"))

        final_status = "stopped" if self.spec_queue.stop_requested else "completed"
        self.queue_service.finalize(self.spec_queue, final_status)
        self.ui_queue.put(("queue_finished", final_status))

    def restore_bundle(self) -> None:
        if self.restore_active:
            self.log_event("Restore Bundle blocked: restore already in progress.")
            return
        if not self.current_folder:
            self.log_event("Restore Bundle blocked: no project folder selected.")
            self.set_status_action("restore failed")
            return
        bundle = self._active_bundle()
        if bundle is None:
            self.log_event("Restore Bundle blocked: no bundle available.")
            self.set_status_action("restore failed")
            return
        if bundle.total_files == 0:
            self.log_event("Restore Bundle blocked: bundle has no files to restore.")
            self.set_status_action("restore failed")
            return

        self.log_event("computing restore preview (bundle)")
        preview = self.restore_service.compute_bundle_preview(self.current_folder, bundle)
        self.run_state_service.set_restore_preview(preview)
        self.pending_restore_type = "bundle"
        self._refresh_restore_preview()

        # Switch to preview tab
        for i, tabid in enumerate(self.notebook.tabs()):
            if "Restore Preview" in self.notebook.tab(tabid, "text"):
                self.notebook.select(i)
                break

        self.log_event("restore preview ready - please confirm restore")

    def _restore_bundle_worker(self, project_root: Path, bundle: WorkingSetBundle, slot_index: int) -> None:
        try:
            result = self.restore_service.restore_bundle(project_root, bundle)
            self.ui_queue.put(("restore_done", (slot_index, result)))
        except Exception as exc:
            self.ui_queue.put(("restore_failed", str(exc)))

    def restore_candidate(self) -> None:
        if self.restore_active:
            self.log_event("Restore Candidate blocked: restore already in progress.")
            return
        if not self.current_folder:
            self.log_event("Restore Candidate blocked: no project folder selected.")
            return
        edit_state = self.run_state_service.bundle_edit_state
        run = edit_state.latest_edit_run
        if run is None or run.candidate_bundle is None:
            self.log_event("Restore Candidate blocked: no candidate bundle available.")
            return
        if run.validation_status != "passed":
            self.log_event("Restore Candidate blocked: candidate bundle failed validation.")
            return

        self.log_event("computing restore preview (candidate)")
        preview = self.restore_service.compute_candidate_preview(self.current_folder, run.candidate_bundle)
        self.run_state_service.set_restore_preview(preview)
        self.pending_restore_type = "candidate"
        self._refresh_restore_preview()

        # Switch to preview tab
        for i, tabid in enumerate(self.notebook.tabs()):
            if "Restore Preview" in self.notebook.tab(tabid, "text"):
                self.notebook.select(i)
                break

        self.log_event("restore preview ready - please confirm restore")

    def confirm_restore(self) -> None:
        if self.restore_active:
            return
        if not self.current_folder:
            return

        if self.pending_restore_type == "bundle":
            bundle = self._active_bundle()
            if not bundle:
                return
            self.restore_active = True
            self.confirm_restore_button.state(["disabled"])
            self.restore_bundle_button.state(["disabled"])
            self.run_state_service.begin_restore()
            self._refresh_restore_view()
            self.log_event("restore confirmed (bundle)")
            self.set_status_action("restoring")
            thread = threading.Thread(target=self._restore_bundle_worker, args=(Path(self.current_folder), bundle, self.selected_slot_index), daemon=True)
            self.restore_thread = thread
            thread.start()
        elif self.pending_restore_type == "candidate":
            edit_state = self.run_state_service.bundle_edit_state
            run = edit_state.latest_edit_run
            if not run or not run.candidate_bundle:
                return
            self.restore_active = True
            self.confirm_restore_button.state(["disabled"])
            self.restore_candidate_button.state(["disabled"])
            self.run_state_service.begin_restore()
            self._refresh_restore_view()
            run.restore_status = "started"
            self._refresh_candidate_view()
            self.log_event("restore confirmed (candidate)")
            self.set_status_action("restoring candidate")
            thread = threading.Thread(target=self._restore_candidate_worker, args=(Path(self.current_folder), run, self.selected_slot_index), daemon=True)
            self.restore_thread = thread
            thread.start()

        self.pending_restore_type = "none"

    def _restore_candidate_worker(self, project_root: Path, edit_run: BundleEditRun, slot_index: int) -> None:
        try:
            result = self.restore_service.restore_candidate_bundle(project_root, edit_run.candidate_bundle)
            edit_run.restore_status = result.status
            self.ui_queue.put(("restore_done", (slot_index, result)))
            self.ui_queue.put(("candidate_refresh", None))
        except Exception as exc:
            edit_run.restore_status = "failed"
            self.ui_queue.put(("restore_failed", str(exc)))
            self.ui_queue.put(("candidate_refresh", None))

    def run_bundle_edit(self) -> None:
        if self.bundle_edit_active:
            self.log_event("Bundle Edit blocked: a run is already in progress.")
            return

        model = self.model_var.get().strip()
        if not model:
            self.log_event("Bundle Edit blocked: no model selected.")
            return

        spec = self.spec_text.get("1.0", "end-1c").strip()
        if not spec:
            self.log_event("Bundle Edit blocked: spec textbox is empty.")
            return

        bundle = self._active_bundle()
        if not bundle:
            self.log_event("Bundle Edit blocked: no source bundle available.")
            return

        self.log_event("bundle edit started")

        queue_state = self.spec_queue
        if queue_state.active_slot_index >= 0:
            self.log_event(f"slot context identified: slot {queue_state.active_slot_index + 1}")
        else:
            self.log_event("spec context identified: current active spec")

        self.log_event(f"source bundle file count: {bundle.total_files}")

        try:
            request = PromptRequest(
                model_name=model,
                project_folder=self._current_project_folder_text(),
                spec_text=spec
            )
            assembled_prompt = self.bundle_prompt_builder.build(request, bundle)
        except Exception as exc:
            self.log_event(f"prompt assembly failed: {exc}")
            return

        self.log_event("prompt assembled")
        self._set_text_widget_content(self.prompt_preview, assembled_prompt)

        edit_run = BundleEditRun(
            run_id=f"run_{int(time.time())}",
            slot_index=self.selected_slot_index,
            model_name=model,
            spec_text=spec,
            source_bundle=bundle,
            assembled_prompt=assembled_prompt,
            started_at=self.run_state_service._now(),
            status="running"
        )
        self.run_state_service.begin_bundle_edit(edit_run)
        self._refresh_candidate_view()

        snapshot = self.ollama_service.create_snapshot(model, assembled_prompt)
        self.bundle_edit_active = True
        self.edit_bundle_button.state(["disabled"])
        self.set_status_action("editing bundle")
        self.append_log_separator("Bundle Edit Run")
        self.log_event("model selected")
        self.log_event(f"prompt length: {len(assembled_prompt)}")

        thread = threading.Thread(target=self._run_bundle_edit_worker, args=(snapshot, edit_run), daemon=True)
        self.bundle_edit_thread = thread
        thread.start()

    def _run_bundle_edit_worker(self, snapshot: OllamaRunSnapshot, edit_run: BundleEditRun) -> None:
        try:
            self.ui_queue.put(("bundle_edit_streaming_started", None))
            accumulator = []
            for event in self.ollama_service.run_prompt_stream(snapshot):
                if event["type"] == "chunk":
                    chunk = event["text"]
                    accumulator.append(chunk)
                    self.ui_queue.put(("bundle_edit_chunk", chunk))
                elif event["type"] == "done":
                    raw_output = "".join(accumulator)
                    edit_run.raw_model_output = raw_output
                    self.ui_queue.put(("bundle_edit_streaming_done", edit_run))
        except Exception as exc:
            self.ui_queue.put(("bundle_edit_failed", (edit_run, str(exc))))

    def run_llm(self) -> None:
        if self.llm_run_active:
            self.log_event("Run LLM blocked: a run is already in progress.")
            return

        model = self.model_var.get().strip()
        if not model:
            self.log_event("Run LLM blocked: no model selected.")
            self.set_status_action("failed")
            return

        spec = self.spec_text.get("1.0", "end-1c").strip()
        if not spec:
            self.log_event("Run LLM blocked: spec textbox is empty.")
            self.set_status_action("failed")
            return

        self.log_event("prompt assembly started")
        try:
            assembled_prompt = self._build_prompt_from_ui()
        except Exception as exc:
            self.log_event(f"prompt assembly failed: {exc}")
            self.set_status_action("failed")
            return
        self.log_event("prompt assembly completed")
        self._set_text_widget_content(self.prompt_preview, assembled_prompt)

        project_folder = self._current_project_folder_text()
        run_state = self.run_state_service.begin_run(
            model_name=model,
            project_folder=project_folder,
            spec_text=spec,
            assembled_prompt=assembled_prompt,
        )
        self._refresh_response_view()
        snapshot = self.ollama_service.create_snapshot(model, assembled_prompt)
        self.active_run_snapshot = snapshot
        self.llm_run_active = True
        self.llm_run_started_at = time.time()
        self.llm_chunk_count = 0
        self.llm_output_chars = 0
        self.run_llm_button.state(["disabled"])
        self.append_log_separator("LLM Run")
        self.log_event("run started")
        self.log_event(f"selected model: {snapshot.model}")
        self.log_event(f"prompt length: {len(run_state.assembled_prompt)}")
        self.log_event("prompt submitted")
        self.set_status_action("running")

        thread = threading.Thread(target=self._run_llm_worker, args=(snapshot,), daemon=True)
        self.llm_run_thread = thread
        thread.start()

    def _run_llm_worker(self, snapshot: OllamaRunSnapshot) -> None:
        try:
            self.ui_queue.put(("llm_streaming_started", snapshot.model))
            for event in self.ollama_service.run_prompt_stream(snapshot):
                self.ui_queue.put(("llm_event", event))
        except Exception as exc:
            self.ui_queue.put(("llm_failed", str(exc)))

    def _append_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.insert("end", text)
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def _process_ui_queue(self) -> None:
        while True:
            try:
                message, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_ui_message(message, payload)
        self.root.after(100, self._process_ui_queue)

    def _handle_ui_message(self, message: str, payload: object) -> None:
        if message == "tree_loaded":
            self._render_tree(payload)  # type: ignore[arg-type]
            self.log_event("Project tree refreshed.")
            return
        if message == "tree_error":
            self.log_event(f"Tree refresh failed: {payload}")
            return
        if message == "models_loaded":
            models = payload if isinstance(payload, list) else []
            self.model_combo["values"] = models
            if models:
                current = self.model_var.get()
                if current not in models:
                    self.model_var.set(models[0])
                self.model_combo.state(["!disabled", "readonly"])
                self.status_model_var.set(f"Model: {self.model_var.get()}")
                self.log_event(f"Loaded {len(models)} Ollama model(s).")
                self._refresh_prompt_preview()
            else:
                self.model_var.set("")
                self.model_combo.state(["disabled"])
                self.status_model_var.set("Model: unavailable")
                self.log_event("No local Ollama models found.")
                self._refresh_prompt_preview()
            return
        if message == "models_error":
            self.model_combo["values"] = []
            self.model_var.set("")
            self.model_combo.state(["disabled"])
            self.status_model_var.set("Model: unavailable")
            self.log_event(f"Ollama model refresh failed: {payload}")
            self._refresh_prompt_preview()
            return
        if message == "command_done":
            result = payload
            if not isinstance(result, ProcessResult):
                return
            output_parts = [f"\nPS> {result.command}\n"]
            if result.stdout:
                output_parts.append(result.stdout)
                if not result.stdout.endswith("\n"):
                    output_parts.append("\n")
            if result.stderr:
                output_parts.append(result.stderr)
                if not result.stderr.endswith("\n"):
                    output_parts.append("\n")
            output_parts.append(f"[exit code: {result.return_code}]\n")
            self._append_output("".join(output_parts))
            if result.return_code == 0:
                self.log_event(f"Command completed successfully: {result.command}")
            else:
                self.log_event(f"Command failed with exit code {result.return_code}: {result.command}")
            return
        if message == "command_error":
            self._append_output(f"\n[command error] {payload}\n")
            self.log_event(f"Command execution error: {payload}")
            return
        if message == "index_done":
            architecture_index = payload
            if not isinstance(architecture_index, ArchitectureIndex):
                return
            self.index_build_active = False
            self.build_index_button.state(["!disabled"])
            self.run_state_service.complete_index_build(architecture_index)
            self._refresh_index_view()
            self.log_event(f"files scanned count: {architecture_index.file_count}")
            self.log_event(f"files indexed count: {architecture_index.indexed_file_count}")
            self.log_event(f"skipped files count: {architecture_index.skipped_file_count}")
            self.log_event(f"parse error count: {architecture_index.parse_error_count}")
            self.log_event("index build completed")
            self.set_status_action("index completed")
            return
        if message == "index_failed":
            self.index_build_active = False
            self.build_index_button.state(["!disabled"])
            self.run_state_service.fail_index_build(str(payload))
            self._refresh_index_view()
            self.log_event(f"index build failed: {payload}")
            self.set_status_action("index failed")
            return
        if message == "selection_done":
            if not isinstance(payload, tuple) or len(payload) != 2:
                return
            slot_index, selection_result = payload
            if not isinstance(selection_result, SelectionResult):
                return
            self.selection_active = False
            self.select_files_button.state(["!disabled"])
            if slot_index >= 0:
                self.spec_queue.queue_slots[slot_index].selection_result = selection_result
            self.run_state_service.complete_selection(selection_result)
            self._refresh_selection_view()
            self._refresh_queue_view()
            self.log_event(f"primary files selected count: {selection_result.selected_primary_count}")
            self.log_event(f"context files selected count: {selection_result.selected_context_count}")
            self.log_event(f"unmatched terms count: {len(selection_result.unmatched_terms)}")
            self.log_event("selection completed")
            self.set_status_action("selection completed")
            return
        if message == "selection_failed":
            self.selection_active = False
            self.select_files_button.state(["!disabled"])
            self.run_state_service.fail_selection(str(payload))
            self._refresh_selection_view()
            self.log_event(f"selection failed: {payload}")
            self.set_status_action("selection failed")
            return
        if message == "queue_slot_state":
            self._refresh_queue_view()
            self._refresh_pipeline_view()
            return
        if message == "pipeline_update":
            self._refresh_pipeline_view()
            return
        if message == "queue_log":
            self.log_event(str(payload))
            return
        if message == "queue_slot_selection":
            if not isinstance(payload, tuple) or len(payload) != 2:
                return
            slot_index, selection_result = payload
            if not isinstance(slot_index, int) or not isinstance(selection_result, SelectionResult):
                return
            self.spec_queue.queue_slots[slot_index].selection_result = selection_result
            self._set_active_artifacts(selection_result, None)
            self._refresh_queue_view()
            self.log_event(f"slot selection completed: {slot_index + 1}")
            return
        if message == "queue_slot_bundle":
            if not isinstance(payload, tuple) or len(payload) != 2:
                return
            slot_index, bundle = payload
            if not isinstance(slot_index, int) or not isinstance(bundle, WorkingSetBundle):
                return
            self.spec_queue.queue_slots[slot_index].bundle_result = bundle
            self._set_active_artifacts(None, bundle)
            self._refresh_queue_view()
            self.log_event(f"slot bundle built: {slot_index + 1}")
            self.log_event(f"slot bundle file count: {bundle.total_files}")
            return
        if message == "queue_slot_completed":
            if not isinstance(payload, int):
                return
            self._refresh_queue_view()
            self.log_event(f"Slot {payload + 1} completed")
            return
        if message == "queue_slot_failed":
            if not isinstance(payload, tuple) or len(payload) != 2:
                return
            slot_index, reason = payload
            if not isinstance(slot_index, int):
                return
            self._refresh_queue_view()
            self.log_event(f"Slot {slot_index + 1} failed")
            self.log_event(f"failure reason: {reason}")
            return
        if message == "queue_slot_stopped":
            if not isinstance(payload, tuple) or len(payload) != 2:
                return
            slot_index, reason = payload
            if not isinstance(slot_index, int):
                return
            self._refresh_queue_view()
            self.log_event(f"Slot {slot_index + 1} stopped")
            self.log_event(f"stop reason: {reason}")
            return
        if message == "queue_finished":
            final_status = str(payload)
            self.queue_active = False
            self.start_queue_button.state(["!disabled"])
            self.stop_queue_button.state(["disabled"])
            self.run_state_service.set_queue_state(self.spec_queue, status=final_status)
            self._refresh_queue_view()
            self._refresh_pipeline_view()
            self.log_event(f"queue {final_status}")
            self.set_status_action(f"queue {final_status}")
            return
        if message == "restore_done":
            if not isinstance(payload, tuple) or len(payload) != 2:
                return
            slot_index, restore_result = payload
            if not isinstance(restore_result, RestoreResult):
                return
            self.restore_active = False
            self.restore_bundle_button.state(["!disabled"])
            if slot_index >= 0:
                self.spec_queue.queue_slots[slot_index].restore_result = restore_result
            self.run_state_service.complete_restore(restore_result)
            self._refresh_restore_view()
            self._refresh_queue_view()
            self.log_event(f"files written count: {restore_result.written_file_count}")
            self.log_event(f"files skipped count: {restore_result.skipped_file_count}")
            self.log_event(f"files failed count: {restore_result.failed_file_count}")
            self.log_event(f"restore {restore_result.status}")
            self.set_status_action(f"restore {restore_result.status}")
            self.refresh_tree()
            return
        if message == "restore_failed":
            self.restore_active = False
            self.restore_bundle_button.state(["!disabled"])
            self.run_state_service.fail_restore(str(payload))
            self._refresh_restore_view()
            self.log_event(f"restore failed: {payload}")
            self.set_status_action("restore failed")
            return
        if message == "llm_streaming_started":
            self.log_event(f"streaming began for model: {payload}")
            return
        if message == "llm_event":
            if not isinstance(payload, dict):
                return
            event_type = payload.get("type")
            if event_type == "chunk":
                chunk = str(payload.get("text", ""))
                self.llm_chunk_count += 1
                self.llm_output_chars += len(chunk)
                self.run_state_service.append_chunk(chunk)
                self.append_model_output(chunk)
                if self.llm_chunk_count == 1:
                    self.append_model_output("\n")
                if self.llm_chunk_count % 10 == 0:
                    self.log_event(f"streaming chunks received: {self.llm_chunk_count}")
                self._refresh_response_view()
                return
            if event_type == "warning":
                self.log_event(str(payload.get("message", "Streaming warning received.")))
                return
            if event_type == "done":
                elapsed = time.time() - self.llm_run_started_at
                self.llm_run_active = False
                self.run_llm_button.state(["!disabled"])
                self.append_model_output("\n")
                self.log_event(f"streaming chunks received: {self.llm_chunk_count}")
                self.log_event(f"run completed in {elapsed:.1f}s")
                self.log_event(f"output size: {self.llm_output_chars} chars")
                self.run_state_service.complete_run()
                self.log_event("response captured")
                self._refresh_response_view()
                self.set_status_action("completed")
                self.active_run_snapshot = None
                return
        if message == "candidate_refresh":
            self._refresh_candidate_view()
            return
        if message == "bundle_edit_streaming_started":
            self.log_event("generation/streaming active")
            return
        if message == "bundle_edit_chunk":
            self.append_model_output(str(payload))
            return
        if message == "bundle_edit_streaming_done":
            edit_run = payload
            if not isinstance(edit_run, BundleEditRun):
                return
            self.log_event("raw output received")
            self.log_event("bundle parse started")
            try:
                candidate = self.bundle_parser.parse(edit_run.raw_model_output)
                edit_run.candidate_bundle = candidate
                self.log_event("parse successful")
            except Exception as exc:
                self.log_event(f"parse failed: {exc}")
                edit_run.status = "failed"
                edit_run.completed_at = self.run_state_service._now()
                self.bundle_edit_active = False
                self.edit_bundle_button.state(["!disabled"])
                self._refresh_candidate_view()
                if edit_run.slot_index >= 0:
                    self.spec_queue.queue_slots[edit_run.slot_index].llm_edit_run = edit_run
                    self._refresh_queue_view()
                return

            self.log_event("validation started")
            errors = self.bundle_validator.validate(candidate, edit_run.source_bundle, edit_run.source_bundle.project_root)
            if errors:
                edit_run.validation_status = "failed"
                edit_run.validation_errors = errors
                self.log_event("validation failed")
                for err in errors:
                    self.log_event(f"error: {err}")
            else:
                edit_run.validation_status = "passed"
                self.log_event("validation passed")
                self.log_event("candidate bundle ready")

            edit_run.status = "completed"
            edit_run.completed_at = self.run_state_service._now()
            self.bundle_edit_active = False
            self.edit_bundle_button.state(["!disabled"])
            self.set_status_action("edit completed")
            self._refresh_candidate_view()
            if edit_run.slot_index >= 0:
                self.spec_queue.queue_slots[edit_run.slot_index].llm_edit_run = edit_run
                self._refresh_queue_view()
            return
        if message == "bundle_edit_failed":
            edit_run, error = payload
            self.log_event(f"bundle edit failed: {error}")
            edit_run.status = "failed"
            edit_run.completed_at = self.run_state_service._now()
            self.bundle_edit_active = False
            self.edit_bundle_button.state(["!disabled"])
            self.set_status_action("edit failed")
            self._refresh_candidate_view()
            if edit_run.slot_index >= 0:
                self.spec_queue.queue_slots[edit_run.slot_index].llm_edit_run = edit_run
                self._refresh_queue_view()
            return
        if message == "llm_failed":
            self.llm_run_active = False
            self.run_llm_button.state(["!disabled"])
            self.log_event(f"run failed: {payload}")
            self.run_state_service.fail_run(str(payload))
            self._refresh_response_view()
            self.set_status_action("failed")
            self.active_run_snapshot = None
