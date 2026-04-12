from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from models import Node
from renderer import TreemapRenderer
from scanner import ScanEvent, ScanProgress, ScanResult, ScanStats, start_parallel_scan
from shell_utils import open_in_explorer
from tooltip import Tooltip
from treemap import compute_treemap


class TreemapApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Disk Treemap Viewer")
        self.root.geometry("1280x760")
        self.root.minsize(960, 600)

        self.scan_root: Node | None = None
        self.view_root: Node | None = None
        self.selected_node: Node | None = None
        self.navigation_stack: list[Node] = []
        self.show_labels = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self.summary_var = tk.StringVar(value="")
        self.scan_queue: queue.Queue[ScanEvent] = queue.Queue()
        self.active_scan_id = 0
        self.scan_cancel_event: threading.Event | None = None
        self.scan_thread: threading.Thread | None = None
        self.scan_polling_active = False
        self.scan_progress = ScanProgress()

        self._build_layout()
        self.renderer = TreemapRenderer(self.canvas, show_labels=self.show_labels.get())
        self.tooltip = Tooltip(self.canvas)

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)

    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        toolbar.pack(side="top", fill="x")

        self.open_button = ttk.Button(toolbar, text="Open Folder", command=self.open_folder)
        self.open_button.pack(side="left")
        self.rescan_button = ttk.Button(toolbar, text="Rescan", command=self.rescan)
        self.rescan_button.pack(side="left", padx=(6, 0))
        self.back_button = ttk.Button(toolbar, text="Back", command=self.go_back)
        self.back_button.pack(side="left", padx=(6, 0))
        self.reset_button = ttk.Button(toolbar, text="Reset Root", command=self.reset_root)
        self.reset_button.pack(side="left", padx=(6, 0))
        self.explorer_button = ttk.Button(toolbar, text="Open in Explorer", command=self.open_current_in_explorer)
        self.explorer_button.pack(side="left", padx=(6, 0))
        ttk.Checkbutton(
            toolbar,
            text="Show Labels",
            variable=self.show_labels,
            command=self.toggle_labels,
        ).pack(side="left", padx=(12, 0))

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        canvas_frame = ttk.Frame(body)
        self.canvas = tk.Canvas(canvas_frame, bg="#0f172a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        body.add(canvas_frame, weight=5)

        side = ttk.Frame(body, padding=12)
        body.add(side, weight=2)

        ttk.Label(side, text="Selection", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.details_text = tk.Text(
            side,
            width=40,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            bg="#f8fafc",
            relief="solid",
            borderwidth=1,
        )
        self.details_text.pack(fill="both", expand=True, pady=(8, 12))

        ttk.Label(side, text="Scan Errors", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.error_list = tk.Listbox(side, height=10)
        self.error_list.pack(fill="both", expand=False, pady=(8, 0))

        status = ttk.Frame(self.root, padding=(10, 6))
        status.pack(side="bottom", fill="x")
        ttk.Label(status, textvariable=self.status_var).pack(side="left")
        ttk.Label(status, textvariable=self.summary_var).pack(side="right")

    def open_folder(self) -> None:
        selected = filedialog.askdirectory()
        if selected:
            self._scan_and_render(selected)

    def rescan(self) -> None:
        if self.scan_root is not None:
            self._scan_and_render(self.scan_root.path)

    def go_back(self) -> None:
        if self.navigation_stack or self.scan_thread is None or not self.scan_thread.is_alive():
            if not self.navigation_stack:
                return
            self.view_root = self.navigation_stack.pop()
            self.selected_node = self.view_root
            self._render_current()

    def reset_root(self) -> None:
        if self.scan_root is None or self.view_root is self.scan_root:
            return
        self.navigation_stack.clear()
        self.view_root = self.scan_root
        self.selected_node = self.view_root
        self._render_current()

    def toggle_labels(self) -> None:
        self.renderer.set_show_labels(self.show_labels.get())
        self._render_current()

    def open_current_in_explorer(self) -> None:
        target = self.selected_node or self.view_root
        if target is None:
            messagebox.showerror("Open in Explorer", "No folder or file is available to open.")
            return
        try:
            open_in_explorer(target.path, select_file=None if not target.is_dir else False)
        except FileNotFoundError:
            messagebox.showerror("Open in Explorer", "Path no longer exists.")
        except OSError as exc:
            messagebox.showerror("Open in Explorer", f"Failed to open Explorer.\n{exc}")

    def _scan_and_render(self, path: str) -> None:
        self._cancel_active_scan()
        self.active_scan_id += 1
        self.scan_cancel_event = threading.Event()
        self.scan_progress = ScanProgress()
        self.status_var.set("Scanning...")
        self.summary_var.set("")
        self.selected_node = None
        self._show_details(None)
        self._load_errors(ScanStats())
        self._set_scanning_state(True)
        self.scan_thread = start_parallel_scan(
            path,
            self.scan_queue,
            scan_id=self.active_scan_id,
            cancel_event=self.scan_cancel_event,
        )
        self._ensure_scan_polling()

    def _cancel_active_scan(self) -> None:
        if self.scan_cancel_event is not None:
            self.scan_cancel_event.set()

    def _ensure_scan_polling(self) -> None:
        if self.scan_polling_active:
            return
        self.scan_polling_active = True
        self.root.after(75, self._poll_scan_events)

    def _poll_scan_events(self) -> None:
        keep_polling = False
        while True:
            try:
                event = self.scan_queue.get_nowait()
            except queue.Empty:
                break
            keep_polling = True
            self._handle_scan_event(event)

        if self.scan_thread is not None and self.scan_thread.is_alive():
            keep_polling = True
        if keep_polling:
            self.root.after(75, self._poll_scan_events)
        else:
            self.scan_polling_active = False

    def _handle_scan_event(self, event: ScanEvent) -> None:
        if event.scan_id != self.active_scan_id:
            return
        if event.event_type == "scan_started":
            self.status_var.set("Scanning...")
            return
        if event.event_type == "scan_progress" and event.progress is not None:
            self._apply_progress(event.progress)
            return
        if event.event_type == "scan_complete" and event.result is not None:
            self._apply_scan_result(event.result)
            return
        if event.event_type == "scan_failed":
            self._set_scanning_state(False)
            self.status_var.set("Scan failed")
            messagebox.showerror("Scan Failed", event.error_message or "The scan failed unexpectedly.")
            return
        if event.event_type == "scan_cancelled":
            self._set_scanning_state(False)
            self.status_var.set("Scan cancelled")

    def _apply_progress(self, progress: ScanProgress) -> None:
        self.scan_progress.directories_scanned += progress.directories_scanned
        self.scan_progress.files_scanned += progress.files_scanned
        self.scan_progress.bytes_accumulated += progress.bytes_accumulated
        self.scan_progress.skipped_count += progress.skipped_count
        if progress.current_path:
            self.scan_progress.current_path = progress.current_path
        self.status_var.set(
            "Scanning... "
            f"{self.scan_progress.files_scanned:,} files, "
            f"{self.scan_progress.directories_scanned:,} folders, "
            f"{human_size(self.scan_progress.bytes_accumulated)}, "
            f"{self.scan_progress.skipped_count:,} skipped"
        )
        self.summary_var.set(self.scan_progress.current_path or "")

    def _apply_scan_result(self, result: ScanResult) -> None:
        self.scan_root = result.root
        self.view_root = result.root
        self.selected_node = result.root
        self.navigation_stack.clear()
        self._load_errors(result.stats)
        self._update_summary(result.stats)
        self._set_scanning_state(False)
        self._render_current()

    def _render_current(self) -> None:
        if self.view_root is None:
            return
        width = max(self.canvas.winfo_width(), 200)
        height = max(self.canvas.winfo_height(), 200)
        self.status_var.set("Rendering...")
        rects = compute_treemap(self.view_root, 0, 0, width, height)
        self.renderer.draw(rects, selected_node=self.selected_node)
        if self.selected_node is not None:
            self._show_details(self.selected_node)
        self.status_var.set("Ready")

    def _on_canvas_resize(self, _event: tk.Event) -> None:
        if self.view_root is not None:
            self._render_current()

    def _on_motion(self, event: tk.Event) -> None:
        rect = self.renderer.rect_at(event.x, event.y)
        self.renderer.highlight_hover(rect)
        if rect is None:
            self.tooltip.hide()
            return
        self.tooltip.show(event.x_root, event.y_root, _tooltip_text(rect.node))

    def _on_leave(self, _event: tk.Event) -> None:
        self.renderer.highlight_hover(None)
        self.tooltip.hide()

    def _on_click(self, event: tk.Event) -> None:
        rect = self.renderer.rect_at(event.x, event.y)
        self.renderer.select(rect)
        self.tooltip.hide()
        if rect is None:
            self.selected_node = None
            self._show_details(None)
            return
        self.selected_node = rect.node
        self._show_details(rect.node)
        self.status_var.set(f"Selected: {rect.node.path}")

    def _on_double_click(self, event: tk.Event) -> None:
        rect = self.renderer.rect_at(event.x, event.y)
        if rect is None or not rect.node.is_dir or rect.node is self.view_root:
            return
        if self.view_root is not None:
            self.navigation_stack.append(self.view_root)
        self.view_root = rect.node
        self.selected_node = rect.node
        self._render_current()

    def _show_details(self, node: Node | None) -> None:
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", "end")
        if node is None:
            self.details_text.insert("1.0", "No item selected.")
        else:
            lines = [
                f"Name: {node.display_name}",
                f"Path: {node.path}",
                f"Type: {node.type_name}",
                f"Size: {human_size(node.size)} ({node.size} bytes)",
                f"Files: {node.file_count}",
                f"Folders: {node.dir_count}",
            ]
            if node.extension:
                lines.append(f"Extension: {node.extension}")
            if node.error:
                lines.append(f"Error: {node.error}")
            self.details_text.insert("1.0", "\n".join(lines))
        self.details_text.configure(state="disabled")

    def _load_errors(self, stats: ScanStats) -> None:
        self.error_list.delete(0, "end")
        for message in stats.errors[:500]:
            self.error_list.insert("end", f"{message.path}: {message.message}")

    def _update_summary(self, stats: ScanStats) -> None:
        self.summary_var.set(
            f"Done: {stats.files:,} files, {stats.dirs:,} folders, {stats.skipped:,} skipped"
        )

    def _set_scanning_state(self, scanning: bool) -> None:
        nav_state = "disabled" if scanning else "normal"
        self.back_button.configure(state=nav_state)
        self.reset_button.configure(state=nav_state)


def human_size(size: int) -> str:
    units = ["bytes", "KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "bytes":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} bytes"


def _tooltip_text(node: Node) -> str:
    lines = [
        node.display_name,
        node.path,
        f"Type: {node.type_name}",
        f"Size: {human_size(node.size)}",
    ]
    if node.is_dir:
        lines.append(f"Files: {node.file_count}  Folders: {node.dir_count}")
    if node.error:
        lines.append(f"Error: {node.error}")
    return "\n".join(lines)
