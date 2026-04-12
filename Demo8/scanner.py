from __future__ import annotations

import os
import queue
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from models import Node


PROGRESS_INTERVAL_SECONDS = 0.2
PROGRESS_ENTRY_INTERVAL = 256


@dataclass(slots=True)
class ScanErrorRecord:
    path: str
    message: str


@dataclass(slots=True)
class ScanStats:
    files: int = 0
    dirs: int = 0
    skipped: int = 0
    bytes_total: int = 0
    errors: list[ScanErrorRecord] = field(default_factory=list)

    def merge(self, other: "ScanStats") -> None:
        self.files += other.files
        self.dirs += other.dirs
        self.skipped += other.skipped
        self.bytes_total += other.bytes_total
        self.errors.extend(other.errors)


@dataclass(slots=True)
class ScanProgress:
    directories_scanned: int = 0
    files_scanned: int = 0
    bytes_accumulated: int = 0
    skipped_count: int = 0
    current_path: str | None = None
    outstanding_jobs: int = 0
    completed_jobs: int = 0
    deferred_splits: int = 0


@dataclass(slots=True)
class ScanResult:
    root: Node
    stats: ScanStats


@dataclass(slots=True)
class ScanEvent:
    event_type: str
    scan_id: int
    progress: ScanProgress | None = None
    result: ScanResult | None = None
    error_message: str | None = None


@dataclass(slots=True)
class ScanConfig:
    max_workers: int = field(default_factory=lambda: default_max_workers())
    split_max_depth: int = 3
    split_child_dir_threshold: int = 12
    max_outstanding_tasks: int | None = None
    max_child_splits_per_directory: int | None = None

    def __post_init__(self) -> None:
        if self.max_outstanding_tasks is None:
            self.max_outstanding_tasks = self.max_workers * 4
        if self.max_child_splits_per_directory is None:
            self.max_child_splits_per_directory = self.max_workers


@dataclass(slots=True)
class ScanJob:
    path: str
    parent_path: str
    depth: int
    split_budget: int


@dataclass(slots=True)
class DeferredScanJob:
    path: str
    parent_path: str
    depth: int


@dataclass(slots=True)
class WorkerScanResult:
    job: ScanJob
    node: Node
    stats: ScanStats
    deferred_jobs: list[DeferredScanJob]


def default_max_workers() -> int:
    return min(8, max(2, os.cpu_count() or 4))


def scan_path(root_path: str) -> tuple[Node, ScanStats]:
    return scan_path_serial(root_path)


def scan_path_serial(root_path: str) -> tuple[Node, ScanStats]:
    stats = ScanStats()
    progress = _NoopProgressEmitter()
    root_node = _scan_dir_serial(root_path, None, stats, progress, None)
    stats.bytes_total = root_node.size
    return root_node, stats


def start_parallel_scan(
    root_path: str,
    event_queue: queue.Queue[ScanEvent],
    scan_id: int,
    max_workers: int | None = None,
    cancel_event: threading.Event | None = None,
    config: ScanConfig | None = None,
) -> threading.Thread:
    thread = threading.Thread(
        target=run_parallel_scan,
        args=(root_path, event_queue, scan_id, max_workers, cancel_event, config),
        daemon=True,
        name=f"scan-coordinator-{scan_id}",
    )
    thread.start()
    return thread


def run_parallel_scan(
    root_path: str,
    event_queue: queue.Queue[ScanEvent],
    scan_id: int,
    max_workers: int | None = None,
    cancel_event: threading.Event | None = None,
    config: ScanConfig | None = None,
) -> None:
    cancel_event = cancel_event or threading.Event()
    effective = config or ScanConfig(max_workers=max_workers or default_max_workers())
    if max_workers is not None and config is None:
        effective.max_workers = max_workers
        effective.__post_init__()

    event_queue.put(ScanEvent(event_type="scan_started", scan_id=scan_id))
    try:
        if cancel_event.is_set():
            event_queue.put(ScanEvent(event_type="scan_cancelled", scan_id=scan_id))
            return
        result = _coordinate_parallel_scan(root_path, event_queue, scan_id, effective, cancel_event)
        if result is None:
            event_queue.put(ScanEvent(event_type="scan_cancelled", scan_id=scan_id))
            return
        event_queue.put(
            ScanEvent(
                event_type="scan_complete",
                scan_id=scan_id,
                result=result,
                progress=ScanProgress(
                    directories_scanned=result.stats.dirs,
                    files_scanned=result.stats.files,
                    bytes_accumulated=result.stats.bytes_total,
                    skipped_count=result.stats.skipped,
                    current_path=root_path,
                ),
            )
        )
    except Exception as exc:
        event_queue.put(ScanEvent(event_type="scan_failed", scan_id=scan_id, error_message=str(exc)))


