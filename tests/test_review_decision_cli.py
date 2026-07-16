from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_project"
PINNED_COMMIT = "b66790165a2d4f82943cd199b3b499e1f1725fc3"


def run_cli_subprocess(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    env["UNIT_TEST_RUNNER_PRODUCER_COMMIT"] = PINNED_COMMIT
    command = [sys.executable, "-m", "unit_test_runner", "--json", *args]
    # File-backed capture waits for the CLI process itself instead of waiting
    # for pipe EOF from any short-lived fixture descendants.
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
            check=False,
            timeout=120,
        )
        stdout_file.seek(0)
        stderr_file.seek(0)
        return subprocess.CompletedProcess(
            command,
            completed.returncode,
            stdout_file.read().decode("utf-8", errors="replace"),
            stderr_file.read().decode("utf-8", errors="replace"),
        )


def run_cli_in_process(*args: str) -> subprocess.CompletedProcess[str]:
    from unit_test_runner.cli.main import main

    command = ["unit_test_runner", "--json", *args]
    stdout = io.StringIO()
    stderr = io.StringIO()
    previous_commit = os.environ.get("UNIT_TEST_RUNNER_PRODUCER_COMMIT")
    os.environ["UNIT_TEST_RUNNER_PRODUCER_COMMIT"] = PINNED_COMMIT
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return_code = main(["--json", *args])
    finally:
        if previous_commit is None:
            os.environ.pop("UNIT_TEST_RUNNER_PRODUCER_COMMIT", None)
        else:
            os.environ["UNIT_TEST_RUNNER_PRODUCER_COMMIT"] = previous_commit
    return subprocess.CompletedProcess(
        command,
        return_code,
        stdout.getvalue(),
        stderr.getvalue(),
    )


# Most semantic guard checks run in-process to avoid accumulating compiler/probe
# descendants across many subprocesses. A dedicated test below retains the real
# process-boundary envelope/exit assertion.
run_cli = run_cli_in_process


def result_details(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)["data"]["details"]


