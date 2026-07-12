import hashlib
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.cli.artifacts import (
    ExpectedArtifact,
    ProducedArtifact,
    build_expected_artifact,
    build_produced_artifact,
)
from unit_test_runner.cli.commands import (
    _artifacts_from_explicit_outputs,
    handle_run_tests,
    handle_suite_run,
)
from unit_test_runner.cli.errors import CLIError
from unit_test_runner.cli.outcomes import DomainOutcome
from unit_test_runner.cli.parser import ArgumentParseError, build_parser
from unit_test_runner.cli.result import CLIResult
from unit_test_runner.contracts import RunOutcome
from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.execution.evidence_paths import EvidencePaths
from unit_test_runner.execution.run_paths import RunPaths


class CliArtifactReferenceTests(unittest.TestCase):
    def _tree_hashes(self, root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_produced_file_uses_final_bytes_and_actual_json_contract_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            report = root / "results" / "cli_result.json"
            report.parent.mkdir(parents=True)
            payload = CLIResult(
                status="ok",
                exit_code=0,
                command="doctor",
                message="ok",
                outcome=DomainOutcome("command", RunOutcome.PASSED, None),
                invocation_id="inv-artifact-001",
                producer_commit="6c3aecac794f18bffd4307213481cbfaf270cdba",
            ).to_dict()
            final_bytes = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            report.write_bytes(final_bytes)

            artifact = build_produced_artifact(
                root,
                report,
                kind=ArtifactKind.CLI_RESULT.value,
            )

            self.assertEqual(ArtifactKind.CLI_RESULT.value, artifact.kind)
            self.assertEqual("results/cli_result.json", artifact.path)
            self.assertTrue(artifact.exists)
            self.assertEqual(hashlib.sha256(final_bytes).hexdigest(), artifact.sha256)
            self.assertEqual("1.0.0", artifact.schema_version)
            self.assertEqual(
                {
                    "artifact_kind": ArtifactKind.CLI_RESULT.value,
                    "path": "results/cli_result.json",
                    "exists": True,
                    "sha256": hashlib.sha256(final_bytes).hexdigest(),
                    "schema_version": "1.0.0",
                },
                artifact.to_dict(),
            )

    def test_typed_json_requires_recognized_supported_and_valid_contract_identity(self):
        valid = CLIResult(
            status="ok",
            exit_code=0,
            command="doctor",
            message="ok",
            outcome=DomainOutcome("command", RunOutcome.PASSED, None),
            invocation_id="inv-artifact-002",
            producer_commit="6c3aecac794f18bffd4307213481cbfaf270cdba",
        ).to_dict()
        mutations = {
            "missing_kind": lambda payload: payload.pop("artifact_kind"),
            "missing_version": lambda payload: payload.pop("schema_version"),
            "unknown_kind": lambda payload: payload.update(artifact_kind="unknown_kind"),
            "unsupported_version": lambda payload: payload.update(schema_version="9.9.9"),
            "schema_invalid": lambda payload: payload["data"].pop("command"),
            "semantic_invalid": lambda payload: payload["data"].update(
                outcome_kind="test_run",
                outcome="failed",
                green=False,
                exit_code=0,
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir).resolve()
                path = root / "result.json"
                payload = json.loads(json.dumps(valid))
                mutate(payload)
                path.write_text(json.dumps(payload), encoding="utf-8")

                with self.assertRaises(ValueError):
                    build_produced_artifact(root, path, kind=None)

    def test_missing_non_file_and_escaped_paths_are_rejected_as_produced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir).resolve()
            root = parent / "workspace"
            root.mkdir()
            directory = root / "reports"
            directory.mkdir()
            outside = parent / "outside.json"
            outside.write_text("{}", encoding="utf-8")

            for path, error_type in [
                (root / "missing.json", FileNotFoundError),
                (directory, ValueError),
                (outside, ValueError),
            ]:
                with self.subTest(path=path), self.assertRaises(error_type):
                    build_produced_artifact(root, path, kind="report")

    def test_json_kind_mismatch_is_rejected_instead_of_relabelled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            report = root / "report.json"
            report.write_text(
                json.dumps(
                    {
                        "artifact_kind": ArtifactKind.EVIDENCE_MANIFEST.value,
                        "schema_version": "1.0.0",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "artifact kind"):
                build_produced_artifact(
                    root,
                    report,
                    kind=ArtifactKind.TEST_EXECUTION_REPORT.value,
                )

    def test_json_without_contract_identity_is_never_relabelled_as_typed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            legacy = root / "legacy.json"
            legacy.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "status": "ok",
                        "command": "doctor",
                        "exit_code": 0,
                        "data": {},
                        "warnings": [],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "contract identity"):
                build_produced_artifact(
                    root,
                    legacy,
                    kind=ArtifactKind.TEST_EXECUTION_REPORT.value,
                )

            artifact = build_produced_artifact(root, legacy, kind=None)
            self.assertEqual("untyped_json", artifact.kind)
            self.assertEqual("0.1", artifact.schema_version)

            for invalid in (
                {"schema_version": "0.1"},
                {"schema_version": "0.1", "status": "ok", "command": "doctor"},
                {"schema_version": "0.2", "status": "ok", "command": "doctor", "exit_code": 0, "data": {}, "warnings": [], "errors": []},
            ):
                legacy.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(ValueError):
                    build_produced_artifact(root, legacy, kind=None)

    def test_explicit_output_allowlist_excludes_existing_input_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            previous_dossier = root / "reports" / "function_dossier.json"
            produced = root / "reports" / "quick_summary.md"
            previous_dossier.parent.mkdir(parents=True)
            previous_dossier.write_text('{"schema_version":"0.1"}\n', encoding="utf-8")
            produced.write_text("# Quick summary\n", encoding="utf-8")
            command_payload = {
                "previous_dossier": str(previous_dossier),
                "reports": {"quick_summary_md": str(produced)},
            }

            artifacts = _artifacts_from_explicit_outputs(
                root,
                [
                    (
                        Path(command_payload["reports"]["quick_summary_md"]),
                        ArtifactKind.QUICK_SUMMARY.value,
                    )
                ],
            )

            self.assertEqual(["reports/quick_summary.md"], [item.path for item in artifacts])

    def test_expected_only_reference_has_no_production_claims(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            expected = build_expected_artifact(
                root,
                root / "reports" / "future.json",
                kind=ArtifactKind.TEST_SPEC.value,
            )

            self.assertIsInstance(expected, ExpectedArtifact)
            self.assertEqual(
                {
                    "artifact_kind": ArtifactKind.TEST_SPEC.value,
                    "path": "reports/future.json",
                },
                expected.to_dict(),
            )
            self.assertFalse((root / "reports" / "future.json").exists())
            self.assertNotIn("exists", expected.to_dict())
            self.assertNotIn("sha256", expected.to_dict())

    def test_run_tests_uses_only_immutable_originating_paths_and_never_reads_latest_aliases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir).resolve()
            run_root = workspace / "runs" / "run-origin"
            evidence_root = workspace / "evidence" / "evidence-origin"
            run_paths = RunPaths(
                run_id="run-origin",
                root=run_root,
                execution_report=run_root / "test_execution_report.json",
                result_json=run_root / "test_result.json",
                result_csv=run_root / "test_result.csv",
                stdout_log=run_root / "logs" / "stdout.log",
                stderr_log=run_root / "logs" / "stderr.log",
                combined_log=run_root / "logs" / "test_execution.log",
            )
            evidence_paths = EvidencePaths(
                evidence_id="evidence-origin",
                source_run_id="run-origin",
                root=evidence_root,
                evidence_manifest=evidence_root / "evidence_manifest.json",
                evidence_package=evidence_root / "evidence_package.md",
            )
            json_files = [
                (run_paths.execution_report, ArtifactKind.TEST_EXECUTION_REPORT),
                (run_paths.result_json, ArtifactKind.TEST_RESULT),
                (evidence_paths.source_run, ArtifactKind.EVIDENCE_SOURCE_RUN),
                (evidence_paths.evidence_manifest, ArtifactKind.EVIDENCE_MANIFEST),
                (workspace / "reports" / "latest_run.json", ArtifactKind.LATEST_RUN_POINTER),
                (workspace / "reports" / "latest_evidence.json", ArtifactKind.LATEST_EVIDENCE_POINTER),
            ]
            for path, kind in json_files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "artifact_kind": kind.value,
                            "schema_version": "1.0.0",
                        }
                    ),
                    encoding="utf-8",
                )
            for path in [
                run_paths.result_csv,
                run_paths.stdout_log,
                run_paths.stderr_log,
                run_paths.combined_log,
                evidence_paths.evidence_package,
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"{path.name}\n", encoding="utf-8")
            interloper = workspace / "runs" / "run-interloper" / "test_execution_report.json"
            interloper.parent.mkdir(parents=True)
            interloper.write_text(
                json.dumps(
                    {
                        "artifact_kind": ArtifactKind.TEST_EXECUTION_REPORT.value,
                        "schema_version": "1.0.0",
                    }
                ),
                encoding="utf-8",
            )
            report = SimpleNamespace(
                status="passed",
                executed=True,
                parsed_result=SimpleNamespace(
                    total=1,
                    passed=1,
                    failed=0,
                    inconclusive=0,
                    crashed=0,
                    not_run=0,
                ),
                run_paths=run_paths,
            )
            manifest = SimpleNamespace(
                summary=SimpleNamespace(test_execution_status="passed"),
                evidence_paths=evidence_paths,
            )
            args = Namespace(
                command="run-tests",
                workspace=str(workspace),
                executable=None,
                run=True,
                plan=False,
                dry_run=False,
                timeout=60,
                run_id=None,
                allow_placeholder_tests=True,
                treat_placeholder_as_inconclusive=True,
            )

            def immutable_artifact(root, path, *, kind):
                relative = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
                if relative in {"reports/latest_run.json", "reports/latest_evidence.json"}:
                    raise AssertionError(f"mutable alias was read: {relative}")
                return ProducedArtifact(
                    kind=kind,
                    path=relative,
                    exists=True,
                    sha256="a" * 64,
                    schema_version="1.0.0" if Path(path).suffix.lower() == ".json" else None,
                )

            with mock.patch(
                "unit_test_runner.cli.commands.prepare_test_execution_evidence",
                return_value=(report, manifest),
            ), mock.patch(
                "unit_test_runner.cli.commands.build_produced_artifact",
                side_effect=immutable_artifact,
            ):
                result = handle_run_tests(args)

            produced = {artifact.path for artifact in result.artifacts}
            self.assertEqual(
                {
                    "runs/run-origin/test_execution_report.json",
                    "runs/run-origin/test_result.json",
                    "runs/run-origin/test_result.csv",
                    "runs/run-origin/logs/stdout.log",
                    "runs/run-origin/logs/stderr.log",
                    "runs/run-origin/logs/test_execution.log",
                    "evidence/evidence-origin/source_run.json",
                    "evidence/evidence-origin/evidence_manifest.json",
                    "evidence/evidence-origin/evidence_package.md",
                },
                produced,
            )
            self.assertFalse(any("run-interloper" in path for path in produced))
            envelope = result.to_dict()
            self.assertEqual(produced, {item["path"] for item in envelope["data"]["artifacts"]})

    def test_run_tests_parser_accepts_plan_and_keeps_modes_exclusive(self):
        parser = build_parser()

        planned = parser.parse_args(["run-tests", "--workspace", "workspace", "--plan"])
        legacy = parser.parse_args(["run-tests", "--workspace", "workspace", "--dry-run"])

        self.assertTrue(planned.plan)
        self.assertFalse(planned.run)
        self.assertFalse(planned.dry_run)
        self.assertTrue(legacy.dry_run)
        self.assertFalse(legacy.run)
        self.assertFalse(legacy.plan)
        with self.assertRaises(ArgumentParseError):
            parser.parse_args(
                ["run-tests", "--workspace", "workspace", "--plan", "--run"]
            )

    def test_plan_and_dry_run_alias_do_not_mutate_workspace_or_execute(self):
        for mode in ("plan", "dry_run"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir).resolve()
                self._write_plan_workspace(workspace)
                existing = [
                    workspace / "runs" / "run-existing" / "test_execution_report.json",
                    workspace / "evidence" / "evidence-existing" / "evidence_manifest.json",
                    workspace / "reports" / "latest_run.json",
                    workspace / "reports" / "latest_evidence.json",
                    workspace / "logs" / "existing.log",
                ]
                for path in existing:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(f"existing:{path.name}\n", encoding="utf-8")
                before = self._tree_hashes(workspace)
                args = Namespace(
                    command="run-tests",
                    workspace=str(workspace),
                    executable=None,
                    run=False,
                    plan=mode == "plan",
                    dry_run=mode == "dry_run",
                    timeout=60,
                    run_id="run-plan",
                    allow_placeholder_tests=True,
                    treat_placeholder_as_inconclusive=True,
                )

                with mock.patch(
                    "unit_test_runner.cli.commands.prepare_test_execution_evidence",
                    side_effect=AssertionError("plan must not prepare execution or evidence"),
                ):
                    result = handle_run_tests(args)

                after = self._tree_hashes(workspace)
                self.assertEqual(before, after)
                self.assertIs(RunOutcome.PLANNED, result.outcome.state)
                self.assertEqual(0, result.exit_code)
                self.assertEqual([], result.artifacts)
                expected = {artifact.path for artifact in result.expected_artifacts}
                self.assertEqual(
                    {
                        "runs/run-plan/test_execution_report.json",
                        "runs/run-plan/test_result.json",
                        "runs/run-plan/test_result.csv",
                    },
                    expected,
                )
                envelope = result.to_dict()
                self.assertEqual("planned", envelope["data"]["outcome"])
                self.assertEqual([], envelope["data"]["artifacts"])
                self.assertTrue(
                    all(
                        "exists" not in item and "sha256" not in item
                        for item in envelope["data"]["expected_artifacts"]
                    )
                )
                diagnostic_codes = {
                    item["code"] for item in envelope["data"]["diagnostics"]
                }
                if mode == "dry_run":
                    self.assertIn("deprecated_dry_run_alias", diagnostic_codes)
                else:
                    self.assertNotIn("deprecated_dry_run_alias", diagnostic_codes)

    def test_run_plan_rejects_missing_reports_and_explicit_executable_without_writes(self):
        cases = ("missing_report", "missing_executable")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir).resolve()
                executable = self._write_plan_workspace(workspace)
                if case == "missing_report":
                    (workspace / "reports" / "harness_skeleton_report.json").unlink()
                elif case == "missing_executable":
                    executable = workspace / "bin" / "missing.exe"
                before = self._tree_hashes(workspace)
                args = Namespace(
                    command="run-tests",
                    workspace=str(workspace),
                    executable=str(executable),
                    run=False,
                    plan=True,
                    dry_run=False,
                    timeout=60,
                    run_id="run-plan",
                    allow_placeholder_tests=True,
                    treat_placeholder_as_inconclusive=True,
                )

                with mock.patch(
                    "unit_test_runner.cli.commands.prepare_test_execution_evidence",
                    side_effect=AssertionError("plan must not prepare execution or evidence"),
                ), self.assertRaises(CLIError):
                    handle_run_tests(args)

                self.assertEqual(before, self._tree_hashes(workspace))

    def test_run_plan_reports_valid_blockers_without_writes(self):
        for case, expected_code in (
            ("failed_build_probe", "build_probe_not_successful"),
            ("placeholder", "placeholder_tests_not_allowed"),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir).resolve()
                executable = self._write_plan_workspace(workspace)
                if case == "failed_build_probe":
                    (workspace / "reports" / "build_probe_report.json").write_text(
                        json.dumps({"function": {"status": "failed"}}),
                        encoding="utf-8",
                    )
                else:
                    (workspace / "reports" / "harness_skeleton_report.json").write_text(
                        json.dumps(
                            {
                                "function": {"name": "sample"},
                                "unresolved_placeholders": [{"name": "expected_value"}],
                            }
                        ),
                        encoding="utf-8",
                    )
                before = self._tree_hashes(workspace)
                args = Namespace(
                    command="run-tests",
                    workspace=str(workspace),
                    executable=str(executable),
                    run=False,
                    plan=True,
                    dry_run=False,
                    timeout=60,
                    run_id="run-plan",
                    allow_placeholder_tests=False,
                    treat_placeholder_as_inconclusive=True,
                )

                result = handle_run_tests(args)

                self.assertEqual(before, self._tree_hashes(workspace))
                envelope = result.to_dict()
                self.assertEqual("planned", envelope["data"]["outcome"])
                self.assertIsNone(envelope["data"]["green"])
                self.assertEqual(0, envelope["data"]["exit_code"])
                self.assertIn(
                    expected_code,
                    {item["code"] for item in envelope["data"]["diagnostics"]},
                )

    def test_suite_plan_and_dry_run_alias_do_not_write_reports_or_run_entries(self):
        for mode in ("plan", "dry_run"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir).resolve()
                suite = root / "suite_manifest.json"
                suite.write_text('{"schema_version":"0.1","entries":[]}', encoding="utf-8")
                existing = root / "reports" / "existing.md"
                existing.parent.mkdir()
                existing.write_text("keep\n", encoding="utf-8")
                before = self._tree_hashes(root)
                args = Namespace(
                    command="suite-run",
                    suite=str(suite),
                    entry_ids=None,
                    tag=None,
                    all=True,
                    run=False,
                    plan=mode == "plan",
                    dry_run=mode == "dry_run",
                    fail_fast=False,
                    timeout=60,
                    require_green=True,
                )

                with mock.patch(
                    "unit_test_runner.cli.commands.run_suite",
                    side_effect=AssertionError("suite plan must not run suite entries"),
                ):
                    result = handle_suite_run(args)

                self.assertEqual(before, self._tree_hashes(root))
                self.assertIs(RunOutcome.PLANNED, result.outcome.state)
                self.assertEqual([], result.artifacts)
                self.assertEqual(
                    {
                        "reports/suite_run_report.json",
                        "reports/suite_run_report.md",
                        "reports/suite_run_report.csv",
                    },
                    {artifact.path for artifact in result.expected_artifacts},
                )
                diagnostic_codes = {
                    item["code"] for item in result.to_dict()["data"]["diagnostics"]
                }
                if mode == "dry_run":
                    self.assertIn("deprecated_dry_run_alias", diagnostic_codes)
                else:
                    self.assertNotIn("deprecated_dry_run_alias", diagnostic_codes)

    def test_suite_plan_read_only_validates_manifest_and_selected_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            suite = root / "suite_manifest.json"
            args = Namespace(
                command="suite-run",
                suite=str(suite),
                entry_ids=["missing-entry"],
                tag=None,
                all=False,
                run=False,
                plan=True,
                dry_run=False,
                fail_fast=False,
                timeout=60,
                require_green=False,
            )
            suite.write_text("{invalid", encoding="utf-8")
            before = self._tree_hashes(root)

            with self.assertRaises(CLIError):
                handle_suite_run(args)
            self.assertEqual(before, self._tree_hashes(root))

            suite.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "suite_id": "suite",
                        "entries": [
                            {
                                "entry_id": "known-entry",
                                "enabled": True,
                                "tags": ["selected"],
                                "function": {"name": "sample"},
                                "workspace": str(root / "workspace"),
                                "dossier": str(root / "workspace" / "reports" / "function_dossier.json"),
                                "test_execution_report": str(root / "workspace" / "reports" / "test_execution_report.json"),
                                "registered_at": "2026-07-12T00:00:00Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            before = self._tree_hashes(root)

            with self.assertRaisesRegex(CLIError, "missing-entry"):
                handle_suite_run(args)
            self.assertEqual(before, self._tree_hashes(root))

    def test_suite_plan_validates_selected_entry_prerequisites_without_writes(self):
        for case in ("missing_workspace", "missing_dossier", "missing_execution_preflight"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir).resolve()
                workspace = root / "workspace"
                dossier = workspace / "reports" / "function_dossier.json"
                if case != "missing_workspace":
                    workspace.mkdir(parents=True)
                if case == "missing_execution_preflight":
                    dossier.parent.mkdir(parents=True, exist_ok=True)
                    dossier.write_text(
                        json.dumps({"target": {"function": "sample", "source": "src/sample.c"}}),
                        encoding="utf-8",
                    )
                suite = root / "suite_manifest.json"
                suite.write_text(
                    json.dumps(
                        {
                            "schema_version": "0.1",
                            "suite_id": "suite",
                            "entries": [
                                {
                                    "entry_id": "sample-entry",
                                    "enabled": True,
                                    "tags": ["selected"],
                                    "function": {"name": "sample", "source": "src/sample.c"},
                                    "workspace": str(workspace),
                                    "dossier": str(dossier),
                                    "test_execution_report": str(
                                        workspace / "reports" / "test_execution_report.json"
                                    ),
                                    "registered_at": "2026-07-12T00:00:00Z",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                before = self._tree_hashes(root)
                args = Namespace(
                    command="suite-run",
                    suite=str(suite),
                    entry_ids=["sample-entry"],
                    tag=None,
                    all=False,
                    run=False,
                    plan=True,
                    dry_run=False,
                    fail_fast=False,
                    timeout=60,
                    require_green=False,
                )

                with mock.patch(
                    "unit_test_runner.cli.commands.run_suite",
                    side_effect=AssertionError("suite plan must not execute entries"),
                ), self.assertRaises(CLIError):
                    handle_suite_run(args)

                self.assertEqual(before, self._tree_hashes(root))

    def test_suite_plan_reports_entry_scoped_blockers_without_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            workspace = root / "workspace"
            self._write_plan_workspace(workspace)
            dossier = workspace / "reports" / "function_dossier.json"
            dossier.write_text(
                json.dumps({"target": {"function": "sample", "source": "src/sample.c"}}),
                encoding="utf-8",
            )
            (workspace / "reports" / "build_probe_report.json").write_text(
                json.dumps({"function": {"status": "failed"}}),
                encoding="utf-8",
            )
            suite = root / "suite_manifest.json"
            suite.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "suite_id": "suite",
                        "entries": [
                            {
                                "entry_id": "sample-entry",
                                "enabled": True,
                                "tags": ["selected"],
                                "function": {"name": "sample", "source": "src/sample.c"},
                                "workspace": str(workspace),
                                "dossier": str(dossier),
                                "test_execution_report": str(
                                    workspace / "reports" / "test_execution_report.json"
                                ),
                                "registered_at": "2026-07-12T00:00:00Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            before = self._tree_hashes(root)
            args = Namespace(
                command="suite-run",
                suite=str(suite),
                entry_ids=["sample-entry"],
                tag=None,
                all=False,
                run=False,
                plan=True,
                dry_run=False,
                fail_fast=False,
                timeout=60,
                require_green=False,
            )

            result = handle_suite_run(args)

            self.assertEqual(before, self._tree_hashes(root))
            envelope = result.to_dict()
            self.assertEqual("planned", envelope["data"]["outcome"])
            self.assertEqual(0, envelope["data"]["exit_code"])
            blockers = [
                item
                for item in envelope["data"]["diagnostics"]
                if item["code"] == "suite_entry_build_probe_not_successful"
            ]
            self.assertEqual(1, len(blockers))
            self.assertIn("sample-entry", blockers[0]["message"])

    def _write_plan_workspace(self, workspace: Path) -> Path:
        reports = workspace / "reports"
        source = workspace / "src" / "sample.c"
        executable = workspace / "bin" / "utr_probe.exe"
        reports.mkdir(parents=True, exist_ok=True)
        source.parent.mkdir(parents=True, exist_ok=True)
        executable.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("int sample(void) { return 0; }\n", encoding="utf-8")
        executable.write_bytes(b"runner")
        payloads = {
            "test_case_design.json": {
                "function": {"name": "sample"},
                "test_cases": [],
            },
            "harness_skeleton_report.json": {
                "function": {"name": "sample"},
                "unresolved_placeholders": [],
            },
            "build_probe_report.json": {"function": {"status": "succeeded"}},
            "build_workspace_report.json": {
                "function": {"name": "sample"},
                "source": {"path": "src/sample.c"},
            },
        }
        for name, payload in payloads.items():
            (reports / name).write_text(json.dumps(payload), encoding="utf-8")
        return executable


if __name__ == "__main__":
    unittest.main()
