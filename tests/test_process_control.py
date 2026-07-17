from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unit_test_runner.process_control import run_process_tree

_WINDOWS_SYNCHRONIZE = 0x00100000
_WINDOWS_WAIT_OBJECT_0 = 0x00000000
_WINDOWS_WAIT_TIMEOUT = 0x00000102
_WINDOWS_WAIT_FAILED = 0xFFFFFFFF
_WINDOWS_ERROR_ACCESS_DENIED = 5
_WINDOWS_ERROR_INVALID_PARAMETER = 87

if os.name == "nt":
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _windows_open_process = _kernel32.OpenProcess
    _windows_open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _windows_open_process.restype = wintypes.HANDLE
    _windows_wait_for_single_object = _kernel32.WaitForSingleObject
    _windows_wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _windows_wait_for_single_object.restype = wintypes.DWORD
    _windows_close_handle = _kernel32.CloseHandle
    _windows_close_handle.argtypes = [wintypes.HANDLE]
    _windows_close_handle.restype = wintypes.BOOL
else:
    _windows_open_process = None
    _windows_wait_for_single_object = None
    _windows_close_handle = None


def _windows_process_exists(pid: int) -> bool:
    if (
        _windows_open_process is None
        or _windows_wait_for_single_object is None
        or _windows_close_handle is None
    ):
        raise RuntimeError("Windows process probing is unavailable on this platform")

    ctypes.set_last_error(0)
    handle = _windows_open_process(_WINDOWS_SYNCHRONIZE, False, pid)
    if not handle:
        error_code = ctypes.get_last_error()
        if error_code == _WINDOWS_ERROR_INVALID_PARAMETER:
            return False
        if error_code == _WINDOWS_ERROR_ACCESS_DENIED:
            return True
        raise ctypes.WinError(error_code)

    try:
        wait_result = _windows_wait_for_single_object(handle, 0)
        if wait_result == _WINDOWS_WAIT_OBJECT_0:
            return False
        if wait_result == _WINDOWS_WAIT_TIMEOUT:
            return True
        if wait_result == _WINDOWS_WAIT_FAILED:
            raise ctypes.WinError(ctypes.get_last_error())
        raise OSError(f"Unexpected WaitForSingleObject result: {wait_result}")
    finally:
        _windows_close_handle(handle)


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        return _windows_process_exists(pid)

    status = Path(f"/proc/{pid}/status")
    if status.exists():
        try:
            for line in status.read_text(encoding="utf-8").splitlines():
                if line.startswith("State:") and "Z" in line:
                    return False
        except OSError:
            pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for_exit(pids: list[int], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(not process_exists(pid) for pid in pids):
            return True
        time.sleep(0.05)
    return all(not process_exists(pid) for pid in pids)


class ProcessControlTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process probing requires Windows")
    def test_process_exists_treats_windows_invalid_pid_as_exited(self):
        module = sys.modules[__name__]
        with mock.patch.object(
            module,
            "_windows_open_process",
            return_value=0,
        ), mock.patch.object(ctypes, "get_last_error", return_value=87):
            self.assertFalse(process_exists(999999))

    @unittest.skipUnless(os.name == "nt", "Windows process probing requires Windows")
    def test_process_exists_treats_windows_access_denied_as_existing(self):
        module = sys.modules[__name__]
        with mock.patch.object(
            module,
            "_windows_open_process",
            return_value=0,
        ), mock.patch.object(ctypes, "get_last_error", return_value=5):
            self.assertTrue(process_exists(4))

    @unittest.skipUnless(os.name == "nt", "Windows process probing requires Windows")
    def test_process_exists_uses_non_destructive_windows_probe(self):
        with mock.patch(
            "os.kill",
            side_effect=AssertionError("Windows process existence checks must not call os.kill"),
        ):
            self.assertTrue(process_exists(os.getpid()))

    def test_preserves_output_and_return_code_for_normal_completion(self):
        result = run_process_tree(
            [
                sys.executable,
                "-c",
                "import sys; print('stdout-value'); print('stderr-value', file=sys.stderr); sys.exit(7)",
            ],
            text=True,
            timeout_seconds=5,
        )

        self.assertFalse(result.timed_out)
        self.assertEqual(7, result.returncode)
        self.assertIn("stdout-value", result.stdout)
        self.assertIn("stderr-value", result.stderr or "")

    def test_timeout_terminates_parent_and_grandchild(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pid_file = root / "pids.json"
            script = root / "parent.py"
            script.write_text(
                "\n".join(
                    [
                        "import json",
                        "import subprocess",
                        "import sys",
                        "import time",
                        f"pid_file = {str(pid_file)!r}",
                        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
                        "with open(pid_file, 'w', encoding='utf-8') as handle:",
                        "    json.dump({'parent': __import__('os').getpid(), 'child': child.pid}, handle)",
                        "time.sleep(60)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            pids: list[int] = []
            try:
                result = run_process_tree(
                    [sys.executable, str(script)],
                    text=True,
                    timeout_seconds=5.0,
                )
                recorded = json.loads(pid_file.read_text(encoding="utf-8"))
                pids = [int(recorded["parent"]), int(recorded["child"])]

                self.assertTrue(result.timed_out)
                self.assertTrue(wait_for_exit(pids), f"processes still running: {[pid for pid in pids if process_exists(pid)]}")
            finally:
                cleanup_signal = signal.SIGTERM if os.name == "nt" else signal.SIGKILL
                for pid in pids:
                    if process_exists(pid):
                        try:
                            os.kill(pid, cleanup_signal)
                        except OSError:
                            pass


if __name__ == "__main__":
    unittest.main()
