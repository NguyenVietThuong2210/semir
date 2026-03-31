"""
tests/base.py — Shared utilities: Timer checkpoints + JSON snapshots + run logger.
"""
import atexit
import json
import os
import sys
import time
from datetime import datetime, timezone as _tz
from decimal import Decimal
from pathlib import Path

from django.test import TestCase

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
OUTPUT_DIR    = Path(__file__).parent / "output"
INPUT_DIR     = Path(__file__).parent / "input"

SNAPSHOTS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ── JSON serialiser ────────────────────────────────────────────────────────

class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        return super().default(obj)


def _normalise(data):
    return json.loads(json.dumps(data, cls=_Encoder))


# ── Run logger (singleton per process) ────────────────────────────────────

class _RunLogger:
    """Write timestamped log entries to output/<datetime>_ut_run.log"""

    def __init__(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = OUTPUT_DIR / f"{ts}_ut_run.log"
        self._f = open(self.path, "w", encoding="utf-8")
        self._write(f"{'='*70}")
        self._write(f"UT RUN STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write(f"{'='*70}")
        print(f"\n[LOG] Writing to: {self.path}")

    def _write(self, line: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {line}"
        self._f.write(entry + "\n")
        self._f.flush()

    def log(self, line: str):
        self._write(line)

    def section(self, title: str):
        self._write("")
        self._write(f"{'─'*60}")
        self._write(f"  {title}")
        self._write(f"{'─'*60}")

    def timer_result(self, timer_name: str, checkpoints: list, total: float):
        self._write(f"")
        self._write(f"  TIMER: {timer_name}")
        for label, elapsed, delta in checkpoints:
            bar = "#" * min(int(delta * 5), 30)
            self._write(f"    {delta:7.2f}s  {bar}  {label}")
        self._write(f"    TOTAL: {total:.2f}s")

    def finalize(self, results: list):
        """Write summary at end of all tests."""
        if self._f.closed:
            return
        self._write("")
        self._write(f"{'='*70}")
        self._write(f"SUMMARY")
        self._write(f"{'='*70}")
        for r in results:
            self._write(f"  {r}")
        self._write(f"{'='*70}")
        self._write(f"UT RUN FINISHED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write(f"{'='*70}")
        self._f.close()
        print(f"[LOG] Run log saved: {self.path}")


_RUN_LOG: _RunLogger | None = None


def _atexit_finalize():
    global _RUN_LOG
    if _RUN_LOG is not None:
        _RUN_LOG.finalize(SnapshotTestCase._summary_results)


def get_run_log() -> _RunLogger:
    global _RUN_LOG
    if _RUN_LOG is None:
        _RUN_LOG = _RunLogger()
        atexit.register(_atexit_finalize)
    return _RUN_LOG


# ── Timer ──────────────────────────────────────────────────────────────────

class Timer:
    def __init__(self, name: str):
        self.name = name
        self._start = time.perf_counter()
        self._last  = self._start
        self._checkpoints: list[tuple[str, float, float]] = []

    def checkpoint(self, label: str) -> float:
        now = time.perf_counter()
        delta = now - self._last
        self._last = now
        self._checkpoints.append((label, now - self._start, delta))
        # Live progress to stdout and log
        safe_label = label.encode("ascii", errors="replace").decode("ascii")
        print(f"  [{self.name}] {delta:.2f}s  {safe_label}")
        get_run_log().log(f"  [{self.name}] {delta:.2f}s  {label}")
        return delta

    def total(self) -> float:
        return time.perf_counter() - self._start

    def report(self) -> str:
        sep = "-" * 60
        lines = [f"\n{sep}", f"  [TIMER] {self.name}", sep]
        for label, elapsed, delta in self._checkpoints:
            bar = "#" * min(int(delta * 5), 30)
            lines.append(f"  {delta:7.2f}s  {bar}  {label}")
        lines.append(f"  TOTAL: {self.total():.2f}s")
        lines.append(f"{sep}\n")
        out = "\n".join(lines)
        safe = out.encode("ascii", errors="replace").decode("ascii")
        print(safe)
        get_run_log().timer_result(self.name, self._checkpoints, self.total())
        return out


# ── Snapshot helpers ────────────────────────────────────────────────────────

def _snapshot_path(name: str) -> Path:
    return SNAPSHOTS_DIR / f"{name}.json"


def save_snapshot(name: str, data):
    path = _snapshot_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_normalise(data), f, indent=2, ensure_ascii=False)
    get_run_log().log(f"  [snapshot] saved: {path.name}")


def load_snapshot(name: str):
    path = _snapshot_path(name)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Base test case ──────────────────────────────────────────────────────────

class SnapshotTestCase(TestCase):
    _summary_results: list[str] = []

    def timer(self, name: str) -> Timer:
        get_run_log().section(name)
        return Timer(name)

    def assert_snapshot(self, name: str, data, *, update: bool = False):
        update = update or os.environ.get("UPDATE_SNAPSHOTS") == "1"
        normalised = _normalise(data)
        existing = load_snapshot(name)
        if existing is None or update:
            save_snapshot(name, normalised)
            get_run_log().log(f"  [snapshot] {'updated' if existing else 'created'}: {name}")
            return
        self._deep_compare(name, existing, normalised, path="root")

    def _deep_compare(self, snap_name, expected, actual, path: str):
        if type(expected) != type(actual):
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                pass
            else:
                self.fail(f"[{snap_name}] type mismatch at {path}: "
                          f"expected {type(expected).__name__}, got {type(actual).__name__}")
        if isinstance(expected, dict):
            missing = set(expected.keys()) - set(actual.keys())
            extra   = set(actual.keys())   - set(expected.keys())
            self.assertFalse(missing, f"[{snap_name}] missing keys at {path}: {missing}")
            self.assertFalse(extra,   f"[{snap_name}] extra keys at {path}: {extra}")
            for k in expected:
                self._deep_compare(snap_name, expected[k], actual[k], f"{path}.{k}")
        elif isinstance(expected, list):
            self.assertEqual(len(expected), len(actual),
                f"[{snap_name}] list length at {path}: expected {len(expected)}, got {len(actual)}")
            for i, (e, a) in enumerate(zip(expected, actual)):
                self._deep_compare(snap_name, e, a, f"{path}[{i}]")
        elif isinstance(expected, float):
            self.assertAlmostEqual(expected, actual, places=2,
                msg=f"[{snap_name}] float at {path}: {expected} vs {actual}")
        else:
            self.assertEqual(expected, actual,
                f"[{snap_name}] value at {path}: {expected!r} vs {actual!r}")

    def record_page_timing(self, page: str, total_s: float, checkpoints: list):
        """Record page-level timing summary for final report."""
        flag = "SLOW" if total_s > 20 else "OK"
        line = f"[PAGE {flag}] {page}: {total_s:.2f}s"
        SnapshotTestCase._summary_results.append(line)
        get_run_log().log(line)
        for label, _, delta in checkpoints:
            sub = f"  - {label}: {delta:.2f}s"
            SnapshotTestCase._summary_results.append(sub)
            get_run_log().log(sub)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # Summary is written by atexit handler when the process exits
