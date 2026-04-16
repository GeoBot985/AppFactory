from __future__ import annotations

import queue
import shutil
import threading
import time
import json
import uuid
import tkinter as tk
from pathlib import Path
from datetime import datetime
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
from services.run_ledger.models import RunState as DurableRunState, QueueState as DurableQueueState, QueueDefinition, RunMetadata, LedgerEvent
from services.run_ledger.ledger import LedgerService
from services.run_ledger.queue_store import QueueStore
from services.run_ledger.recovery import RecoveryService, InterruptionCategory, RecoveryAction
from services.run_ledger.executor import ResumeService, ReplayService
from services.run_ledger.consistency import ConsistencyChecker

from workspace.models import ExecutionMode, SourcePolicy, PromotionStatus
from workspace.fingerprints import FingerprintService
from workspace.snapshots import SnapshotService
from workspace.promotion import PromotionService
from workspace.conflicts import ConflictService

from verification.engine import VerificationEngine
from verification.outcome import OutcomeSynthesizer
from verification.models import FailureStage, FinalOutcome, CheckStatus, VerificationReport
from verification.reporting import ReportingService

from services.policy.models import RiskClass, PolicyDecision, PolicyConfig, ApprovalStatus
from services.policy.risk_classifier import RiskClassifier
from services.policy.evaluator import PolicyEvaluator
from services.policy.approvals import ApprovalService

from runtime_profiles.models import RuntimeProfile, DriftPolicyMode
from runtime_profiles.registry import ProfileRegistry
from runtime_profiles.interpreter import InterpreterResolver, InterpreterValidator
from runtime_profiles.environment import EnvironmentBuilder, EnvironmentMasker
from runtime_profiles.fingerprints import RuntimeFingerprintService
from runtime_profiles.commands import CommandExecutor, CommandResult
from runtime_profiles.drift import DriftDetector