def _coordinate_parallel_scan(
    root_path: str,
    event_queue: queue.Queue[ScanEvent],
    scan_id: int,
    config: ScanConfig,
    cancel_event: threading.Event,
) -> ScanResult | None:
    root_node = Node.from_dir(root_path)
    path_index: dict[str, Node] = {root_path: root_node}
    aggregate_stats = ScanStats(dirs=1)
    progress = _ProgressEmitter(event_queue, scan_id)
    progress.record_dir(root_path)

    backlog_jobs: deque[ScanJob] = deque()
    discovered_jobs: deque[ScanJob] = deque()
    try:
        with os.scandir(root_path) as entries:
            root_dirs: list[tuple[str, str]] = []
            for entry in entries:
                if cancel_event.is_set():
                    return None
                try:
                    if entry.is_symlink():
                        aggregate_stats.skipped += 1
                        aggregate_stats.errors.append(ScanErrorRecord(path=entry.path, message="Skipped symlink"))
                        progress.record_skip(entry.path)
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        root_dirs.append((entry.name, entry.path))
                    else:
                        child = _scan_file_entry(entry.path, entry.name, root_node)
                        root_node.children.append(child)
                        aggregate_stats.files += 1
                        aggregate_stats.bytes_total += child.size
                        progress.record_file(child.size, child.path)
                except OSError as exc:
                    aggregate_stats.skipped += 1
                    aggregate_stats.errors.append(ScanErrorRecord(path=entry.path, message=str(exc)))
                    root_node.children.append(
                        Node(
                            name=entry.name,
                            path=entry.path,
                            is_dir=False,
                            size=0,
                            error=str(exc),
                            parent=root_node,
                        )
                    )
                    progress.record_skip(entry.path)
    except OSError as exc:
        aggregate_stats.skipped += 1
        aggregate_stats.errors.append(ScanErrorRecord(path=root_path, message=str(exc)))
        root_node.error = str(exc)
        progress.record_skip(root_path)
        _finalize_tree(root_node, aggregate_stats)
        progress.flush(force=True)
        return ScanResult(root=root_node, stats=aggregate_stats)

    for _, dir_path in sorted(root_dirs, key=lambda item: item[0].lower()):
        backlog_jobs.append(
            ScanJob(
                path=dir_path,
                parent_path=root_path,
                depth=1,
                split_budget=config.max_child_splits_per_directory,
            )
        )

    active: dict[Future[WorkerScanResult], ScanJob] = {}
    completed_jobs = 0
    total_deferred_splits = 0

    with ThreadPoolExecutor(max_workers=config.max_workers, thread_name_prefix="scan-worker") as executor:
        while backlog_jobs or discovered_jobs or active:
            if cancel_event.is_set():
                for future in active:
                    future.cancel()
                return None

            while backlog_jobs and len(active) + len(discovered_jobs) < config.max_outstanding_tasks:
                discovered_jobs.append(backlog_jobs.popleft())

            while discovered_jobs and len(active) < config.max_workers:
                job = discovered_jobs.popleft()
                future = executor.submit(_scan_job_worker, job, config, cancel_event, event_queue, scan_id)
                active[future] = job

            if not active:
                continue

            done, _ = wait(active.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                job = active.pop(future)
                if cancel_event.is_set():
                    for pending in active:
                        pending.cancel()
                    return None
                result = future.result()
                _attach_subtree(result.node, result.job.parent_path, path_index)
                aggregate_stats.merge(result.stats)
                completed_jobs += 1
                total_deferred_splits += len(result.deferred_jobs)
                progress.record_scheduler_state(
                    current_path=result.job.path,
                    outstanding_jobs=len(active) + len(discovered_jobs),
                    completed_jobs=completed_jobs,
                    deferred_splits=total_deferred_splits,
                )
                _schedule_or_inline_deferred_jobs(
                    result.deferred_jobs,
                    discovered_jobs,
                    len(active),
                    aggregate_stats,
                    path_index,
                    config,
                    cancel_event,
                    event_queue,
                    scan_id,
                    progress,
                    completed_jobs,
                    total_deferred_splits,
                )

    _finalize_tree(root_node, aggregate_stats)
    progress.flush(force=True)
    return ScanResult(root=root_node, stats=aggregate_stats)


def _schedule_or_inline_deferred_jobs(
    deferred_jobs: list[DeferredScanJob],
    discovered_jobs: deque[ScanJob],
    active_count: int,
    aggregate_stats: ScanStats,
    path_index: dict[str, Node],
    config: ScanConfig,
    cancel_event: threading.Event,
    event_queue: queue.Queue[ScanEvent],
    scan_id: int,
    progress: "_ProgressEmitter",
    completed_jobs: int,
    total_deferred_splits: int,
) -> None:
    for deferred in deferred_jobs:
        if cancel_event.is_set():
            return
        outstanding = active_count + len(discovered_jobs)
        if outstanding < config.max_outstanding_tasks:
            discovered_jobs.append(
                ScanJob(
                    path=deferred.path,
                    parent_path=deferred.parent_path,
                    depth=deferred.depth,
                    split_budget=config.max_child_splits_per_directory,
                )
            )
            continue

        inline_result = _scan_job_inline(
            ScanJob(
                path=deferred.path,
                parent_path=deferred.parent_path,
                depth=deferred.depth,
                split_budget=0,
            ),
            config,
            cancel_event,
            event_queue,
            scan_id,
        )
        _attach_subtree(inline_result.node, inline_result.job.parent_path, path_index)
        aggregate_stats.merge(inline_result.stats)
        progress.record_scheduler_state(
            current_path=inline_result.job.path,
            outstanding_jobs=len(discovered_jobs),
            completed_jobs=completed_jobs + 1,
            deferred_splits=total_deferred_splits,
        )


def _scan_job_worker(
    job: ScanJob,
    config: ScanConfig,
    cancel_event: threading.Event,
    event_queue: queue.Queue[ScanEvent],
    scan_id: int,
) -> WorkerScanResult:
    progress = _ProgressEmitter(event_queue, scan_id)
    return _scan_job(job, config, cancel_event, progress)


def _scan_job_inline(
    job: ScanJob,
    config: ScanConfig,
    cancel_event: threading.Event,
    event_queue: queue.Queue[ScanEvent],
    scan_id: int,
) -> WorkerScanResult:
    progress = _ProgressEmitter(event_queue, scan_id)
    return _scan_job(job, config, cancel_event, progress)


def _scan_job(
    job: ScanJob,
    config: ScanConfig,
    cancel_event: threading.Event,
    progress: "_BaseProgressEmitter",
) -> WorkerScanResult:
    stats = ScanStats()
    deferred_jobs: list[DeferredScanJob] = []
    remaining_budget = job.split_budget
    node = _scan_dir_adaptive(
        path=job.path,
        parent=None,
        depth=job.depth,
        stats=stats,
        progress=progress,
        cancel_event=cancel_event,
        config=config,
        deferred_jobs=deferred_jobs,
        remaining_budget_ref=[remaining_budget],
    )
    stats.bytes_total = node.size
    progress.flush(force=True)
    return WorkerScanResult(job=job, node=node, stats=stats, deferred_jobs=deferred_jobs)


def _scan_dir_adaptive(
    path: str,
    parent: Node | None,
    depth: int,
    stats: ScanStats,
    progress: "_BaseProgressEmitter",
    cancel_event: threading.Event | None,
    config: ScanConfig,
    deferred_jobs: list[DeferredScanJob],
    remaining_budget_ref: list[int],
) -> Node:
    node = Node.from_dir(path, parent=parent)
    stats.dirs += 1
    progress.record_dir(path)

    child_dirs: list[tuple[str, str]] = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if cancel_event is not None and cancel_event.is_set():
                    break
                try:
                    if entry.is_symlink():
                        stats.skipped += 1
                        stats.errors.append(ScanErrorRecord(path=entry.path, message="Skipped symlink"))
                        progress.record_skip(entry.path)
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        child_dirs.append((entry.name, entry.path))
                    else:
                        child = _scan_file_entry(entry.path, entry.name, node)
                        node.children.append(child)
                        stats.files += 1
                        stats.bytes_total += child.size
                        progress.record_file(child.size, child.path)
                except OSError as exc:
                    stats.skipped += 1
                    stats.errors.append(ScanErrorRecord(path=entry.path, message=str(exc)))
                    node.children.append(
                        Node(
                            name=entry.name,
                            path=entry.path,
                            is_dir=False,
                            size=0,
                            error=str(exc),
                            parent=node,
                        )
                    )
                    progress.record_skip(entry.path)
    except OSError as exc:
        stats.skipped += 1
        stats.errors.append(ScanErrorRecord(path=path, message=str(exc)))
        node.error = str(exc)
        progress.record_skip(path)
        _sort_children(node)
        return node

    deferred_paths = _choose_deferred_paths(child_dirs, depth, config, remaining_budget_ref[0])
    if deferred_paths:
        remaining_budget_ref[0] -= len(deferred_paths)
        for child_name, child_path in child_dirs:
            if child_path in deferred_paths:
                deferred_jobs.append(
                    DeferredScanJob(path=child_path, parent_path=path, depth=depth + 1)
                )
                continue
            child = _scan_dir_adaptive(
                child_path,
                node,
                depth + 1,
                stats,
                progress,
                cancel_event,
                config,
                deferred_jobs,
                remaining_budget_ref,
            )
            node.children.append(child)
    else:
        for _, child_path in child_dirs:
            child = _scan_dir_adaptive(
                child_path,
                node,
                depth + 1,
                stats,
                progress,
                cancel_event,
                config,
                deferred_jobs,
                remaining_budget_ref,
            )
            node.children.append(child)

    _sort_children(node)
    _refresh_node_aggregates(node)
    return node


def _choose_deferred_paths(
    child_dirs: list[tuple[str, str]],
    depth: int,
    config: ScanConfig,
    remaining_budget: int,
) -> set[str]:
    if depth >= config.split_max_depth:
        return set()
    if len(child_dirs) < config.split_child_dir_threshold:
        return set()
    if remaining_budget <= 0:
        return set()
    child_dirs_sorted = sorted(child_dirs, key=lambda item: item[0].lower())
    limit = min(remaining_budget, config.max_child_splits_per_directory)
    return {path for _, path in child_dirs_sorted[:limit]}


def _scan_dir_serial(
    path: str,
    parent: Node | None,
    stats: ScanStats,
    progress: "_BaseProgressEmitter",
    cancel_event: threading.Event | None,
) -> Node:
    node = Node.from_dir(path, parent=parent)
    stats.dirs += 1
    progress.record_dir(path)

    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if cancel_event is not None and cancel_event.is_set():
                    break
                try:
                    if entry.is_symlink():
                        stats.skipped += 1
                        stats.errors.append(ScanErrorRecord(path=entry.path, message="Skipped symlink"))
                        progress.record_skip(entry.path)
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        child = _scan_dir_serial(entry.path, node, stats, progress, cancel_event)
                        node.children.append(child)
                    else:
                        child = _scan_file_entry(entry.path, entry.name, node)
                        node.children.append(child)
                        stats.files += 1
                        stats.bytes_total += child.size
                        progress.record_file(child.size, child.path)
                except OSError as exc:
                    stats.skipped += 1
                    stats.errors.append(ScanErrorRecord(path=entry.path, message=str(exc)))
                    node.children.append(
                        Node(
                            name=entry.name,
                            path=entry.path,
                            is_dir=False,
                            size=0,
                            error=str(exc),
                            parent=node,
                        )
                    )
                    progress.record_skip(entry.path)
    except OSError as exc:
        stats.skipped += 1
        stats.errors.append(ScanErrorRecord(path=path, message=str(exc)))
        node.error = str(exc)
        progress.record_skip(path)

    _sort_children(node)
    _refresh_node_aggregates(node)
    return node


def _scan_file_entry(path: str, name: str, parent: Node | None) -> Node:
    size = os.stat(path, follow_symlinks=False).st_size
    return Node.from_file(path, size, parent=parent)


def _attach_subtree(node: Node, parent_path: str, path_index: dict[str, Node]) -> None:
    parent = path_index[parent_path]
    node.parent = parent
    parent.children.append(node)
    _register_paths(node, path_index)


def _register_paths(node: Node, path_index: dict[str, Node]) -> None:
    path_index[node.path] = node
    for child in node.children:
        child.parent = node
        if child.is_dir:
            _register_paths(child, path_index)


def _refresh_node_aggregates(node: Node) -> None:
    size = 0
    file_count = 0
    dir_count = 0
    for child in node.children:
        size += child.size
        file_count += child.file_count
        if child.is_dir:
            dir_count += child.dir_count + 1
        else:
            file_count += 0
    node.size = size
    node.file_count = file_count
    node.dir_count = dir_count


def _recompute_tree(node: Node) -> None:
    for child in node.children:
        child.parent = node
        if child.is_dir:
            _recompute_tree(child)
    _sort_children(node)
    _refresh_node_aggregates(node)


def _finalize_tree(root_node: Node, aggregate_stats: ScanStats) -> None:
    _recompute_tree(root_node)
    aggregate_stats.bytes_total = root_node.size


def _sort_children(node: Node) -> None:
    node.children.sort(key=lambda item: (-item.size, item.display_name.lower(), item.path.lower()))


class _BaseProgressEmitter:
    def record_dir(self, path: str) -> None:
        raise NotImplementedError

    def record_file(self, size: int, path: str) -> None:
        raise NotImplementedError

    def record_skip(self, path: str) -> None:
        raise NotImplementedError

    def record_scheduler_state(
        self,
        current_path: str,
        outstanding_jobs: int,
        completed_jobs: int,
        deferred_splits: int,
    ) -> None:
        raise NotImplementedError

    def flush(self, force: bool = False) -> None:
        raise NotImplementedError


class _NoopProgressEmitter(_BaseProgressEmitter):
    def record_dir(self, path: str) -> None:
        return

    def record_file(self, size: int, path: str) -> None:
        return

    def record_skip(self, path: str) -> None:
        return

    def record_scheduler_state(
        self,
        current_path: str,
        outstanding_jobs: int,
        completed_jobs: int,
        deferred_splits: int,
    ) -> None:
        return

    def flush(self, force: bool = False) -> None:
        return


class _ProgressEmitter(_BaseProgressEmitter):
    def __init__(self, event_queue: queue.Queue[ScanEvent], scan_id: int) -> None:
        self.event_queue = event_queue
        self.scan_id = scan_id
        self.pending = ScanProgress()
        self.last_emit = time.monotonic()
        self.pending_entries = 0
        self._lock = threading.Lock()

    def record_dir(self, path: str) -> None:
        with self._lock:
            self.pending.directories_scanned += 1
            self.pending.current_path = path
            self.pending_entries += 1
            self._maybe_emit_locked()

    def record_file(self, size: int, path: str) -> None:
        with self._lock:
            self.pending.files_scanned += 1
            self.pending.bytes_accumulated += size
            self.pending.current_path = path
            self.pending_entries += 1
            self._maybe_emit_locked()

    def record_skip(self, path: str) -> None:
        with self._lock:
            self.pending.skipped_count += 1
            self.pending.current_path = path
            self.pending_entries += 1
            self._maybe_emit_locked()

    def record_scheduler_state(
        self,
        current_path: str,
        outstanding_jobs: int,
        completed_jobs: int,
        deferred_splits: int,
    ) -> None:
        with self._lock:
            self.pending.current_path = current_path
            self.pending.outstanding_jobs = outstanding_jobs
            self.pending.completed_jobs = completed_jobs
            self.pending.deferred_splits = deferred_splits
            self._emit_locked(force=True)

    def flush(self, force: bool = False) -> None:
        with self._lock:
            self._emit_locked(force=force)

    def _maybe_emit_locked(self) -> None:
        now = time.monotonic()
        if self.pending_entries >= PROGRESS_ENTRY_INTERVAL or now - self.last_emit >= PROGRESS_INTERVAL_SECONDS:
            self._emit_locked(force=True)

    def _emit_locked(self, force: bool) -> None:
        has_work = any(
            (
                self.pending.directories_scanned,
                self.pending.files_scanned,
                self.pending.bytes_accumulated,
                self.pending.skipped_count,
                self.pending.outstanding_jobs,
                self.pending.completed_jobs,
                self.pending.deferred_splits,
            )
        )
        if not force and not has_work:
            return
        if not has_work and self.pending.current_path is None:
            return
        self.event_queue.put(
            ScanEvent(
                event_type="scan_progress",
                scan_id=self.scan_id,
                progress=ScanProgress(
                    directories_scanned=self.pending.directories_scanned,
                    files_scanned=self.pending.files_scanned,
                    bytes_accumulated=self.pending.bytes_accumulated,
                    skipped_count=self.pending.skipped_count,
                    current_path=self.pending.current_path,
                    outstanding_jobs=self.pending.outstanding_jobs,
                    completed_jobs=self.pending.completed_jobs,
                    deferred_splits=self.pending.deferred_splits,
                ),
            )
        )
        self.pending = ScanProgress()
        self.pending_entries = 0
        self.last_emit = time.monotonic()
