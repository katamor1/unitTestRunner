import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_models import BuildProbeReport, BuildWorkspaceReport
from unit_test_runner.build.build_report_writer import write_build_reports
from unit_test_runner.dossier.artifact_collector import collect_artifacts
from unit_test_runner.harness.harness_models import HarnessGenerationPolicy, HarnessSkeletonReport
from unit_test_runner.harness.harness_report_writer import write_harness_report
from tests.windows_path_alias_support import (
    require_windows_path_alias_pair,
    temporary_windows_alias_directory,
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactProvenanceHashTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows 8.3 aliases require Windows")
    def test_build_report_records_long_generated_path_under_short_output_alias(self):
        with temporary_windows_alias_directory() as temp_dir:
            pair = require_windows_path_alias_pair(self, temp_dir)
            build = BuildWorkspaceReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="generated",
                output_root=pair.short,
                copied_files=[],
                referenced_files=[],
                generated_build_files=[],
                compile_units=[],
                link_units=[],
                include_dirs=[],
                defines=[],
                compiler_options=[],
                build_commands=[],
                diagnostics=[],
            )
            probe = BuildProbeReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="not_run",
                executed=False,
                exit_code=None,
                commands=[],
                diagnostics=[],
                missing_includes=[],
                unresolved_symbols=[],
                pch_issues=[],
                vc6_compatibility_issues=[],
                log_files=[],
            )
            try:
                write_build_reports(pair.short, build, probe)
            except ValueError as error:
                self.fail(f"long generated path must fit short output root: {error}")
            inventory = {
                item.workspace_path.as_posix()
                for item in build.generated_build_files
            }
            self.assertIn("build/UTR_Control_Update.dsp", inventory)

    def test_regenerated_report_inventories_only_hash_final_external_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            harness = HarnessSkeletonReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="partial",
                output_root=workspace,
                generation_policy=HarnessGenerationPolicy(),
                generated_files=[],
                stub_skeletons=[],
                test_skeletons=[],
                unresolved_placeholders=[],
                build_hints=[],
                warnings=[],
            )
            build = BuildWorkspaceReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="generated",
                output_root=workspace,
                copied_files=[],
                referenced_files=[],
                generated_build_files=[],
                compile_units=[],
                link_units=[],
                include_dirs=[],
                defines=[],
                compiler_options=[],
                build_commands=[],
                diagnostics=[],
            )
            probe = BuildProbeReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="not_run",
                executed=False,
                exit_code=None,
                commands=[],
                diagnostics=[],
                missing_includes=[],
                unresolved_symbols=[],
                pch_issues=[],
                vc6_compatibility_issues=[],
                log_files=[],
            )

            write_harness_report(workspace, harness)
            write_build_reports(workspace, build, probe)
            write_harness_report(workspace, harness)
            write_build_reports(workspace, build, probe)

            harness_payload = json.loads(
                (workspace / "reports" / "harness_skeleton_report.json").read_text(
                    encoding="utf-8"
                )
            )
            harness_files = {
                item["path"]: item for item in harness_payload["generated_files"]
            }
            self.assertIsNone(
                harness_files["reports/harness_skeleton_report.json"]["sha256"]
            )
            self._assert_recorded_hashes_match(
                workspace,
                harness_payload["generated_files"],
                "path",
                {"reports/harness_skeleton_report.json"},
            )

            build_payload = json.loads(
                (workspace / "reports" / "build_workspace_report.json").read_text(
                    encoding="utf-8"
                )
            )
            build_files = {
                item["workspace_path"]: item
                for item in build_payload["generated_build_files"]
            }
            self.assertIsNone(
                build_files["reports/build_workspace_report.json"]["sha256"]
            )
            self.assertFalse(
                build_files["reports/build_workspace_report.json"]["required"]
            )
            self._assert_recorded_hashes_match(
                workspace,
                build_payload["generated_build_files"],
                "workspace_path",
                {"reports/build_workspace_report.json"},
            )

            artifacts, _payloads, _warnings = collect_artifacts(workspace)
            external_index = {item.artifact_kind: item for item in artifacts}
            for kind, relative in [
                ("harness_skeleton_report", "reports/harness_skeleton_report.json"),
                ("build_workspace_report", "reports/build_workspace_report.json"),
            ]:
                self.assertEqual(
                    sha256(workspace / relative),
                    external_index[kind].sha256,
                )

    def _assert_recorded_hashes_match(
        self,
        workspace,
        entries,
        path_field,
        allowed_unhashed,
    ):
        self.assertEqual(
            allowed_unhashed,
            {entry[path_field] for entry in entries if entry["sha256"] is None},
        )
        for entry in entries:
            digest = entry["sha256"]
            if digest is None:
                continue
            path = workspace / entry[path_field]
            self.assertTrue(path.exists(), entry[path_field])
            self.assertEqual(sha256(path), digest, entry[path_field])


if __name__ == "__main__":
    unittest.main()