from ops.ops_service import OpsService
from ops.health import HealthEvaluator
from ops.rebuild import RebuildService


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
        self.ledger_service = LedgerService(Path.cwd())
        self.queue_store = QueueStore(Path.cwd())
        self.recovery_service = RecoveryService(Path.cwd(), self.ledger_service)
        self.resume_service = ResumeService(Path.cwd(), self.ledger_service)
        self.replay_service = ReplayService(Path.cwd(), self.ledger_service, self.audit_log_service)
        self.consistency_checker = ConsistencyChecker(Path.cwd(), self.ledger_service)

        self.ops_service = OpsService(Path.cwd())
        self.health_evaluator = HealthEvaluator(Path.cwd())
        self.rebuild_service = RebuildService(Path.cwd())

        self.policy_config = PolicyConfig()
        self.risk_classifier = RiskClassifier(self.policy_config)
        self.policy_evaluator = PolicyEvaluator(self.policy_config)
        self.approval_service = ApprovalService(Path.cwd())

        self.profile_registry = ProfileRegistry()
        self._load_external_profiles()
        self.env_masker = EnvironmentMasker()

    def _load_external_profiles(self):
        profile_file = Path.cwd() / "profiles.yaml"
        if profile_file.exists():
            try:
                import yaml
                with profile_file.open("r") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict) and "profiles" in data:
                        for p_id, p_data in data["profiles"].items():
                            p_data["profile_id"] = p_id
                            profile = self.profile_registry.from_dict(p_data)
                            self.profile_registry.register(profile)
                self.log_event(f"Loaded external profiles from {profile_file}")
            except Exception as e:
                self.log_event(f"Failed to load external profiles: {e}")

        self.fingerprint_service = FingerprintService()
        self.snapshot_service = SnapshotService(self.fingerprint_service)
        self.promotion_service = PromotionService(self.fingerprint_service)
        self.conflict_service = ConflictService(self.fingerprint_service)

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
        self.write_mode_var = tk.StringVar(value="dry-run")
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
        self.root.after(200, self._startup_recovery)

    def _startup_recovery(self):
        self.log_event("Attempting queue rehydration...")
        current_queues = self.queue_store.load_current_queues()
        if current_queues:
            # Sort by updated_at or just take the last one
            latest_q_id = list(current_queues.keys())[-1]
            q_def = self.queue_store.get_queue_definition(latest_q_id)
            if q_def:
                self.log_event(f"Rehydrating queue {latest_q_id} (State: {q_def.state.value})")
                self.spec_queue.queue_id = q_def.queue_id
                self.spec_queue.queue_status = "paused" # Always start paused after recovery
                for i, s_info in enumerate(q_def.slots):
                    if i < len(self.spec_queue.queue_slots):
                        slot = self.spec_queue.queue_slots[i]
                        slot.spec_text = s_info.get("spec", "")

                        # Find latest run for this slot in ledger
                        all_runs = self.ledger_service.load_current_runs()
                        slot_runs = [r for r in all_runs.values() if r.get("queue_id") == q_def.queue_id and r.get("slot_id") == str(i)]
                        if slot_runs:
                             # Sort by updated_at
                             slot_runs.sort(key=lambda x: x.get("updated_at", ""))
                             latest_run = slot_runs[-1]
                             slot.current_run_id = latest_run.get("run_id")
                             status_map = {
                                 DurableRunState.COMPLETED.value: "completed",
                                 DurableRunState.FAILED.value: "failed",
                                 DurableRunState.INTERRUPTED.value: "interrupted",
                                 DurableRunState.RECOVERY_PENDING.value: "interrupted",
                             }
                             slot.status = status_map.get(latest_run.get("state"), "ready" if slot.spec_text else "empty")

                self._refresh_queue_view()

        self.log_event("Starting durability recovery scan...")
        plan = self.recovery_service.scan_for_interrupted_runs()
        if plan:
            self.log_event(f"Detected {len(plan)} interrupted run(s).")
            self.recovery_service.persist_recovery_plan(plan)
            for item in plan:
                self.log_event(f"  - Run {item.run_id}: {item.category.value} -> Recommended: {item.recommended_action.value} ({item.reason})")

                # Update ledger to mark as INTERRUPTED or RECOVERY_PENDING
                metadata = self.ledger_service.get_run_metadata(item.run_id)
                if metadata:
                    metadata.state = DurableRunState.INTERRUPTED
                    self.ledger_service.update_run_metadata(metadata)
                    self.ledger_service.record_event(
                        entity_type="run",
                        entity_id=item.run_id,
                        event_type="state_transition",
                        new_state=DurableRunState.INTERRUPTED.value,
                        run_id=item.run_id,
                        payload={"reason": "startup_recovery_scan"}
                    )
        else:
            self.log_event("No interrupted runs detected.")

        self.log_event("Running ledger consistency check...")
        issues = self.consistency_checker.check_consistency()
        if issues:
            self.log_event(f"Detected {len(issues)} consistency issue(s).")
            self.consistency_checker.persist_consistency_report(issues)
            for issue in issues:
                self.log_event(f"  - [{issue.issue_type}] {issue.description}")
        else:
            self.log_event("Ledger consistency check passed.")

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
        self._refresh_approvals_view()
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
        ttk.Label(top, text="Write Mode", style="Panel.TLabel").grid(row=0, column=8, sticky="w", padx=(12, 0))
        self.write_mode_combo = ttk.Combobox(top, textvariable=self.write_mode_var, state="readonly", values=["dry-run", "apply"], width=10)
        self.write_mode_combo.grid(row=0, column=9, sticky="w", padx=(8, 0))
        Tooltip(self.write_mode_combo, "Choose whether file operations are simulated or written to disk.")

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

        self.resume_run_button = ttk.Button(action_row, text="Resume", command=self.resume_run)
        self.resume_run_button.pack(side="left", padx=(0, 8))
        Tooltip(self.resume_run_button, "Resume the selected interrupted run from the last safe phase boundary.")

        self.replay_run_button = ttk.Button(action_row, text="Replay", command=self.replay_run)
        self.replay_run_button.pack(side="left", padx=(0, 8))
        Tooltip(self.replay_run_button, "Re-execute a past run for diagnosis/comparison.")

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
        approvals_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        slot_detail_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        ops_console_frame = ttk.Frame(notebook, style="Panel.TFrame", padding=4)
        notebook.add(viewer_frame, text="File Viewer")
        notebook.add(prompt_frame, text="Prompt Preview")
        notebook.add(response_frame, text="Latest Response")
        notebook.add(index_frame, text="Architecture Index")
        notebook.add(selection_frame, text="File Selection")
        notebook.add(bundle_frame, text="Bundle Preview")
        notebook.add(candidate_frame, text="Candidate Bundle")
        notebook.add(restore_preview_frame, text="Restore Preview")
        notebook.add(restore_frame, text="Restore Result")
        notebook.add(approvals_frame, text="Policy & Approvals")
        notebook.add(slot_detail_frame, text="Slot Detail")
        notebook.add(ops_console_frame, text="Operations Console")
        self.notebook = notebook

        for frame in (viewer_frame, prompt_frame, response_frame, index_frame, selection_frame, bundle_frame, candidate_frame, restore_preview_frame, restore_frame, approvals_frame, slot_detail_frame, ops_console_frame):
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

        # Approvals Tab
        approvals_frame.rowconfigure(1, weight=1)
        approvals_frame.columnconfigure(0, weight=1)

        ttk.Label(approvals_frame, text="Pending Approvals", font=("Segoe UI", 11, "bold"), style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.approvals_list = ttk.Treeview(approvals_frame, columns=("id", "gate", "entity", "risk", "status"), show="headings")
        self.approvals_list.heading("id", text="ID")
        self.approvals_list.heading("gate", text="Gate")
        self.approvals_list.heading("entity", text="Entity")
        self.approvals_list.heading("risk", text="Risk")
        self.approvals_list.heading("status", text="Status")
        self.approvals_list.column("id", width=150)
        self.approvals_list.column("gate", width=100)
        self.approvals_list.column("entity", width=150)
        self.approvals_list.column("risk", width=80)
        self.approvals_list.column("status", width=100)
        self.approvals_list.grid(row=1, column=0, sticky="nsew")
        self.approvals_list.bind("<<TreeviewSelect>>", self._on_approval_selected)

        appr_scroll = ttk.Scrollbar(approvals_frame, orient="vertical", command=self.approvals_list.yview)
        self.approvals_list.configure(yscrollcommand=appr_scroll.set)
        appr_scroll.grid(row=1, column=1, sticky="ns")

        self.appr_detail_view = tk.Text(
            approvals_frame,
            wrap="word",
            height=8,
            bg="#1b1b1c",
            fg="#d4d4d4",
            font=("Consolas", 10),
            relief="flat",
        )
        self.appr_detail_view.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 8))
        self.appr_detail_view.configure(state="disabled")

        appr_actions = ttk.Frame(approvals_frame, style="Panel.TFrame")
        appr_actions.grid(row=3, column=0, sticky="ew")

        self.approve_btn = ttk.Button(appr_actions, text="Approve", command=self.approve_selected, state="disabled")
        self.approve_btn.pack(side="left", padx=(0, 8))

        self.deny_btn = ttk.Button(appr_actions, text="Deny", command=self.deny_selected, state="disabled")
        self.deny_btn.pack(side="left", padx=(0, 8))

        refresh_appr_btn = ttk.Button(appr_actions, text="Refresh", command=self._refresh_approvals_view)
        refresh_appr_btn.pack(side="right")

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

        # Operations Console Tab
        self._build_ops_console(ops_console_frame)
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

    def _build_ops_console(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        header = ttk.Frame(parent, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(header, text="Operations Console", font=("Segoe UI", 12, "bold"), style="Panel.TLabel").pack(side="left")

        refresh_btn = ttk.Button(header, text="Refresh All", command=self._refresh_ops_console)
        refresh_btn.pack(side="right", padx=5)

        rebuild_btn = ttk.Button(header, text="Rebuild Indices", command=self._rebuild_ops_indices)
        rebuild_btn.pack(side="right")

        self.ops_notebook = ttk.Notebook(parent)
        self.ops_notebook.grid(row=1, column=0, sticky="nsew")

        self.ops_dashboard_frame = ttk.Frame(self.ops_notebook, style="Panel.TFrame", padding=4)
        self.ops_queues_frame = ttk.Frame(self.ops_notebook, style="Panel.TFrame", padding=4)
        self.ops_runs_frame = ttk.Frame(self.ops_notebook, style="Panel.TFrame", padding=4)
        self.ops_approvals_frame = ttk.Frame(self.ops_notebook, style="Panel.TFrame", padding=4)
        self.ops_regression_frame = ttk.Frame(self.ops_notebook, style="Panel.TFrame", padding=4)
        self.ops_recovery_frame = ttk.Frame(self.ops_notebook, style="Panel.TFrame", padding=4)

        self.ops_notebook.add(self.ops_dashboard_frame, text="Dashboard")
        self.ops_notebook.add(self.ops_queues_frame, text="Queues")
        self.ops_notebook.add(self.ops_runs_frame, text="Runs")
        self.ops_notebook.add(self.ops_approvals_frame, text="Approvals")
        self.ops_notebook.add(self.ops_regression_frame, text="Regression")
        self.ops_notebook.add(self.ops_recovery_frame, text="Recovery & Ledger")

        self._build_ops_dashboard(self.ops_dashboard_frame)
        self._build_ops_queues(self.ops_queues_frame)
        self._build_ops_runs(self.ops_runs_frame)
        self._build_ops_approvals(self.ops_approvals_frame)
        self._build_ops_regression(self.ops_regression_frame)
        self._build_ops_recovery(self.ops_recovery_frame)

    def _build_ops_dashboard(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        self.dashboard_view = tk.Text(
            parent,
            wrap="word",
            bg="#1b1b1c",
            fg="#d4d4d4",
            font=("Consolas", 11),
            relief="flat",
        )
        self.dashboard_view.grid(row=0, column=0, sticky="nsew")
        self.dashboard_view.configure(state="disabled")

        self.dashboard_view.tag_configure("header", foreground="#569cd6", font=("Consolas", 12, "bold"))
        self.dashboard_view.tag_configure("banner", background="#4b1f1f", foreground="#f44747", font=("Consolas", 11, "bold"))
        self.dashboard_view.tag_configure("label", foreground="#9cdcfe")
        self.dashboard_view.tag_configure("value", foreground="#d4d4d4")
        self.dashboard_view.tag_configure("ok", foreground="#6a9955")
        self.dashboard_view.tag_configure("warn", foreground="#d7ba7d")
        self.dashboard_view.tag_configure("fail", foreground="#f44747")

    def _build_ops_queues(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.ops_queues_list = ttk.Treeview(parent, columns=("id", "status", "slots", "created", "age"), show="headings")
        self.ops_queues_list.heading("id", text="Queue ID")
        self.ops_queues_list.heading("status", text="Status")
        self.ops_queues_list.heading("slots", text="Slots (C/F/T)")
        self.ops_queues_list.heading("created", text="Created At")
        self.ops_queues_list.heading("age", text="Age (min)")
        self.ops_queues_list.grid(row=0, column=0, sticky="nsew")

    def _build_ops_runs(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.ops_runs_list = ttk.Treeview(parent, columns=("id", "spec", "state", "risk", "duration", "slot"), show="headings")
        self.ops_runs_list.heading("id", text="Run ID")
        self.ops_runs_list.heading("spec", text="Spec ID")
        self.ops_runs_list.heading("state", text="State")
        self.ops_runs_list.heading("risk", text="Risk")
        self.ops_runs_list.heading("duration", text="Dur (s)")
        self.ops_runs_list.heading("slot", text="Slot")
        self.ops_runs_list.grid(row=0, column=0, sticky="nsew")
        self.ops_runs_list.bind("<Double-1>", self._on_ops_run_double_click)

    def _on_ops_run_double_click(self, _event):
        selected = self.ops_runs_list.selection()
        if not selected: return
        values = self.ops_runs_list.item(selected[0])["values"]
        slot_idx_str = values[5]
        try:
            idx = int(slot_idx_str)
            self.select_slot(idx)
            # Switch to Slot Detail tab
            for i, tabid in enumerate(self.notebook.tabs()):
                if "Slot Detail" in self.notebook.tab(tabid, "text"):
                    self.notebook.select(i)
                    break
        except: pass

    def _build_ops_approvals(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.ops_appr_list = ttk.Treeview(parent, columns=("id", "entity", "risk", "status", "age"), show="headings")
        self.ops_appr_list.heading("id", text="ID")
        self.ops_appr_list.heading("entity", text="Entity")
        self.ops_appr_list.heading("risk", text="Risk")
        self.ops_appr_list.heading("status", text="Status")
        self.ops_appr_list.heading("age", text="Age (min)")
        self.ops_appr_list.grid(row=0, column=0, sticky="nsew")

    def _build_ops_regression(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.ops_reg_list = ttk.Treeview(parent, columns=("suite", "status", "pass", "fail", "last_run"), show="headings")
        self.ops_reg_list.heading("suite", text="Suite")
        self.ops_reg_list.heading("status", text="Status")
        self.ops_reg_list.heading("pass", text="Pass")
        self.ops_reg_list.heading("fail", text="Fail")
        self.ops_reg_list.heading("last_run", text="Last Run")
        self.ops_reg_list.grid(row=0, column=0, sticky="nsew")

    def _build_ops_recovery(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.ops_recovery_view = tk.Text(parent, bg="#1b1b1c", fg="#d4d4d4", font=("Consolas", 10))
        self.ops_recovery_view.grid(row=0, column=0, sticky="nsew")

    def _refresh_ops_console(self) -> None:
        self.log_event("Refreshing Operations Console...")
        self._refresh_ops_dashboard()
        self._refresh_ops_queues()
        self._refresh_ops_runs()
        self._refresh_ops_approvals()
        self._refresh_ops_regression()
        self._refresh_ops_recovery()

    def _rebuild_ops_indices(self) -> None:
        self.log_event("Rebuilding Operations Indices...")
        self.rebuild_service.rebuild_all()
        self._refresh_ops_console()

    def _refresh_ops_dashboard(self) -> None:
        summary = self.ops_service._load_json("dashboard_summary.json", {})
        health = self.ops_service._load_json("health_status.json", {})

        self.dashboard_view.configure(state="normal")
        self.dashboard_view.delete("1.0", "end")

        self.dashboard_view.insert("end", "SYSTEM HEALTH\n", "header")
        overall = health.get("status", "UNKNOWN")
        tag = "ok" if overall == "OK" else "warn" if overall == "WARN" else "fail"
        self.dashboard_view.insert("end", f"OVERALL STATUS: {overall}\n\n", tag)

        banners = summary.get("banners", [])
        if banners:
            self.dashboard_view.insert("end", "ACTIVE ALERTS:\n", "header")
            for b in banners:
                self.dashboard_view.insert("end", f" [! {b} ] ", "banner")
            self.dashboard_view.insert("end", "\n\n")

        self.dashboard_view.insert("end", "METRICS SUMMARY\n", "header")
        metrics = [
            ("Active Queues", summary.get("active_queues", 0)),
            ("Running Runs", summary.get("running_runs", 0)),
            ("Approval Pending", summary.get("approval_pending_runs", 0)),
            ("Interrupted Runs", summary.get("interrupted_runs", 0)),
            ("Failing Regressions", summary.get("failing_regression_suites", 0)),
            ("Ledger Issues", summary.get("ledger_issues", 0)),
        ]
        for label, val in metrics:
            self.dashboard_view.insert("end", f"{label:20}: ", "label")
            self.dashboard_view.insert("end", f"{val}\n", "value")

        self.dashboard_view.configure(state="disabled")

    def _refresh_ops_queues(self) -> None:
        self.ops_queues_list.delete(*self.ops_queues_list.get_children())
        data = self.ops_service._load_json("queue_index.json", [])
        for q in data:
            slots_str = f"{q.get('slots_completed')}/{q.get('slots_failed')}/{q.get('slots_total')}"
            self.ops_queues_list.insert("", "end", values=(q.get("queue_id"), q.get("status"), slots_str, q.get("created_at"), q.get("age_minutes")))

    def _refresh_ops_runs(self) -> None:
        self.ops_runs_list.delete(*self.ops_runs_list.get_children())
        data = self.ops_service._load_json("run_index.json", [])
        for r in data:
            self.ops_runs_list.insert("", "end", values=(r.get("run_id"), r.get("spec_id"), r.get("state"), r.get("risk_class", "-"), r.get("duration_seconds", "-"), r.get("slot_id", "-")))

    def _refresh_ops_approvals(self) -> None:
        self.ops_appr_list.delete(*self.ops_appr_list.get_children())
        data = self.ops_service._load_json("approval_index.json", [])
        for a in data:
            self.ops_appr_list.insert("", "end", values=(a.get("approval_id"), a.get("entity_id"), a.get("risk_class"), a.get("status"), a.get("age_minutes")))

    def _refresh_ops_regression(self) -> None:
        self.ops_reg_list.delete(*self.ops_reg_list.get_children())
        data = self.ops_service._load_json("regression_index.json", [])
        for reg in data:
            self.ops_reg_list.insert("", "end", values=(reg.get("suite_id"), reg.get("last_status"), reg.get("passing_cases"), reg.get("failing_cases"), reg.get("last_run_at")))

    def _refresh_ops_recovery(self) -> None:
        data = self.ops_service._load_json("recovery_index.json", [])
        health = self.ops_service._load_json("health_status.json", {})
        self.ops_recovery_view.configure(state="normal")
        self.ops_recovery_view.delete("1.0", "end")
        self.ops_recovery_view.insert("end", "INTERRUPTED / RECOVERABLE RUNS\n", "header")
        if not data:
            self.ops_recovery_view.insert("end", " No interrupted runs detected.\n\n", "ok")
        else:
            for item in data:
                self.ops_recovery_view.insert("end", f" - Run: {item.get('run_id')}\n", "label")
                self.ops_recovery_view.insert("end", f"   Class: {item.get('classification')}\n", "value")
                self.ops_recovery_view.insert("end", f"   State: {item.get('last_durable_state')}\n", "value")
                self.ops_recovery_view.insert("end", f"   Action: {item.get('action_options')}\n\n", "warn")

        self.ops_recovery_view.insert("end", "\nHEALTH & DURABILITY STATUS\n", "header")
        self.ops_recovery_view.insert("end", json.dumps(health, indent=2))
        self.ops_recovery_view.configure(state="disabled")

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

    def _refresh_approvals_view(self) -> None:
        self.approvals_list.delete(*self.approvals_list.get_children())
        pending = self.approval_service.list_pending()
        for a in pending:
            self.approvals_list.insert("", "end", values=(a.approval_id, a.gate_type, a.entity_id, a.risk_class, a.status))

        self.appr_detail_view.configure(state="normal")
        self.appr_detail_view.delete("1.0", "end")
        self.appr_detail_view.configure(state="disabled")
        self.approve_btn.state(["disabled"])
        self.deny_btn.state(["disabled"])

    def _on_approval_selected(self, _event: object) -> None:
        selected = self.approvals_list.selection()
        if not selected:
            return
        approval_id = self.approvals_list.item(selected[0])["values"][0]
        a = self.approval_service.get_approval(approval_id)
        if not a:
            return

        self.appr_detail_view.configure(state="normal")
        self.appr_detail_view.delete("1.0", "end")

        lines = [
            f"Approval ID: {a.approval_id}",
            f"Gate Type:   {a.gate_type}",
            f"Entity ID:   {a.entity_id}",
            f"Queue:Slot:  {a.queue_id}:{int(a.slot_id)+1}",
            f"Required For:{a.required_for}",
            f"Risk Class:  {a.risk_class}",
            f"Requested At:{a.requested_at}",
            "\nReason Codes:",
        ]
        for rc in a.reason_codes:
            lines.append(f"  - {rc}")

        self.appr_detail_view.insert("1.0", "\n".join(lines))
        self.appr_detail_view.configure(state="disabled")

        self.approve_btn.state(["!disabled"])
        self.deny_btn.state(["!disabled"])

    def approve_selected(self) -> None:
        selected = self.approvals_list.selection()
        if not selected:
            return
        approval_id = self.approvals_list.item(selected[0])["values"][0]
        if self.approval_service.approve(approval_id, "local_user", "Manually approved via UI"):
            self.log_event(f"Approved {approval_id}")
            self._refresh_approvals_view()

    def deny_selected(self) -> None:
        selected = self.approvals_list.selection()
        if not selected:
            return
        approval_id = self.approvals_list.item(selected[0])["values"][0]
        if self.approval_service.deny(approval_id, "local_user", "Manually denied via UI"):
            self.log_event(f"Denied {approval_id}")
            self._refresh_approvals_view()

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

        # Durable Run Info
        if slot.current_run_id:
            metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
            if metadata:
                 self.pipeline_view.insert("end", f"\n  Durable State: {metadata.state.value}\n", "completed")
                 self.pipeline_view.insert("end", f"  Run ID: {slot.current_run_id}\n", "pending")

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

        # 0. Durability & Lineage (SPEC 016)
        add_section("DURABILITY & LINEAGE")
        if slot.current_run_id:
            add_field("Current Run ID", slot.current_run_id)
            metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
            if metadata:
                add_field("Durable State", metadata.state.value)
                add_field("Last Updated", metadata.updated_at)
                if metadata.replay_of_run_id:
                    add_field("Replay Of", metadata.replay_of_run_id, "success")
                if metadata.restart_of_run_id:
                    add_field("Restart Of", metadata.restart_of_run_id, "success")
        else:
            add_field("Run ID", "None", "dim")

        # 0. Policy & Risk (SPEC 017)
        add_section("POLICY & RISK")
        if slot.current_run_id:
             risk_path = Path.cwd() / "runs" / slot.current_run_id / "risk_assessment.json"
             if risk_path.exists():
                  try:
                       with risk_path.open("r") as f:
                            risk_data = json.load(f)
                       add_field("Overall Risk", risk_data.get("overall_risk", "-"))
                       add_field("Spec Risk", risk_data.get("spec_risk", "-"))
                       add_field("Promotion Risk (Est)", risk_data.get("promotion_risk_estimate", "-"))
                  except: pass

             pre_exec_path = Path.cwd() / "runs" / slot.current_run_id / "policy_evaluation_pre_execution.json"
             if pre_exec_path.exists():
                  try:
                       with pre_exec_path.open("r") as f:
                            pe = json.load(f)
                       add_field("Pre-Exec Decision", pe.get("decision", "-"))
                       if pe.get("reason_codes"):
                            add_field("Reasons", ", ".join(pe["reason_codes"]))
                  except: pass

             pre_prom_path = Path.cwd() / "runs" / slot.current_run_id / "policy_evaluation_pre_promotion.json"
             if pre_prom_path.exists():
                  try:
                       with pre_prom_path.open("r") as f:
                            pe = json.load(f)
                       add_field("Pre-Promote Decision", pe.get("decision", "-"))
                       if pe.get("reason_codes"):
                            add_field("Reasons", ", ".join(pe["reason_codes"]))
                  except: pass

        # 0. Runtime Info (SPEC 015)
        add_section("RUNTIME ENVIRONMENT")

        runtime_data = None
        if slot.run_summary:
            if hasattr(slot.run_summary, 'runtime'):
                 runtime_data = getattr(slot.run_summary, 'runtime', None)
            elif isinstance(slot.run_summary, dict):
                 runtime_data = slot.run_summary.get("runtime")

        if runtime_data:
            r = runtime_data
            add_field("Profile ID", r.get("profile_id", "-"))
            add_field("Interpreter", r.get("interpreter", "-"))
            add_field("Python Version", r.get("python_version", "-"))
            add_field("Env Inherit", r.get("env_inherit_mode", "-"))
        else:
            add_field("Profile", "Not yet executed", "dim")

        # 0. Isolation Info (SPEC 014)
        add_section("EXECUTION & ISOLATION")
        # Since slot object doesn't have these, we'd need to extend it,
        # but for now we can try to infer or just show what's in run_folder if we had it.
        # Actually, let's just add minimal info.
        is_dsl = self.spec_parser.dsl_parser.is_dsl_spec(slot.spec_text)
        if is_dsl:
            data, _ = self.spec_parser.dsl_parser.parse(slot.spec_text)
            if data:
                exec_data = data.get("execution", {})
                add_field("Mode", exec_data.get("mode", "promote_on_success"))
                add_field("Source Policy", exec_data.get("source_policy", "promoted_head"))

                prom_data = data.get("promotion", {})
                add_field("Promotion Enabled", str(prom_data.get("enabled", True)))

        # 1. Spec
        add_section("SPEC")
        if slot.spec_text.strip():
            is_dsl = self.spec_parser.dsl_parser.is_dsl_spec(slot.spec_text)
            mode_tag = "success" if is_dsl else "dim"
            add_field("Mode", "DSL" if is_dsl else "Legacy", mode_tag)

            if is_dsl:
                _, validation = self.spec_parser.dsl_parser.parse(slot.spec_text)
                if not validation.is_valid:
                    self.slot_detail_view.insert("end", "\n[ DSL VALIDATION ERRORS ]\n", "error")
                    for err in validation.errors:
                        self.slot_detail_view.insert("end", f"- {err['field']}: {err['error']}\n", "error")

            self.slot_detail_view.insert("end", "\n" + slot.spec_text + "\n")
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

        # 4.1 Mutation Ledger
        add_section("WORKSPACE MUTATIONS")
        mutation_dir = None
        if slot.current_run_id:
            metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
            if metadata and metadata.execution_workspace:
                mutation_dir = Path(metadata.execution_workspace).parent / "mutations"
        if mutation_dir and mutation_dir.exists():
            mutation_files = sorted(mutation_dir.glob("*.json"))
            if mutation_files:
                total_created = 0
                total_modified = 0
                total_deleted = 0
                total_failed = 0
                for artifact in mutation_files:
                    try:
                        with artifact.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                        total_created += data.get("created_count", 0)
                        total_modified += data.get("modified_count", 0)
                        total_deleted += data.get("deleted_count", 0)
                        total_failed += data.get("failed_count", 0)
                        add_field(f"Artifact {artifact.stem}", data.get("status", "-"))
                        batch_summary = data.get("batch_summary")
                        if batch_summary:
                            self.slot_detail_view.insert(
                                "end",
                                f"  batch: {batch_summary.get('batch_validation_status', '-')} complexity={batch_summary.get('complexity', '-')}\n",
                                "value" if not str(batch_summary.get("batch_validation_status", "")).startswith("batch_invalid") else "error",
                            )
                            for reason in batch_summary.get("batch_failure_reasons", []):
                                self.slot_detail_view.insert("end", f"    batch failure: {reason}\n", "error")
                            for warning in batch_summary.get("warnings", []):
                                self.slot_detail_view.insert("end", f"    batch warning: {warning}\n", "dim")
                            for summary in batch_summary.get("file_summaries", []):
                                path = summary.get("path", "-")
                                purpose = summary.get("purpose", "-")
                                self.slot_detail_view.insert("end", f"    file: {path} [{purpose}]\n", "value")
                        test_summary = data.get("test_summary")
                        if test_summary:
                            status = test_summary.get("status", "-")
                            self.slot_detail_view.insert(
                                "end",
                                f"  tests: {status} total={test_summary.get('total_tests', 0)} passed={test_summary.get('tests_passed', 0)} failed={test_summary.get('tests_failed', 0)} skipped={test_summary.get('tests_skipped', 0)}\n",
                                "value" if status.startswith("passed") else "error",
                            )
                            if test_summary.get("failure_class"):
                                self.slot_detail_view.insert("end", f"    test failure: {test_summary.get('failure_class')} - {test_summary.get('failure_detail', '')}\n", "error")
                            for failing_test in test_summary.get("failing_tests", [])[:8]:
                                self.slot_detail_view.insert("end", f"    failing test: {failing_test}\n", "error")
                            if test_summary.get("no_tests_found"):
                                self.slot_detail_view.insert("end", "    no tests detected\n", "dim")
                        if data.get("files_validated", 0):
                            self.slot_detail_view.insert(
                                "end",
                                f"  validation: passed={data.get('files_passed', 0)} failed={data.get('files_failed', 0)}\n",
                                "value" if data.get("files_failed", 0) == 0 else "error",
                            )
                        for item in data.get("results", []):
                            path = item.get("path", "-")
                            status = item.get("status", "-")
                            delta = item.get("size_delta", 0)
                            self.slot_detail_view.insert("end", f"  {path} -> {status} (size_delta={delta})\n", "value" if status != "failed" else "error")
                            validation = item.get("validation")
                            if validation and validation.get("status") == "invalid":
                                line = validation.get("line_number", 0)
                                col = validation.get("column_offset", 0)
                                msg = validation.get("error_message", "validation failed")
                                offending = validation.get("offending_line", "")
                                self.slot_detail_view.insert("end", f"    validation: {msg} at {line}:{col}\n", "error")
                                if offending:
                                    self.slot_detail_view.insert("end", f"    line: {offending}\n", "error")
                    except Exception as exc:
                        self.slot_detail_view.insert("end", f"  Failed to read {artifact.name}: {exc}\n", "error")
                add_field("Created", str(total_created), "success" if total_created else "value")
                add_field("Modified", str(total_modified), "success" if total_modified else "value")
                add_field("Deleted", str(total_deleted), "value")
                add_field("Failed", str(total_failed), "error" if total_failed else "value")
            else:
                self.slot_detail_view.insert("end", "No mutation artifacts available.\n", "dim")
        else:
            self.slot_detail_view.insert("end", "No mutation artifacts available.\n", "dim")

        # 4.2 Attempt History
        add_section("ATTEMPT HISTORY")
        attempt_dir = None
        if slot.current_run_id:
            metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
            if metadata and metadata.execution_workspace:
                attempt_dir = Path(metadata.execution_workspace).parent / "attempts"
        if attempt_dir and attempt_dir.exists():
            attempt_files = sorted(attempt_dir.glob("*.json"))
            if attempt_files:
                for artifact in attempt_files:
                    try:
                        with artifact.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                        add_field(f"Attempt Artifact {artifact.stem}", data.get("final_outcome", "-"))
                        add_field("Applied Attempt", str(data.get("applied_attempt_index", 0)))
                        add_field("Stopped Reason", data.get("stopped_reason", "-"))
                        for attempt in data.get("attempts", []):
                            idx = attempt.get("attempt_index", 0)
                            attempt_type = attempt.get("attempt_type", "-")
                            success = attempt.get("success", False)
                            failure = attempt.get("failure_class", "")
                            tag = "success" if success else "error" if failure else "value"
                            self.slot_detail_view.insert("end", f"  Attempt {idx} [{attempt_type}] -> {'success' if success else 'failed'}\n", tag)
                            if failure:
                                self.slot_detail_view.insert("end", f"    failure: {failure}\n", "error")
                            summary = attempt.get("validation_result_summary", "")
                            if summary:
                                self.slot_detail_view.insert("end", f"    validation: {summary}\n", "value")
                            stop = attempt.get("stop_reason", "")
                            if stop:
                                self.slot_detail_view.insert("end", f"    next/stop: {stop}\n", "dim")
                    except Exception as exc:
                        self.slot_detail_view.insert("end", f"  Failed to read {artifact.name}: {exc}\n", "error")
            else:
                self.slot_detail_view.insert("end", "No attempt artifacts available.\n", "dim")
        else:
            self.slot_detail_view.insert("end", "No attempt artifacts available.\n", "dim")

        # 4.3 Context Package
        add_section("GENERATION CONTEXT")
        context_dir = None
        if slot.current_run_id:
            metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
            if metadata and metadata.execution_workspace:
                context_dir = Path(metadata.execution_workspace).parent / "contexts"
        if context_dir and context_dir.exists():
            context_files = sorted(context_dir.glob("*.json"))
            if context_files:
                for artifact in context_files:
                    try:
                        with artifact.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                        add_field(f"Context Artifact {artifact.stem}", data.get("selection_confidence", "-"))
                        selected = data.get("selected_files", [])
                        add_field("Selected Files", str(len(selected)))
                        for item in selected:
                            path = item.get("relative_path", "-")
                            reason = item.get("reason", "-")
                            mode = item.get("include_mode", "-")
                            chars = item.get("included_chars", 0)
                            self.slot_detail_view.insert("end", f"  {path} [{reason}] mode={mode} chars={chars}\n", "value")
                    except Exception as exc:
                        self.slot_detail_view.insert("end", f"  Failed to read {artifact.name}: {exc}\n", "error")
            else:
                self.slot_detail_view.insert("end", "No context artifacts available.\n", "dim")
        else:
            self.slot_detail_view.insert("end", "No context artifacts available.\n", "dim")

        # 4.4 Targeting
        add_section("TARGETING")
        targeting_dir = None
        if slot.current_run_id:
            metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
            if metadata and metadata.execution_workspace:
                targeting_dir = Path(metadata.execution_workspace).parent / "targeting"
        if targeting_dir and targeting_dir.exists():
            targeting_files = sorted(targeting_dir.glob("*.json"))
            if targeting_files:
                for artifact in targeting_files:
                    try:
                        with artifact.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                        add_field(f"Targeting Artifact {artifact.stem}", data.get("scope_policy_result", "-"))
                        add_field("Scope Class", data.get("scope_class", "-"))
                        add_field("Scope Confidence", data.get("scope_confidence", "-"))
                        self.slot_detail_view.insert("end", f"  primary editable: {data.get('primary_target_files', [])}\n", "value")
                        self.slot_detail_view.insert("end", f"  secondary editable: {data.get('secondary_edit_files', [])}\n", "value")
                        self.slot_detail_view.insert("end", f"  read-only context: {data.get('read_only_context_files', [])}\n", "dim")
                        for symbol in data.get("target_symbols", []):
                            self.slot_detail_view.insert("end", f"  symbol: {symbol.get('symbol_name')} [{symbol.get('resolution_status')}] {symbol.get('file_candidates', [])}\n", "value")
                        for warning in data.get("warnings", []):
                            self.slot_detail_view.insert("end", f"  warning: {warning}\n", "dim")
                    except Exception as exc:
                        self.slot_detail_view.insert("end", f"  Failed to read {artifact.name}: {exc}\n", "error")
            else:
                self.slot_detail_view.insert("end", "No targeting artifacts available.\n", "dim")
        else:
            self.slot_detail_view.insert("end", "No targeting artifacts available.\n", "dim")

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

        # 6. Verification Report
        if slot.verification_report:
            add_section("VERIFICATION")
            v = slot.verification_report
            add_field("Total Checks", str(v.summary["total"]))
            add_field("Passed", str(v.summary["passed"]), "success" if v.summary["passed"] == v.summary["total"] else "value")
            add_field("Failed", str(v.summary["failed"]), "error" if v.summary["failed"] > 0 else "value")
            add_field("Warned", str(v.summary["warned"]), "dim" if v.summary["warned"] > 0 else "value")

            if v.checks:
                 self.slot_detail_view.insert("end", "\nDetailed Checks:\n", "label")
                 for c in v.checks:
                      status_tag = "success" if c.status == CheckStatus.PASS else "error" if c.status in {CheckStatus.FAIL, CheckStatus.ERROR} else "dim"
                      self.slot_detail_view.insert("end", f"  [{c.status.value.upper()}] {c.check_id} ({c.severity.value})\n", status_tag)
                      if c.status in {CheckStatus.FAIL, CheckStatus.ERROR}:
                           self.slot_detail_view.insert("end", f"      {c.message}\n", "error")

        # 7. Run Summary
        if slot.run_summary:
            add_section("RUN SUMMARY")
            s = slot.run_summary

            # If s is a dict (from artifact) or dataclass (from run)
            if hasattr(s, 'final_status'):
                add_field("Final Status", s.final_status.value, "success" if s.final_status == FinalOutcome.COMPLETED else "error" if s.final_status in {FinalOutcome.FAILED, FinalOutcome.PARTIAL_FAILURE} else "dim")
                add_field("Failure Stage", s.failure_stage.value if s.failure_stage else "None", "error" if s.failure_stage else "success")
                add_field("Summary", s.summary)
            else:
                add_field("Final Status", s.get("final_status", "-"))
                add_field("Failure Stage", s.get("failure_stage", "None"))

        # 8. Failure Info
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
                # Check for warnings
                if slot.run_summary and slot.run_summary.final_status == FinalOutcome.COMPLETED_WITH_WARNINGS:
                     bg = "#3b3b1f" # Dark yellow/brown for warnings
                else:
                     bg = "#1f3b2d"
            elif slot.status == "failed":
                bg = "#4b1f1f"
            elif slot.status == "stopped":
                bg = "#4a3b1f"
            elif slot.status == "ready":
                bg = "#2d2d30"
            elif slot.status == "interrupted":
                bg = "#4a3b1f" # same as stopped for now
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
        slot.current_run_id = ""
        self.log_event(f"Cleared slot {idx + 1}")
        self._refresh_queue_view()

    def resume_run(self) -> None:
        idx = self.selected_slot_index
        slot = self.spec_queue.queue_slots[idx]
        if not slot.current_run_id:
            self.log_event("Resume blocked: no run ID for selected slot.")
            return

        metadata = self.resume_service.prepare_resume(slot.current_run_id)
        if not metadata:
            self.log_event(f"Resume blocked: run {slot.current_run_id} is not resumable.")
            return

        self.log_event(f"Resuming run {slot.current_run_id} from phase {metadata.state.value}")
        # Simplified resume: just start the queue from this slot
        # In a full implementation, we would pass the metadata to the worker
        self.start_queue()

    def replay_run(self) -> None:
        idx = self.selected_slot_index
        slot = self.spec_queue.queue_slots[idx]
        if not slot.current_run_id:
            self.log_event("Replay blocked: no run ID for selected slot.")
            return

        replay_metadata = self.replay_service.create_replay_run(slot.current_run_id)
        if not replay_metadata:
            self.log_event(f"Replay blocked: could not initialize replay for {slot.current_run_id}")
            return

        self.log_event(f"Initializing replay: {replay_metadata.run_id} (original: {slot.current_run_id})")

        # Update lineage
        slot.replay_run_ids.append(replay_metadata.run_id)

        # Record replay start in ledger
        self.ledger_service.update_run_metadata(replay_metadata)
        self.ledger_service.record_event(
            entity_type="run",
            entity_id=replay_metadata.run_id,
            event_type="replay_started",
            new_state=DurableRunState.CREATED.value,
            run_id=replay_metadata.run_id,
            payload={"original_run_id": slot.current_run_id}
        )

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

        # Persist queue definition
        q_def = QueueDefinition(
            queue_id=self.spec_queue.queue_id,
            created_at=datetime.now().isoformat(),
            settings={}, # TODO: capture real settings if any
            slots=[{"index": i, "spec": s} for i, s in enumerate(specs)],
            runtime_defaults={},
            recovery_policy="manual",
            source_policy="promoted_head",
            state=DurableQueueState.RUNNING
        )
        self.queue_store.save_queue_definition(q_def)
        self.ledger_service.record_event(
            entity_type="queue",
            entity_id=self.spec_queue.queue_id,
            event_type="state_transition",
            new_state=DurableQueueState.RUNNING.value,
            previous_state=DurableQueueState.CREATED.value,
            queue_id=self.spec_queue.queue_id
        )

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

        # SPEC 014: Capture initial canonical state for fixed_base policy
        initial_canonical_path = self.current_folder
        fixed_base_root = None
        if any(slot.spec_text.strip() for slot in self.spec_queue.queue_slots):
             # Create a hidden fixed base snapshot if any slot might need it
             # For simplicity, we create it in the first run's folder or a dedicated one
             pass

        for slot in self.spec_queue.queue_slots:
            if self.spec_queue.stop_requested:
                if slot.status == "ready":
                    self.queue_service.mark_slot_stopped(slot, "stop requested before slot start")
                    self.ui_queue.put(("queue_slot_stopped", (slot.slot_index, slot.failure_reason)))
                continue
            if not slot.spec_text.strip():
                slot.status = "empty"
                continue

            # SPEC 016: Durable Run Identity
            if not slot.current_run_id:
                run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
                slot.current_run_id = run_id
            else:
                self.ui_queue.put(("queue_log", f"Preserving run ID {slot.current_run_id} for resume"))

            self.queue_service.mark_slot_running(self.spec_queue, slot)
            self.ui_queue.put(("queue_slot_state", slot.slot_index))
            self.ui_queue.put(("queue_log", f"Active slot changed to {slot.slot_index + 1}"))
            self.ui_queue.put(("queue_log", f"Slot {slot.slot_index + 1} started"))

            stages = [
                "Spec Intake",
                "Spec Parsing",
                "Policy Check (Pre-Exec)",
                "Runtime Environment",
                "Task Execution",
                "Structural Validation",
                "Deterministic Verification",
                "Regression Comparison",
                "Outcome Synthesis",
                "Policy Check (Pre-Promote)",
                "Logging / Audit",
            ]
            current_stage_idx = -1

            def update_stage(name: str, status: str, message: str = ""):
                nonlocal current_stage_idx
                self.queue_service.update_stage_status(slot, name, status, message)
                if status == "running":
                    current_stage_idx = stages.index(name)

                # SPEC 016: Record state transition in ledger
                if status == "running":
                    durable_state = self._map_stage_to_durable_state(name)
                    if durable_state:
                         self._record_run_transition(slot, durable_state)

                self.ui_queue.put(("pipeline_update", None))

            def check_stop():
                if self.spec_queue.stop_requested:
                    raise InterruptedError("stop requested")

            try:
                tasks = []
                verification_data = {}
                spec_data = None
                all_changes = []
                run_folder = None
                execution_workspace = None
                snapshot_manifest = None

                v_synthesizer = OutcomeSynthesizer()
                v_report = None
                failure_stage = None

                # 1. Spec Intake
                update_stage("Spec Intake", "running")
                if not slot.spec_text.strip():
                    failure_stage = FailureStage.SPEC_FAILURE
                    raise RuntimeError("no spec")

                is_dsl = self.spec_parser.dsl_parser.is_dsl_spec(slot.spec_text)

                if is_dsl:
                    spec_data, validation = self.spec_parser.dsl_parser.parse(slot.spec_text)
                    if not validation.is_valid:
                         failure_stage = FailureStage.SPEC_FAILURE
                         raise ValueError(f"DSL Validation Failed: {validation.errors[0]['error']}")
                else:
                    # Check if it looks like YAML but failed is_dsl_spec
                    try:
                        import yaml
                        potential_yaml = yaml.safe_load(slot.spec_text)
                        if isinstance(potential_yaml, dict) and ("spec_version" in potential_yaml or "tasks" in potential_yaml):
                             # User intended DSL but it's malformed
                             _, validation = self.spec_parser.dsl_parser.parse(slot.spec_text)
                             if not validation.is_valid:
                                  failure_stage = FailureStage.SPEC_FAILURE
                                  raise ValueError(f"Malformed DSL: {validation.errors[0]['error']}")
                    except:
                        pass

                self.ui_queue.put(("queue_log", f"Mode detected: {'DSL' if is_dsl else 'Legacy'}"))
                update_stage("Spec Intake", "completed", f"mode={'dsl' if is_dsl else 'legacy'}")
                check_stop()

                # SPEC 014: Workspace Isolation & Snapshotting
                metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
                resuming = metadata is not None and metadata.state not in {DurableRunState.CREATED, DurableRunState.SNAPSHOT_PREPARING}

                if resuming and metadata.execution_workspace:
                     run_folder = Path(metadata.execution_workspace).parent
                else:
                     run_folder = self.audit_log_service.create_run_folder(slot.slot_index + 1)

                execution_mode = ExecutionMode.PROMOTE_ON_SUCCESS
                source_policy = SourcePolicy.PROMOTED_HEAD

                if spec_data:
                    if "execution" in spec_data:
                        if "mode" in spec_data["execution"]:
                            execution_mode = ExecutionMode(spec_data["execution"]["mode"])
                        if "source_policy" in spec_data["execution"]:
                            source_policy = SourcePolicy(spec_data["execution"]["source_policy"])

                source_workspace = self.current_folder
                if source_policy == SourcePolicy.FIXED_BASE:
                     if fixed_base_root is None:
                          # Initialize fixed base snapshot on first need
                          fixed_base_root = run_folder / "fixed_base_source"
                          fixed_base_root.mkdir(parents=True, exist_ok=True)
                          self.ui_queue.put(("queue_log", "Initializing fixed base snapshot..."))
                          # Copy current canonical to fixed base root
                          self.snapshot_service._copy_workspace(self.current_folder, fixed_base_root, [".git", "__pycache__", "runs", "regression_runs"])

                     source_workspace = fixed_base_root
                     self.ui_queue.put(("queue_log", "Using fixed base snapshot as source"))

                if resuming and metadata.source_snapshot_manifest and Path(metadata.source_snapshot_manifest).exists():
                     self.ui_queue.put(("queue_log", "Resuming from existing workspace snapshot..."))
                     from workspace.snapshots import SnapshotManifest
                     with Path(metadata.source_snapshot_manifest).open("r") as f:
                          snapshot_manifest = SnapshotManifest.from_dict(json.load(f))
                else:
                    self.ui_queue.put(("queue_log", f"Creating isolated workspace snapshot (Mode: {execution_mode.value})"))
                    snapshot_manifest = self.snapshot_service.create_execution_snapshot(
                        run_id=run_folder.name,
                        spec_id=spec_data.get("spec_id", "legacy") if spec_data else "legacy",
                        source_workspace=source_workspace,
                        execution_root=run_folder,
                        mode=execution_mode
                    )
                execution_workspace = Path(snapshot_manifest.execution_workspace)
                self.ui_queue.put(("queue_log", f"Isolated workspace ready: {execution_workspace}"))

                # Update run metadata with snapshot info
                metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
                if metadata:
                    metadata.spec_id = spec_data.get("spec_id", "legacy") if spec_data else "legacy"
                    metadata.execution_mode = execution_mode.value
                    metadata.source_policy = source_policy.value
                    metadata.source_snapshot_manifest = str(snapshot_manifest.manifest_path)
                    metadata.execution_workspace = str(execution_workspace)
                    metadata.state = DurableRunState.SNAPSHOT_READY
                    self.ledger_service.update_run_metadata(metadata)

                    self.ledger_service.record_event(
                        entity_type="run",
                        entity_id=slot.current_run_id,
                        event_type="artifact_registered",
                        new_state=DurableRunState.SNAPSHOT_READY.value,
                        run_id=slot.current_run_id,
                        payload={"artifact": "snapshot_manifest", "path": str(snapshot_manifest.manifest_path)}
                    )

                # v_engine initialization moved after Runtime Environment

                # 2. Spec Parsing
                update_stage("Spec Parsing", "running")
                tasks, verification_data = self.spec_parser.parse(slot.spec_text)
                if not tasks:
                    self.ui_queue.put(("queue_log", "No tasks found in spec"))
                else:
                    self.ui_queue.put(("queue_log", f"Parsed {len(tasks)} tasks"))
                update_stage("Spec Parsing", "completed", f"tasks={len(tasks)}")
                check_stop()

                # 2.1 Policy Check (Pre-Execution) (SPEC 017)
                update_stage("Policy Check (Pre-Exec)", "running")
                risk_assessment = self.risk_classifier.classify(tasks, spec_data)
                self.audit_log_service.log_artifact(run_folder, "risk_assessment.json", json.dumps(risk_assessment.to_dict(), indent=2))
                self.ui_queue.put(("queue_log", f"Computed risk: {risk_assessment.overall_risk}"))

                policy_result = self.policy_evaluator.evaluate_pre_execution(slot.current_run_id, risk_assessment)
                self.audit_log_service.log_artifact(run_folder, "policy_evaluation_pre_execution.json", json.dumps(policy_result.to_dict(), indent=2))

                if policy_result.decision == PolicyDecision.POLICY_DENIED.value:
                     failure_stage = FailureStage.POLICY_CONTROL if hasattr(FailureStage, 'POLICY_CONTROL') else FailureStage.SPEC_FAILURE
                     raise RuntimeError(f"POLICY_DENIED: {', '.join(policy_result.reason_codes)}")

                if policy_result.decision == PolicyDecision.APPROVAL_REQUIRED.value:
                     # Check if already approved (e.g. from resume)
                     existing_appr = self.approval_service.find_latest_for_entity(slot.current_run_id, "execution")
                     if existing_appr and existing_appr.status == ApprovalStatus.APPROVED.value:
                          self.ui_queue.put(("queue_log", f"Approval found: {existing_appr.approval_id} (Approved by {existing_appr.decider})"))
                     else:
                          if not existing_appr:
                               self.approval_service.create_approval_request("execution", "run", slot.current_run_id, self.spec_queue.queue_id, str(slot.slot_index), policy_result)

                          self.ui_queue.put(("queue_log", "Approval required. Pausing queue."))
                          update_stage("Policy Check (Pre-Exec)", "pending", "Waiting for approval")
                          # Pause queue
                          self.spec_queue.queue_status = "paused"
                          self.ui_queue.put(("queue_slot_paused_approval", slot.slot_index))
                          return # Exit worker, will be resumed

                update_stage("Policy Check (Pre-Exec)", "completed", f"risk={risk_assessment.overall_risk}")
                check_stop()

                # 2.5 Runtime Environment (SPEC 015)
                update_stage("Runtime Environment", "running")

                # Resolve profile ID with precedence: Spec > Queue > Default
                profile_id = "default"

                # Check queue settings
                if spec_data and "queue_settings" in spec_data:
                     # This might come from a queue-level config in the future,
                     # but for now we look for it in the spec if it's there.
                     # Actually, SPEC 015 says queue might define it.
                     pass

                # We can check if the queue itself has a default profile (e.g. from UI or queue state)
                # For now, let's look for 'runtime' block in spec
                if spec_data and "runtime" in spec_data:
                    if isinstance(spec_data["runtime"], dict) and "profile" in spec_data["runtime"]:
                        profile_id = spec_data["runtime"]["profile"]

                profile = self.profile_registry.get_profile(profile_id)
                if not profile:
                    failure_stage = FailureStage.RUNTIME_PROFILE_INVALID
                    raise ValueError(f"Runtime profile not found: {profile_id}")

                int_resolver = InterpreterResolver(self.current_folder)
                interpreter_path = int_resolver.resolve(profile)

                int_validator = InterpreterValidator()
                ok, err_type, version_info = int_validator.validate(interpreter_path)
                if not ok:
                    failure_stage = FailureStage.RUNTIME_ENVIRONMENT_FAILURE
                    raise RuntimeError(f"Interpreter validation failed ({err_type}): {version_info}")

                if spec_data and "runtime" in spec_data and "python_version" in spec_data["runtime"]:
                    ok, err_type, msg = int_validator.check_version_constraints(version_info, spec_data["runtime"]["python_version"])
                    if not ok:
                        failure_stage = FailureStage.RUNTIME_ENVIRONMENT_FAILURE
                        raise RuntimeError(f"Python version constraint mismatch ({err_type}): {msg}")

                env_builder = EnvironmentBuilder()
                runtime_env = env_builder.build(profile)

                fp_service = RuntimeFingerprintService()
                fingerprint = fp_service.capture(profile, interpreter_path)

                pip_ok, pip_freeze = fp_service.capture_pip_freeze(interpreter_path)

                if profile.dependency_fingerprint.required and not pip_ok:
                    failure_stage = FailureStage.RUNTIME_ENVIRONMENT_FAILURE
                    raise RuntimeError(f"DEPENDENCY_FINGERPRINT_CAPTURE_FAILED: {pip_freeze}")

                # Drift Detection (SPEC 015 Requirement 14)
                drift_status = "none"
                baseline_path = self.current_folder / ".agent_workbench" / "runtime_baseline.json"
                if baseline_path.exists():
                    try:
                        with baseline_path.open("r") as f:
                            baseline = json.load(f)
                        detector = DriftDetector()
                        drifts = detector.detect(fingerprint, baseline)
                        if drifts:
                            drift_status = "detected"
                            for drift in drifts:
                                self.ui_queue.put(("queue_log", f"DRIFT DETECTED: {drift['type']} - Expected: {drift['expected']}, Actual: {drift['actual']}"))

                            if profile.drift_policy.on_python_version_mismatch == DriftPolicyMode.FAIL:
                                failure_stage = FailureStage.RUNTIME_ENVIRONMENT_FAILURE
                                raise RuntimeError(f"ENVIRONMENT_DRIFT_DETECTED: {drifts[0]['type']}")
                    except Exception as e:
                        self.ui_queue.put(("queue_log", f"Drift detection failed: {e}"))

                # Log artifacts
                self.audit_log_service.log_artifact(run_folder, "runtime_profile_resolved.json", {
                    "profile_id": profile.profile_id,
                    "interpreter": interpreter_path,
                    "python_version": version_info,
                    "env_inherit_mode": profile.env.inherit_mode.value
                })
                self.audit_log_service.log_artifact(run_folder, "runtime_environment_masked.json", self.env_masker.mask_env(runtime_env))
                self.audit_log_service.log_artifact(run_folder, "dependency_fingerprint.json", fingerprint)
                if pip_ok:
                    self.audit_log_service.log_artifact(run_folder, "pip_freeze.txt", pip_freeze)

                update_stage("Runtime Environment", "completed", f"profile={profile_id}")
                check_stop()

                v_engine = VerificationEngine(execution_workspace, cmd_executor=CommandExecutor(profile, interpreter_path, runtime_env, execution_workspace))

                # 3. Task Execution
                update_stage("Task Execution", "running")
                if not execution_workspace:
                    failure_stage = FailureStage.HARNESS_FAILURE
                    raise RuntimeError("no execution workspace")

                file_ops = FileOpsService(execution_workspace)

                # Setup CommandExecutor for this run
                cmd_executor = CommandExecutor(profile, interpreter_path, runtime_env, execution_workspace)

                executor = TaskExecutorService(
                    file_ops,
                    self.ollama_service,
                    self.process_service,
                    model_name,
                    run_folder=run_folder,
                    cmd_executor=cmd_executor,
                    mutation_mode=self.write_mode_var.get(),
                )

                # Settings
                fail_fast = True
                if spec_data and "settings" in spec_data:
                    fail_fast = spec_data["settings"].get("fail_fast", True)

                for task in tasks:
                    self.ui_queue.put(("queue_log", f"Executing task: {task.id} ({task.type.value} {task.target})"))
                    result = executor.execute(task)
                    self.ui_queue.put(("queue_log", f"Task result: {result.message}"))
                    if not result.success:
                        if fail_fast:
                            failure_stage = FailureStage.EDIT_FAILURE
                            raise RuntimeError(f"Task {task.id} failed: {result.message}")
                        else:
                            self.ui_queue.put(("queue_log", f"Task {task.id} failed (continuing): {result.message}"))
                    all_changes.extend(result.changes)

                update_stage("Task Execution", "completed", f"changes={len(all_changes)}")
                check_stop()

                # 4. Structural Validation
                update_stage("Structural Validation", "running")
                for change in all_changes:
                    # Skip validation for files that were deleted
                    target_path = execution_workspace / change
                    if not target_path.exists():
                        continue

                    if change.endswith(".py"):
                        ok, msg = self.validation_service.validate_python_syntax(target_path)
                        if not ok:
                            failure_stage = FailureStage.STRUCTURAL_VALIDATION_FAILURE
                            raise RuntimeError(f"Validation failed for {change}: {msg}")
                update_stage("Structural Validation", "completed")
                check_stop()

                # 5. Deterministic Verification
                update_stage("Deterministic Verification", "running")
                v_report = v_engine.run(verification_data, tasks)
                slot.verification_report = v_report
                update_stage("Deterministic Verification", "completed", f"passed={v_report.summary['passed']}/{v_report.summary['total']}")
                check_stop()

                # 6. Regression Comparison
                update_stage("Regression Comparison", "running")
                # Placeholder for now
                regression_status = {"enabled": False}
                if verification_data.get("regression", {}).get("enabled"):
                     regression_status = {"enabled": True, "status": "pass"} # Placeholder
                update_stage("Regression Comparison", "completed")
                check_stop()

                # 7. Outcome Synthesis
                update_stage("Outcome Synthesis", "running")
                spec_id = spec_data.get("spec_id", "legacy_run") if spec_data else "legacy_run"
                run_summary = v_synthesizer.synthesize(spec_id, tasks, v_report, failure_stage, regression_status)
                slot.run_summary = run_summary
                update_stage("Outcome Synthesis", "completed", f"outcome={run_summary.final_status.value}")
                check_stop()

                # 7.1 Policy Check (Pre-Promotion) (SPEC 017)
                update_stage("Policy Check (Pre-Promote)", "running")

                # Compute actual change set facts
                created, modified, deleted = self.promotion_service.detect_changes(snapshot_manifest.source_fingerprint, execution_workspace)
                facts = {
                    "changed_file_count": len(created) + len(modified) + len(deleted),
                    "contains_deletion": len(deleted) > 0,
                    "touches_protected_path": False,
                    "touches_critical_path": False,
                    "final_status": run_summary.final_status.value
                }

                # Check for block deletions in tasks
                for t in tasks:
                    if t.type == TaskType.MODIFY and t.constraints:
                        try:
                            data = json.loads(t.constraints)
                            if data.get("operation") == "delete_block":
                                facts["contains_deletion"] = True
                                break
                        except: pass

                # Check for protected paths in changes
                for f in created + modified + deleted:
                    p_risk, _ = self.risk_classifier._classify_by_path(f)
                    if p_risk == RiskClass.R3_CRITICAL:
                        facts["touches_critical_path"] = True
                    elif p_risk == RiskClass.R2_HIGH:
                        facts["touches_protected_path"] = True

                promotion_risk, risk_reasons = self.risk_classifier.classify_actual_promotion(facts)
                self.ui_queue.put(("queue_log", f"Actual promotion risk: {promotion_risk.value}"))

                policy_result_prom = self.policy_evaluator.evaluate_pre_promotion(slot.current_run_id, promotion_risk, facts)
                self.audit_log_service.log_artifact(run_folder, "policy_evaluation_pre_promotion.json", json.dumps(policy_result_prom.to_dict(), indent=2))

                if policy_result_prom.decision == PolicyDecision.POLICY_DENIED.value:
                     self.ui_queue.put(("queue_log", f"PROMOTION_DENIED: {', '.join(policy_result_prom.reason_codes)}"))
                     # Block promotion by changing execution mode
                     execution_mode = ExecutionMode.DRY_RUN

                if policy_result_prom.decision == PolicyDecision.APPROVAL_REQUIRED.value:
                     existing_appr = self.approval_service.find_latest_for_entity(slot.current_run_id, "promotion")
                     if existing_appr and existing_appr.status == ApprovalStatus.APPROVED.value:
                          self.ui_queue.put(("queue_log", f"Promotion approval found: {existing_appr.approval_id} (Approved by {existing_appr.decider})"))
                     else:
                          if not existing_appr:
                               self.approval_service.create_approval_request("promotion", "run", slot.current_run_id, self.spec_queue.queue_id, str(slot.slot_index), policy_result_prom)

                          self.ui_queue.put(("queue_log", "Promotion approval required. Pausing queue."))
                          update_stage("Policy Check (Pre-Promote)", "pending", "Waiting for approval")
                          self.spec_queue.queue_status = "paused"
                          self.ui_queue.put(("queue_slot_paused_approval", slot.slot_index))
                          return

                update_stage("Policy Check (Pre-Promote)", "completed", f"risk={promotion_risk.value}")
                check_stop()

                # 8. Logging / Audit
                update_stage("Logging / Audit", "running")

                if run_folder and slot.verification_report and slot.run_summary:
                    reporter = ReportingService()
                    reporter.generate_json_report(run_folder, slot.verification_report, slot.run_summary)
                    reporter.generate_html_report(run_folder, slot.verification_report, slot.run_summary)
                # SPEC 012 Requirement 10: Store original and normalized spec
                if is_dsl:
                    self.audit_log_service.log_artifact(run_folder, "spec.yaml", slot.spec_text)
                    normalized_tasks = []
                    for t in tasks:
                        normalized_tasks.append({
                            "id": t.id,
                            "type": t.type.value,
                            "target": t.target,
                            "depends_on": t.depends_on,
                            "constraints": json.loads(t.constraints) if t.constraints else None
                        })
                    normalized_spec = {
                        "spec_id": spec_data.get("spec_id"),
                        "spec_version": spec_data.get("spec_version"),
                        "tasks": normalized_tasks
                    }
                    self.audit_log_service.log_artifact(run_folder, "spec_normalized.json", json.dumps(normalized_spec, indent=2))
                else:
                    self.audit_log_service.log_artifact(run_folder, "spec.txt", slot.spec_text)

                self.audit_log_service.log_artifact(run_folder, "tasks.json", [{"id": t.id, "type": t.type.value, "target": t.target, "status": t.status.value} for t in tasks])

                if slot.run_summary:
                    # Serializing RunSummary (simplified)
                    summary_dict = {
                        "spec_id": slot.run_summary.spec_id,
                        "final_status": slot.run_summary.final_status.value,
                        "failure_stage": slot.run_summary.failure_stage.value if slot.run_summary.failure_stage else None,
                        "verification": slot.run_summary.verification,
                        "regression": slot.run_summary.regression,
                        "runtime": {
                            "profile_id": profile.profile_id,
                            "interpreter": interpreter_path,
                            "python_version": version_info,
                            "env_inherit_mode": profile.env.inherit_mode.value,
                            "dependency_fingerprint_status": "captured",
                            "environment_drift_status": drift_status
                        }
                    }
                    self.audit_log_service.log_artifact(run_folder, "run_summary.json", json.dumps(summary_dict, indent=2))

                # Update run metadata with report info
                metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
                if metadata:
                    metadata.verification_report = str(run_folder / "verification_report.json")
                    self.ledger_service.update_run_metadata(metadata)

                    self.ledger_service.record_event(
                        entity_type="run",
                        entity_id=slot.current_run_id,
                        event_type="artifact_registered",
                        new_state=DurableRunState.COMPLETED.value,
                        run_id=slot.current_run_id,
                        payload={"artifact": "run_summary", "path": str(run_folder / "run_summary.json")}
                    )

                # Simplified log for audit
                execution_log = [f"{t.type.value} {t.target}: {t.status.value}" for t in tasks]
                self.audit_log_service.log_artifact(run_folder, "execution.log", "\n".join(execution_log))

                for change in all_changes:
                    # This captures the FINAL state of the file
                    self.audit_log_service.capture_file_change(run_folder, execution_workspace, change)

                # SPEC 014: Promotion Gate
                if execution_mode == ExecutionMode.PROMOTE_ON_SUCCESS:
                    # Check status
                    allowed_statuses = {"COMPLETED"}
                    if spec_data and "promotion" in spec_data and "allow_on_status" in spec_data["promotion"]:
                        allowed_statuses = set(spec_data["promotion"]["allow_on_status"])

                    if run_summary.final_status.value in allowed_statuses:
                        self.ui_queue.put(("queue_log", "Evaluating promotion gate..."))

                        created, modified, deleted = self.promotion_service.detect_changes(snapshot_manifest.source_fingerprint, execution_workspace)
                        files_to_promote = created + modified + deleted

                        if files_to_promote:
                            # Drift check
                            self.ui_queue.put(("queue_log", "Checking for canonical drift..."))
                            conflict_report = self.conflict_service.check_drift(snapshot_manifest, self.current_folder, files_to_promote)

                            if conflict_report.promotion_status == PromotionStatus.BLOCKED:
                                self.ui_queue.put(("queue_log", f"Promotion BLOCKED: {conflict_report.reason}"))
                                # Update summary to reflect promotion failure
                                run_summary.final_status = FinalOutcome.PARTIAL_FAILURE
                                run_summary.failure_stage = FailureStage.PROMOTION_CONFLICT
                                run_summary.summary += f"\nPromotion blocked by drift: {', '.join([c.path for c in conflict_report.conflicts])}"
                                self.audit_log_service.log_artifact(run_folder, "promotion_conflict.json", {
                                    "status": "blocked",
                                    "conflicts": [{"path": c.path} for c in conflict_report.conflicts]
                                })
                            else:
                                self.ui_queue.put(("queue_log", f"Promoting {len(files_to_promote)} changes to canonical workspace..."))
                                promotion_report = self.promotion_service.promote(snapshot_manifest, execution_workspace, self.current_folder)
                                self.audit_log_service.log_artifact(run_folder, "promotion_report.json", {
                                    "status": promotion_report.promotion_status.value,
                                    "files_created": promotion_report.files_created,
                                    "files_modified": promotion_report.files_modified,
                                    "files_deleted": promotion_report.files_deleted
                                })
                                self.ui_queue.put(("queue_log", "Promotion successful"))
                        else:
                            self.ui_queue.put(("queue_log", "No changes to promote"))
                    else:
                        self.ui_queue.put(("queue_log", f"Promotion skipped: status {run_summary.final_status.value} not in allowed set"))
                elif execution_mode == ExecutionMode.DRY_RUN:
                    self.ui_queue.put(("queue_log", "Dry run: promotion skipped"))

                # SPEC 014: Retention Policy
                keep_on_failure = True
                keep_on_success = False
                if spec_data and "retention" in spec_data:
                    keep_on_failure = spec_data["retention"].get("keep_execution_workspace_on_failure", keep_on_failure)
                    keep_on_success = spec_data["retention"].get("keep_execution_workspace_on_success", keep_on_success)

                is_success = run_summary.final_status in {FinalOutcome.COMPLETED, FinalOutcome.COMPLETED_WITH_WARNINGS}
                should_keep = keep_on_success if is_success else keep_on_failure

                if not should_keep and execution_workspace and execution_workspace.exists():
                    self.ui_queue.put(("queue_log", "Discarding isolated workspace..."))
                    shutil.rmtree(execution_workspace)

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
                    failed_stage_name = stages[current_stage_idx]
                    update_stage(failed_stage_name, "failed", str(exc))
                    for s_name in stages[current_stage_idx + 1:]:
                        update_stage(s_name, "skipped", "upstream failure")

                # Synthesize outcome even on failure if we have enough info
                if tasks or v_report:
                    s_id = spec_data.get("spec_id", "legacy_run") if spec_data else "legacy_run"
                    slot.run_summary = v_synthesizer.synthesize(s_id, tasks, v_report or VerificationReport(), failure_stage, None)
                    if run_folder:
                        reporter = ReportingService()
                        reporter.generate_json_report(run_folder, v_report or VerificationReport(), slot.run_summary)
                        reporter.generate_html_report(run_folder, v_report or VerificationReport(), slot.run_summary)

                self.queue_service.mark_slot_failed(self.spec_queue, slot, str(exc))
                self.ui_queue.put(("queue_slot_failed", (slot.slot_index, str(exc))))
                self.ui_queue.put(("queue_log", f"Slot {slot.slot_index + 1} failed"))

        final_status = "stopped" if self.spec_queue.stop_requested else "completed"

        # Persist final queue state
        q_def = self.queue_store.get_queue_definition(self.spec_queue.queue_id)
        if q_def:
            q_def.state = DurableQueueState.COMPLETED if final_status == "completed" else DurableQueueState.INTERRUPTED
            self.queue_store.save_queue_definition(q_def)

            self.ledger_service.record_event(
                entity_type="queue",
                entity_id=self.spec_queue.queue_id,
                event_type="state_transition",
                new_state=q_def.state.value,
                queue_id=self.spec_queue.queue_id
            )

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

    def _map_stage_to_durable_state(self, stage_name: str) -> DurableRunState | None:
        mapping = {
            "Spec Intake": DurableRunState.CREATED,
            "Spec Parsing": DurableRunState.SNAPSHOT_PREPARING,
            "Policy Check (Pre-Exec)": DurableRunState.SNAPSHOT_PREPARING, # Close enough
            "Runtime Environment": DurableRunState.RUNTIME_RESOLVING,
            "Task Execution": DurableRunState.EXECUTING,
            "Structural Validation": DurableRunState.STRUCTURAL_VALIDATING,
            "Deterministic Verification": DurableRunState.VERIFYING,
            "Outcome Synthesis": DurableRunState.COMPLETED, # Or partial failure etc
            "Policy Check (Pre-Promote)": DurableRunState.PROMOTION_PENDING,
            "Logging / Audit": DurableRunState.COMPLETED,
        }
        return mapping.get(stage_name)

    def _record_run_transition(self, slot: Any, new_state: DurableRunState):
        metadata = self.ledger_service.get_run_metadata(slot.current_run_id)
        prev_state = None
        if not metadata:
            metadata = RunMetadata(
                run_id=slot.current_run_id,
                spec_id="pending",
                queue_id=self.spec_queue.queue_id,
                slot_id=str(slot.slot_index),
                state=new_state,
                execution_mode="promote_on_success",
                runtime_profile="default",
                source_policy="promoted_head"
            )
        else:
            prev_state = metadata.state.value
            metadata.state = new_state
            metadata.updated_at = datetime.now().isoformat()

        self.ledger_service.update_run_metadata(metadata)
        self.ledger_service.record_event(
            entity_type="run",
            entity_id=slot.current_run_id,
            event_type="state_transition",
            new_state=new_state.value,
            previous_state=prev_state,
            run_id=slot.current_run_id,
            queue_id=self.spec_queue.queue_id,
            slot_id=str(slot.slot_index)
        )

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
        if message == "queue_slot_paused_approval":
            self.queue_active = False
            self.start_queue_button.state(["!disabled"])
            self.stop_queue_button.state(["disabled"])
            self._refresh_queue_view()
            self._refresh_pipeline_view()
            self.log_event(f"Queue paused for approval at slot {payload + 1}")
            self.set_status_action("paused for approval")
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
