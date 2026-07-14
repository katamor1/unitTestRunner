from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import (
    TestSpec,
    TestSpecViewDurabilityError,
    export_test_spec_snapshot_views,
    load_test_spec,
    save_test_spec_snapshot,
)
from unit_test_runner.test_spec import exporters as exporter_module
from unit_test_runner.test_spec import repository as repository_module

from tests.spec_support import copied_payload, current_context


def _fail_csv_replace(source, destination):
    destination_path = Path(destination)
    if destination_path.name == "test_spec.csv":
        raise OSError("injected second view replace failure")
    return _fail_csv_replace.original(source, destination)


def _assert_no_residue(test: unittest.TestCase, reports: Path) -> None:
    test.assertFalse((reports / ".test_spec.json.lock").exists())
    test.assertEqual(
        [],
        [item.name for item in reports.iterdir() if item.name.endswith(".tmp")],
    )


class TestSpecFormalReviewExportAtomicityTests(unittest.TestCase):
    def test_fixed_views_retry_one_transient_windows_replace_permission_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = workspace / "reports" / "test_spec.json"
            snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=current_context(workspace),
            )
            original_replace = exporter_module.os.replace
            csv_attempts = 0

            def transient_replace(source, destination):
                nonlocal csv_attempts
                if Path(destination).name == "test_spec.csv":
                    csv_attempts += 1
                    if csv_attempts == 1:
                        raise PermissionError(
                            13,
                            "injected Windows sharing denial",
                        )
                return original_replace(source, destination)

            with mock_patch.object(
                repository_module,
                "_running_on_windows",
                return_value=True,
            ), mock_patch.object(
                repository_module.os,
                "replace",
                side_effect=transient_replace,
            ):
                views = export_test_spec_snapshot_views(
                    snapshot,
                    canonical.parent,
                    canonical_path=canonical,
                )

            self.assertEqual(2, csv_attempts)
            self.assertIn(snapshot.sha256, views["markdown"].read_text(encoding="utf-8"))
            self.assertIn(snapshot.sha256, views["csv"].read_text(encoding="utf-8"))
            _assert_no_residue(self, canonical.parent)

    def test_mismatched_existing_pair_is_rejected_without_visible_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = workspace / "reports" / "test_spec.json"
            context = current_context(workspace)
            old_snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=context,
            )
            views = export_test_spec_snapshot_views(
                old_snapshot,
                canonical.parent,
                canonical_path=canonical,
            )
            mismatched_csv = views["csv"].read_bytes().replace(
                old_snapshot.sha256.encode("ascii"),
                ("f" * 64).encode("ascii"),
            )
            views["csv"].write_bytes(mismatched_csv)
            before = (views["markdown"].read_bytes(), mismatched_csv)
            candidate = load_test_spec(canonical, mode=ContractMode.STRICT)
            candidate.test_cases[0]["title"] = "revision two"
            new_snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                candidate,
                expected_revision=1,
                current_context=context,
            )

            with self.assertRaisesRegex(
                ValueError,
                "do not describe one snapshot",
            ):
                export_test_spec_snapshot_views(
                    new_snapshot,
                    canonical.parent,
                    canonical_path=canonical,
                )

            self.assertEqual(
                before,
                (views["markdown"].read_bytes(), views["csv"].read_bytes()),
            )
            _assert_no_residue(self, canonical.parent)

    def test_rollback_failure_is_explicit_combined_durability_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = workspace / "reports" / "test_spec.json"
            context = current_context(workspace)
            old_snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=context,
            )
            export_test_spec_snapshot_views(
                old_snapshot,
                canonical.parent,
                canonical_path=canonical,
            )
            candidate = load_test_spec(canonical, mode=ContractMode.STRICT)
            candidate.test_cases[0]["title"] = "revision two"
            new_snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                candidate,
                expected_revision=1,
                current_context=context,
            )
            original_replace = exporter_module.os.replace

            def fail_commit_and_rollback(source, destination):
                source_path = Path(source)
                destination_path = Path(destination)
                if destination_path.name == "test_spec.csv":
                    raise OSError("injected commit failure")
                if (
                    destination_path.name == "test_spec.md"
                    and source_path.name.endswith(".rollback.tmp")
                ):
                    raise OSError("injected rollback failure")
                return original_replace(source, destination)

            with mock_patch.object(
                exporter_module.os,
                "replace",
                side_effect=fail_commit_and_rollback,
            ):
                with self.assertRaises(TestSpecViewDurabilityError) as raised:
                    export_test_spec_snapshot_views(
                        new_snapshot,
                        canonical.parent,
                        canonical_path=canonical,
                    )

            self.assertIn("injected commit failure", str(raised.exception))
            self.assertIn("injected rollback failure", str(raised.exception))
            _assert_no_residue(self, canonical.parent)

    def test_second_replace_failure_restores_exact_previous_view_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = workspace / "reports" / "test_spec.json"
            context = current_context(workspace)
            old_snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=context,
            )
            old_views = export_test_spec_snapshot_views(
                old_snapshot,
                canonical.parent,
                canonical_path=canonical,
            )
            old_markdown = old_views["markdown"].read_bytes()
            old_csv = old_views["csv"].read_bytes()
            candidate = load_test_spec(canonical, mode=ContractMode.STRICT)
            candidate.test_cases[0]["title"] = "revision two"
            new_snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                candidate,
                expected_revision=1,
                current_context=context,
            )
            _fail_csv_replace.original = exporter_module.os.replace

            with mock_patch.object(
                exporter_module.os,
                "replace",
                side_effect=_fail_csv_replace,
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "injected second view replace failure",
                ):
                    export_test_spec_snapshot_views(
                        new_snapshot,
                        canonical.parent,
                        canonical_path=canonical,
                    )

            self.assertEqual(old_markdown, old_views["markdown"].read_bytes())
            self.assertEqual(old_csv, old_views["csv"].read_bytes())
            _assert_no_residue(self, canonical.parent)

    def test_second_replace_failure_leaves_no_pair_when_none_existed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = workspace / "reports" / "test_spec.json"
            snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=current_context(workspace),
            )
            markdown = canonical.parent / "test_spec.md"
            csv_path = canonical.parent / "test_spec.csv"
            _fail_csv_replace.original = exporter_module.os.replace

            with mock_patch.object(
                exporter_module.os,
                "replace",
                side_effect=_fail_csv_replace,
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "injected second view replace failure",
                ):
                    export_test_spec_snapshot_views(
                        snapshot,
                        canonical.parent,
                        canonical_path=canonical,
                    )

            self.assertFalse(markdown.exists())
            self.assertFalse(csv_path.exists())
            _assert_no_residue(self, canonical.parent)

    def test_custom_symlink_alias_cannot_bypass_fixed_view_ordering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = workspace / "reports" / "test_spec.json"
            context = current_context(workspace)
            writer_a, _artifact = save_test_spec_snapshot(
                canonical,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=context,
            )
            candidate = load_test_spec(canonical, mode=ContractMode.STRICT)
            candidate.test_cases[0]["title"] = "writer-b"
            writer_b, _artifact = save_test_spec_snapshot(
                canonical,
                candidate,
                expected_revision=1,
                current_context=context,
            )
            views = export_test_spec_snapshot_views(
                writer_b,
                canonical.parent,
                canonical_path=canonical,
            )
            before = (views["markdown"].read_bytes(), views["csv"].read_bytes())
            alias = workspace / "custom-alias"
            try:
                alias.symlink_to(canonical.parent, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")

            with self.assertRaises(ValueError):
                export_test_spec_snapshot_views(
                    writer_a,
                    alias,
                    canonical_path=canonical,
                )

            self.assertEqual(
                before,
                (views["markdown"].read_bytes(), views["csv"].read_bytes()),
            )
            _assert_no_residue(self, canonical.parent)


if __name__ == "__main__":
    unittest.main()
