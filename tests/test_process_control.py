from __future__ import annotations

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


def process_exists(pid: int) -> bool:
    if os.name != "nt":
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
    except OSError as error:
        if getattr(error, "winerror", None) == 87:
            return False
        raise


def wait_for_exit(pids: list[int], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(not process_exists(pid) for pid in pids):
            return True
        time.sleep(0.05)
    return all(not process_exists(pid) for pid in pids)


class ProcessControlTests(unittest.TestCase):
    def test_process_exists_treats_windows_invalid_pid_as_exited(self):
        invalid_pid = OSError(22, "The parameter is incorrect")
        invalid_pid.winerror = 87

        with mock.patch("os.kill", side_effect=invalid_pid):
            self.assertFalse(process_exists(999999))

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
                for pid in pids:
                    if process_exists(pid):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass


if __name__ == "__main__":
    unittest.main()
