from __future__ import annotations

import hashlib
import tempfile
import unittest
from argparse import Namespace
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch as mock_patch

import unit_test_runner.cli.commands as commands_module
import unit_test_runner.test_spec.patch as patch_module
import unit_test_runner.test_spec.repository as repository_module
from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import (
    InvalidTestSpecPatchError,
    TestSpec,
    apply_test_spec_patch,
    export_test_spec_views,
    load_test_spec,
    save_test_spec,
    update_test_spec,
)
from tests.spec_support import copied_payload, current_context
from tests.test_test_spec_cli import create_workspace


CASE_ID = "tc-control-update-001"


def replace(path: str, value):
    return {"op": "replace", "case_id": CASE_ID, "path": path, "value": value}


class TestSpecFormalReviewSnapshotTests(unittest.TestCase):
    def test_target_function_is_immutable_patch_identity(self):
        with self.assertRaises(InvalidTestSpecPatchError):
            apply_test_spec_patch(
                TestSpec.from_payload(copied_payload()),
                {"operations": [replace("/target_function", "Other_Function")]},
            )

    def test_numeric_list_index_aliases_and_prefixes_conflict(self):
        patches = (
            {
                "operations": [
                    replace(
                        "/expected_observations/0/expected_expression", "FIRST"
                    ),
                    replace(
                        "/expected_observations/00/expected_expression", "SECOND"
                    ),
                ]
            },
            {
                "operations": [
                    replace("/expected_observations/00", {}),
                    replace(
                        "/expected_observations/0/expected_expression", "SECOND"
                    ),
                ]
            },
        )
        for value in patches:
            with self.subTest(value=value):
                with self.assertRaises(InvalidTestSpecPatchError):
                    apply_test_spec_patch(TestSpec.from_payload(copied_payload()), value)

    def test_numeric_object_keys_remain_distinct_while_non_ascii_index_is_typed_error(self):
        spec = TestSpec.from_payload(copied_payload())
        observation = spec.test_cases[0]["expected_observations"][0]
        observation["0"] = "zero"
        observation["00"] = "double-zero"

        updated = apply_test_spec_patch(
            spec,
            {
                "operations": [
                    replace("/expected_observations/0/0", "ZERO"),
                    replace("/expected_observations/0/00", "DOUBLE-ZERO"),
                ]
            },
        )

        changed = updated.test_cases[0]["expected_observations"][0]
        self.assertEqual("ZERO", changed["0"])
        self.assertEqual("DOUBLE-ZERO", changed["00"])
        with self.assertRaises(InvalidTestSpecPatchError):
            apply_test_spec_patch(
                spec,
                {
                    "operations": [
                        replace(
                            "/expected_observations/²/expected_expression", "BAD"
                        )
                    ]
                },
            )

    def test_save_artifact_describes_writer_snapshot_after_interleaved_newer_commit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / "reports" / "test_spec.json"
            context = current_context(workspace)
            save_test_spec(
                path,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=context,
            )
            writer_a = load_test_spec(path, mode=ContractMode.STRICT)
            writer_a.test_cases[0]["title"] = "writer-a"
            writer_a_bytes = repository_module.canonical_json_bytes(
                writer_a.with_revision(2)
            )
            original_lock = repository_module._exclusive_lock
            interleaved = False

            @contextmanager
            def release_then_interleave(lock_path, *, timeout_seconds=10.0):
                nonlocal interleaved
                with original_lock(lock_path, timeout_seconds=timeout_seconds):
                    yield
                if not interleaved:
                    interleaved = True
                    writer_b = load_test_spec(path, mode=ContractMode.STRICT)
                    self.assertEqual(2, writer_b.revision)
                    writer_b.test_cases[0]["title"] = "writer-b"
                    save_test_spec(
                        path,
                        writer_b,
                        expected_revision=2,
                        current_context=context,
                    )

            with mock_patch.object(
                repository_module, "_exclusive_lock", release_then_interleave
            ):
                artifact = save_test_spec(
                    path,
                    writer_a,
                    expected_revision=1,
                    current_context=context,
                )

            persisted = load_test_spec(path, mode=ContractMode.STRICT)
            self.assertEqual(3, persisted.revision)
            self.assertEqual("writer-b", persisted.test_cases[0]["title"])
            self.assertEqual(hashlib.sha256(writer_a_bytes).hexdigest(), artifact.sha256)

    def test_update_returns_its_saved_spec_and_hash_after_interleaved_newer_commit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / "reports" / "test_spec.json"
            context = current_context(workspace)
            save_test_spec(
                path,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=context,
            )
            save_name = (
                "save_test_spec_snapshot"
                if hasattr(patch_module, "save_test_spec_snapshot")
                else "save_test_spec"
            )
            original_save = getattr(patch_module, save_name)
            interleaved = False

            def save_then_interleave(*args, **kwargs):
                nonlocal interleaved
                saved = original_save(*args, **kwargs)
                if not interleaved:
                    interleaved = True
                    writer_b = load_test_spec(path, mode=ContractMode.STRICT)
                    self.assertEqual(2, writer_b.revision)
                    writer_b.test_cases[0]["title"] = "writer-b"
                    repository_module.save_test_spec(
                        path,
                        writer_b,
                        expected_revision=2,
                        current_context=context,
                    )
                return saved

            with mock_patch.object(patch_module, save_name, save_then_interleave):
                updated, artifact = update_test_spec(
                    path,
                    {"operations": [replace("/title", "writer-a")]},
                    expected_revision=1,
                    current_context=context,
                )

            expected_bytes = repository_module.canonical_json_bytes(updated)
            self.assertEqual(2, updated.revision)
            self.assertEqual("writer-a", updated.test_cases[0]["title"])
            self.assertEqual(hashlib.sha256(expected_bytes).hexdigest(), artifact.sha256)
            self.assertEqual(3, load_test_spec(path, mode=ContractMode.STRICT).revision)

    def test_export_rejects_stale_caller_without_writing_mixed_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = workspace / "reports" / "test_spec.json"
            context = current_context(workspace)
            save_test_spec(
                canonical,
                TestSpec.from_payload(copied_payload()),
                expected_revision=None,
                current_context=context,
            )
            stale = load_test_spec(canonical, mode=ContractMode.STRICT)
            current = load_test_spec(canonical, mode=ContractMode.STRICT)
            current.test_cases[0]["title"] = "revision-two"
            save_test_spec(
                canonical,
                current,
                expected_revision=1,
                current_context=context,
            )

            with self.assertRaises(ValueError):
                export_test_spec_views(
                    stale, canonical.parent, canonical_path=canonical
                )

            self.assertFalse((canonical.parent / "test_spec.md").exists())
            self.assertFalse((canonical.parent / "test_spec.csv").exists())

    def test_cli_get_response_uses_one_snapshot_during_interleaved_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = create_workspace(workspace)
            initial = load_test_spec(path, mode=ContractMode.STRICT)
            context = commands_module.build_current_artifact_context(
                workspace, initial
            )
            loader_name = (
                "load_test_spec_snapshot"
                if hasattr(commands_module, "load_test_spec_snapshot")
                else "load_test_spec"
            )
            original_loader = getattr(commands_module, loader_name)
            interleaved = False

            def load_then_interleave(*args, **kwargs):
                nonlocal interleaved
                loaded = original_loader(*args, **kwargs)
                if not interleaved:
                    interleaved = True
                    writer_b = load_test_spec(path, mode=ContractMode.STRICT)
                    writer_b.test_cases[0]["title"] = "writer-b"
                    repository_module.save_test_spec(
                        path,
                        writer_b,
                        expected_revision=1,
                        current_context=context,
                    )
                return loaded

            with mock_patch.object(
                commands_module, loader_name, load_then_interleave
            ):
                result = commands_module.handle_get_test_spec(
                    Namespace(workspace=str(workspace), command="get-test-spec")
                )

            response_spec = TestSpec.from_payload(result.data["test_spec"])
            response_bytes = repository_module.canonical_json_bytes(response_spec)
            self.assertEqual(1, result.data["revision"])
            self.assertEqual(
                hashlib.sha256(response_bytes).hexdigest(), result.data["sha256"]
            )
            self.assertEqual(2, load_test_spec(path, mode=ContractMode.STRICT).revision)


if __name__ == "__main__":
    unittest.main()
