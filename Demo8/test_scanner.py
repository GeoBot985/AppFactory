from __future__ import annotations

import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scanner


def test_parallel_matches_serial_on_mixed_tree(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            "root.txt": b"abc",
            "A": {
                "a.bin": b"x" * 10,
                "nested": {
                    "deep.txt": b"12345",
                },
            },
            "B": {
                "b.txt": b"hello",
            },
            "empty": {},
        },
    )

    serial_node, serial_stats = scanner.scan_path_serial(str(tmp_path))
    parallel_result = _run_parallel(str(tmp_path))
    parallel_node = parallel_result.result.root
    parallel_stats = parallel_result.result.stats

    assert parallel_node.size == serial_node.size
    assert parallel_stats.files == serial_stats.files
    assert parallel_stats.dirs == serial_stats.dirs
    assert parallel_stats.skipped == serial_stats.skipped
    assert _tree_signature(parallel_node) == _tree_signature(serial_node)


def test_empty_directory_is_preserved(tmp_path: Path) -> None:
    root = tmp_path / "empty-root"
    root.mkdir()

    result = _run_parallel(str(root)).result

    assert result.root.is_dir is True
    assert result.root.size == 0
    assert result.stats.files == 0
    assert result.stats.dirs == 1


def test_symlink_is_skipped(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("Symlinks are not supported on this platform")
    target = tmp_path / "real.txt"
    target.write_text("data", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("Symlink creation is not permitted in this environment")

    result = _run_parallel(str(tmp_path)).result

    assert result.stats.files == 1
    assert result.stats.skipped == 1
    assert any(error.path.endswith("link.txt") for error in result.stats.errors)


def test_deterministic_merge_behavior(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            "gamma": {"x.txt": b"12"},
            "alpha": {"x.txt": b"12"},
            "beta": {"x.txt": b"1"},
        },
    )

    first = _run_parallel(str(tmp_path), max_workers=3).result.root
    second = _run_parallel(str(tmp_path), max_workers=2).result.root

    assert [child.name for child in first.children] == [child.name for child in second.children]
    assert [child.name for child in first.children] == ["alpha", "gamma", "beta"]


def test_permission_denied_entry_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    denied = tmp_path / "denied"
    denied.mkdir()
    allowed = tmp_path / "allowed.txt"
    allowed.write_text("ok", encoding="utf-8")

    real_scandir = scanner.os.scandir

    class _ScandirWrapper:
        def __init__(self, iterator):
            self._iterator = iterator

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self._iterator.close()
            return False

        def __iter__(self):
            return self

        def __next__(self):
            entry = next(self._iterator)
            if entry.path == str(denied):
                raise PermissionError("access denied")
            return entry

    def fake_scandir(path: str):
        return _ScandirWrapper(real_scandir(path))

    monkeypatch.setattr(scanner.os, "scandir", fake_scandir)

    result = _run_parallel(str(tmp_path)).result

    assert result.stats.files == 1
    assert result.stats.skipped == 1
    assert any("access denied" in error.message for error in result.stats.errors)


def test_one_giant_nested_subtree_matches_serial_with_adaptive_split(tmp_path: Path) -> None:
    deep = tmp_path / "big"
    cursor = deep
    for depth in range(4):
        cursor.mkdir(parents=True, exist_ok=True)
        for index in range(14):
            branch = cursor / f"branch_{depth}_{index:02d}"
            branch.mkdir()
            (branch / "payload.bin").write_bytes(b"x" * (depth + index + 1))
        cursor = cursor / f"next_{depth}"

    serial_node, serial_stats = scanner.scan_path_serial(str(tmp_path))
    config = scanner.ScanConfig(
        max_workers=4,
        split_max_depth=3,
        split_child_dir_threshold=12,
        max_outstanding_tasks=16,
        max_child_splits_per_directory=4,
    )
    adaptive = _run_parallel(str(tmp_path), config=config).result
    adaptive_node = adaptive.root
    adaptive_stats = adaptive.stats

    assert adaptive_node.size == serial_node.size
    assert adaptive_stats.files == serial_stats.files
    assert adaptive_stats.dirs == serial_stats.dirs
    assert _tree_signature(adaptive_node) == _tree_signature(serial_node)


def test_split_threshold_boundary_behavior(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for index in range(11):
        branch = root / f"small_{index:02d}"
        branch.mkdir()
        (branch / "f.txt").write_text("x", encoding="utf-8")
    for index in range(12):
        branch = root / f"large_{index:02d}"
        branch.mkdir()
        (branch / "f.txt").write_text("x", encoding="utf-8")

    assert scanner._choose_deferred_paths(
        [(child.name, str(child)) for child in sorted((root / "small_00").parent.iterdir()) if child.name.startswith("small_")],
        depth=1,
        config=scanner.ScanConfig(split_child_dir_threshold=12),
        remaining_budget=8,
    ) == set()
    deferred = scanner._choose_deferred_paths(
        [(child.name, str(child)) for child in sorted((root / "large_00").parent.iterdir()) if child.name.startswith("large_")],
        depth=1,
        config=scanner.ScanConfig(max_workers=4, split_child_dir_threshold=12, max_child_splits_per_directory=4),
        remaining_budget=4,
    )
    assert len(deferred) == 4


def test_outstanding_task_cap_is_respected(tmp_path: Path) -> None:
    top = tmp_path / "top"
    top.mkdir()
    for index in range(20):
        child = top / f"child_{index:02d}"
        child.mkdir()
        for sub in range(20):
            branch = child / f"sub_{sub:02d}"
            branch.mkdir()
            (branch / "f.txt").write_text("x", encoding="utf-8")

    config = scanner.ScanConfig(
        max_workers=2,
        split_max_depth=3,
        split_child_dir_threshold=5,
        max_outstanding_tasks=3,
        max_child_splits_per_directory=2,
    )
    terminal = _run_parallel(str(tmp_path), config=config)
    progress_events = [event.progress for event in terminal.all_events if event.progress is not None]

    assert progress_events
    assert max(progress.outstanding_jobs for progress in progress_events) <= 3


def test_deterministic_merge_regardless_of_completion_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_tree(
        tmp_path,
        {
            "alpha": {"f.txt": b"1"},
            "beta": {"f.txt": b"22"},
            "gamma": {"f.txt": b"333"},
        },
    )

    original = scanner._scan_job_worker

    def delayed(job, config, cancel_event, event_queue, scan_id):
        delays = {"alpha": 0.08, "beta": 0.01, "gamma": 0.04}
        time.sleep(delays.get(Path(job.path).name, 0))
        return original(job, config, cancel_event, event_queue, scan_id)

    monkeypatch.setattr(scanner, "_scan_job_worker", delayed)

    first = _run_parallel(str(tmp_path), max_workers=3).result.root
    second = _run_parallel(str(tmp_path), max_workers=3).result.root

    assert _tree_signature(first) == _tree_signature(second)


def test_scan_cancelled_event_is_emitted_for_stale_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tree(
        tmp_path,
        {
            "root": {
                **{
                    f"branch_{index:02d}": {
                        **{f"leaf_{leaf:02d}": {"f.txt": b"x"} for leaf in range(12)}
                    }
                    for index in range(12)
                }
            }
        },
    )

    original = scanner._scan_job_worker

    def slow_job(job, config, cancel_event, event_queue, scan_id):
        time.sleep(0.1)
        return original(job, config, cancel_event, event_queue, scan_id)

    monkeypatch.setattr(scanner, "_scan_job_worker", slow_job)

    event_queue: queue.Queue[scanner.ScanEvent] = queue.Queue()
    cancel_event = threading.Event()
    config = scanner.ScanConfig(
        max_workers=2,
        split_max_depth=3,
        split_child_dir_threshold=4,
        max_outstanding_tasks=4,
        max_child_splits_per_directory=2,
    )
    thread = scanner.start_parallel_scan(
        str(tmp_path),
        event_queue,
        scan_id=7,
        cancel_event=cancel_event,
        config=config,
    )
    time.sleep(0.05)
    cancel_event.set()
    thread.join(timeout=5)

    events = _drain_events(event_queue)
    assert any(event.scan_id == 7 for event in events)
    assert events[-1].event_type == "scan_cancelled"


@dataclass
class _Terminal:
    result: scanner.ScanResult
    all_events: list[scanner.ScanEvent]


def _run_parallel(
    path: str,
    max_workers: int | None = None,
    config: scanner.ScanConfig | None = None,
) -> _Terminal:
    event_queue: queue.Queue[scanner.ScanEvent] = queue.Queue()
    scanner.run_parallel_scan(path, event_queue, scan_id=1, max_workers=max_workers, config=config)
    events = _drain_events(event_queue)
    terminal = events[-1]
    assert terminal.event_type == "scan_complete"
    assert terminal.result is not None
    return _Terminal(result=terminal.result, all_events=events)


def _drain_events(event_queue: queue.Queue[scanner.ScanEvent]) -> list[scanner.ScanEvent]:
    events: list[scanner.ScanEvent] = []
    while True:
        try:
            events.append(event_queue.get_nowait())
        except queue.Empty:
            break
    return events


def _tree_signature(node) -> tuple:
    return (
        node.name,
        node.is_dir,
        node.size,
        node.file_count,
        node.dir_count,
        [error for error in ([node.error] if node.error else [])],
        [_tree_signature(child) for child in node.children],
    )


def _write_tree(root: Path, spec: dict[str, object]) -> None:
    for name, value in spec.items():
        path = root / name
        if isinstance(value, dict):
            path.mkdir()
            _write_tree(path, value)
        else:
            path.write_bytes(value)