class ReviewDecisionCLITests(unittest.TestCase):
    def prepare_workspace(self, root: Path) -> Path:
        workspace = root / "Control_Update"
        analyzed = run_cli(
            "analyze-function",
            "--workspace",
            str(VC6_FIXTURE),
            "--dsw",
            str(VC6_FIXTURE / "Product.dsw"),
            "--source",
            "src/control.c",
            "--function",
            "Control_Update",
            "--configuration",
            "Win32 Debug",
            "--out",
            str(workspace),
            "--project",
            "Control",
            "--phase",
            "design",
        )
        self.assertEqual(0, analyzed.returncode, analyzed.stderr or analyzed.stdout)
        finalized = run_cli("finalize-dossier", "--workspace", str(workspace))
        self.assertEqual(0, finalized.returncode, finalized.stderr or finalized.stdout)
        return workspace

    def test_discovery_and_write_share_exact_guards_and_four_axes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(Path(temp_dir))

            discovery = run_cli("get-review-status", "--workspace", str(workspace))
            self.assertEqual(0, discovery.returncode, discovery.stderr or discovery.stdout)
            details = result_details(discovery)
            self.assertEqual(0, details["ledger_revision"])
            self.assertFalse(details["review_complete"])
            self.assertEqual(
                {"ready_for_review", "review_complete", "evidence_ready", "test_green"},
                set(details["readiness"]),
            )
            item = details["items"][0]
            self.assertEqual(64, len(item["subject_fingerprint"]))
            self.assertTrue(item["subject_artifacts"])

            written = run_cli(
                "record-review-decision",
                "--workspace",
                str(workspace),
                "--review-id",
                item["review_id"],
                "--resolution",
                "approved",
                "--reviewer",
                "reviewer01",
                "--rationale",
                "Reviewed against REQ-42",
                "--decided-at",
                "2026-07-12T18:00:00+09:00",
                "--expected-revision",
                "0",
                "--expected-subject-fingerprint",
                item["subject_fingerprint"],
            )
            self.assertEqual(0, written.returncode, written.stderr or written.stdout)
            payload = json.loads(written.stdout)
            self.assertEqual(1, len(payload["data"]["artifacts"]))
            artifact = payload["data"]["artifacts"][0]
            self.assertEqual("review_decisions", artifact["artifact_kind"])
            self.assertEqual("reports/review_decisions.json", artifact["path"])
            self.assertEqual(64, len(artifact["sha256"]))

            rediscovery = run_cli("get-review-status", "--workspace", str(workspace))
            self.assertEqual(0, rediscovery.returncode, rediscovery.stderr or rediscovery.stdout)
            latest = result_details(rediscovery)
            self.assertEqual(1, latest["ledger_revision"])
            status = next(
                value
                for value in latest["items"]
                if value["review_id"] == item["review_id"]
            )
            self.assertEqual("approved", status["status"])
            self.assertEqual("approved", status["resolution"])
            self.assertEqual([], status["blocked_reasons"])

    def test_guard_failures_are_nonzero_and_preserve_ledger_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(Path(temp_dir))
            details = result_details(
                run_cli_in_process("get-review-status", "--workspace", str(workspace))
            )
            item = details["items"][0]
            ledger = workspace / "reports" / "review_decisions.json"

            unknown = run_cli_in_process(
                "record-review-decision",
                "--workspace",
                str(workspace),
                "--review-id",
                "review-unknown",
                "--resolution",
                "approved",
                "--reviewer",
                "reviewer01",
                "--rationale",
                "Reviewed",
                "--decided-at",
                "2026-07-12T18:00:00+09:00",
                "--expected-revision",
                "0",
                "--expected-subject-fingerprint",
                item["subject_fingerprint"],
            )
            self.assertNotEqual(0, unknown.returncode)
            self.assertFalse(ledger.exists())

            mismatch = run_cli_in_process(
                "record-review-decision",
                "--workspace",
                str(workspace),
                "--review-id",
                item["review_id"],
                "--resolution",
                "approved",
                "--reviewer",
                "reviewer01",
                "--rationale",
                "Reviewed",
                "--decided-at",
                "2026-07-12T18:00:00+09:00",
                "--expected-revision",
                "0",
                "--expected-subject-fingerprint",
                "f" * 64,
            )
            self.assertNotEqual(0, mismatch.returncode)
            self.assertFalse(ledger.exists())

            invalid_waiver = run_cli_in_process(
                "record-review-decision",
                "--workspace",
                str(workspace),
                "--review-id",
                item["review_id"],
                "--resolution",
                "waived",
                "--expected-revision",
                "0",
                "--expected-subject-fingerprint",
                item["subject_fingerprint"],
            )
            self.assertNotEqual(0, invalid_waiver.returncode)
            self.assertFalse(ledger.exists())

            written = run_cli_in_process(
                "record-review-decision",
                "--workspace",
                str(workspace),
                "--review-id",
                item["review_id"],
                "--resolution",
                "approved",
                "--reviewer",
                "reviewer01",
                "--rationale",
                "Reviewed",
                "--decided-at",
                "2026-07-12T18:00:00+09:00",
                "--expected-revision",
                "0",
                "--expected-subject-fingerprint",
                item["subject_fingerprint"],
            )
            self.assertEqual(0, written.returncode, written.stderr or written.stdout)
            before = ledger.read_bytes()

            stale = run_cli_in_process(
                "record-review-decision",
                "--workspace",
                str(workspace),
                "--review-id",
                item["review_id"],
                "--resolution",
                "changes_requested",
                "--reviewer",
                "reviewer02",
                "--rationale",
                "Needs changes",
                "--decided-at",
                "2026-07-12T18:05:00+09:00",
                "--expected-revision",
                "0",
                "--expected-subject-fingerprint",
                item["subject_fingerprint"],
            )
            self.assertNotEqual(0, stale.returncode)
            self.assertEqual(before, ledger.read_bytes())

    def test_subprocess_discovery_exit_matches_envelope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(Path(temp_dir))
            result = run_cli_subprocess(
                "get-review-status", "--workspace", str(workspace)
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, payload["data"]["exit_code"])
            self.assertEqual("passed", payload["data"]["outcome"])

    def test_invalid_existing_ledger_is_nonzero_and_never_rewritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(Path(temp_dir))
            details = result_details(
                run_cli_in_process("get-review-status", "--workspace", str(workspace))
            )
            item = details["items"][0]
            ledger = workspace / "reports" / "review_decisions.json"
            corrupt = b'{"artifact_kind":"review_decisions"}\n'
            ledger.write_bytes(corrupt)

            discovery = run_cli_in_process("get-review-status", "--workspace", str(workspace))
            self.assertNotEqual(0, discovery.returncode)
            self.assertEqual(corrupt, ledger.read_bytes())

            write = run_cli_in_process(
                "record-review-decision",
                "--workspace",
                str(workspace),
                "--review-id",
                item["review_id"],
                "--resolution",
                "approved",
                "--reviewer",
                "reviewer01",
                "--rationale",
                "Reviewed",
                "--decided-at",
                "2026-07-12T18:00:00+09:00",
                "--expected-revision",
                "0",
                "--expected-subject-fingerprint",
                item["subject_fingerprint"],
            )
            self.assertNotEqual(0, write.returncode)
            self.assertEqual(corrupt, ledger.read_bytes())


if __name__ == "__main__":
    unittest.main()
