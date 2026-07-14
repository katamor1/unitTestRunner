from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch as mock_patch

from unit_test_runner.contracts import ContractMode
from unit_test_runner.cli import commands as commands_module
from unit_test_runner.dossier import workflow as dossier_workflow
from unit_test_runner.reanalysis import workflow as reanalysis_workflow
from unit_test_runner.reanalysis.reanalysis_models import ReanalysisPolicy
from unit_test_runner.test_spec import (
    TestSpec,
    load_test_spec,
    load_test_spec_snapshot,
    save_test_spec,
    save_test_spec_snapshot,
)
from unit_test_runner.test_spec import exporters as exporter_module
from unit_test_runner.test_spec import repository as repository_module

from tests.spec_support import copied_payload, current_context
from tests.windows_path_alias_support import (
    WINDOWS_8DOT3_PREFIX,
    require_windows_path_alias_pair,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


def _export_snapshot(snapshot, out_dir: Path, canonical: Path):
    snapshot_exporter = getattr(
        exporter_module,
        "export_test_spec_snapshot_views",
        None,
    )
    if snapshot_exporter is not None:
        return snapshot_exporter(
            snapshot,
            out_dir,
            canonical_path=canonical,
        )
    return exporter_module.export_test_spec_views(
        snapshot.spec,
        out_dir,
        canonical_path=canonical,
    )


def _interleaving_save(module, canonical: Path):
    save_name = (
        "save_test_spec_snapshot"
        if hasattr(module, "save_test_spec_snapshot")
        else "save_test_spec"
    )
    original = getattr(module, save_name)
    state = {"interleaved": False}

    def save_then_interleave(*args, **kwargs):
        result = original(*args, **kwargs)
        snapshot = (
            result[0]
            if isinstance(result, tuple)
            else load_test_spec_snapshot(canonical, mode=ContractMode.STRICT)
        )
        state["writer_a"] = snapshot
        if not state["interleaved"]:
            state["interleaved"] = True
            writer_b = load_test_spec(canonical, mode=ContractMode.STRICT)
            writer_b_snapshot, _artifact = repository_module.save_test_spec_snapshot(
                canonical,
                writer_b,
                expected_revision=writer_b.revision,
                current_context=kwargs["current_context"],
            )
            state["writer_b"] = writer_b_snapshot
            _export_snapshot(writer_b_snapshot, canonical.parent, canonical)
        return result

    return save_name, save_then_interleave, state


def _view_identity(markdown: Path, csv_path: Path) -> tuple[int, str]:
    markdown_text = markdown.read_text(encoding="utf-8")
    revision_line = next(
        line for line in markdown_text.splitlines() if line.startswith("- revision:")
    )
    sha_line = next(
        line
        for line in markdown_text.splitlines()
        if line.startswith("- canonical_sha256:")
    )
    revision = int(revision_line.split(":", 1)[1].strip())
    sha256 = sha_line.split(":", 1)[1].strip()
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise AssertionError("Generated TestSpec CSV has no rows.")
    if any(int(row["revision"]) != revision for row in rows):
        raise AssertionError("Markdown and CSV revisions differ.")
    if any(row["canonical_sha256"] != sha256 for row in rows):
        raise AssertionError("Markdown and CSV canonical hashes differ.")
    return revision, sha256


def _single_view_identity(path: Path) -> tuple[int, str]:
    if path.suffix.lower() == ".md":
        lines = path.read_text(encoding="utf-8").splitlines()
        revision = int(
            next(line for line in lines if line.startswith("- revision:"))
            .split(":", 1)[1]
            .strip()
        )
        sha256 = (
            next(
                line
                for line in lines
                if line.startswith("- canonical_sha256:")
            )
            .split(":", 1)[1]
            .strip()
        )
        return revision, sha256
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise AssertionError("Generated TestSpec CSV has no rows.")
    identities = {
        (int(row["revision"]), row["canonical_sha256"])
        for row in rows
    }
    if len(identities) != 1:
        raise AssertionError("Generated TestSpec CSV mixes snapshot identities.")
    return next(iter(identities))


class TestSpecFormalReviewWriterSnapshotTests(unittest.TestCase):
    def test_external_custom_view_cli_inventory_uses_explicit_output_root(self):
        for output_format in ("md", "csv"):
            with self.subTest(output_format=output_format), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                out = root / "canonical-workspace" / "Control_Update"
                external = root / "external-views" / f"review.{output_format}"
                dossier_workflow.analyze_function_workflow(
                    FIXTURE,
                    FIXTURE / "Product.dsw",
                    "src/control.c",
                    "Control_Update",
                    "Win32 Debug",
                    out,
                    "Control",
                    phase="design",
                )
                reports = out / "reports"
                canonical = reports / "test_spec.json"
                fixed_before = {
                    suffix: (reports / f"test_spec.{suffix}").read_bytes()
                    for suffix in ("md", "csv")
                }

                result = commands_module.handle_generate_test_design(
                    Namespace(
                        dossier=None,
                        function_signature=str(reports / "function_signature.json"),
                        global_access=str(reports / "global_access.json"),
                        call_report=str(reports / "call_report.json"),
                        coverage_design=str(reports / "coverage_design.json"),
                        boundary_candidates=str(
                            reports / "boundary_equivalence_candidates.json"
                        ),
                        format=output_format,
                        out=str(external),
                        command="generate-test-design",
                    )
                )

                self.assertEqual(0, result.exit_code)
                self.assertTrue(external.is_file())
                self.assertEqual(
                    {"test_spec", f"test_spec_{'markdown' if output_format == 'md' else 'csv'}"},
                    {artifact.kind for artifact in result.artifacts},
                )
                canonical_artifact = next(
                    artifact for artifact in result.artifacts if artifact.kind == "test_spec"
                )
                custom_artifact = next(
                    artifact for artifact in result.artifacts if artifact.kind != "test_spec"
                )
                self.assertEqual(
                    canonical.read_bytes(),
                    (out / canonical_artifact.path).read_bytes(),
                )
                self.assertEqual(
                    hashlib.sha256(canonical.read_bytes()).hexdigest(),
                    canonical_artifact.sha256,
                )
                self.assertEqual(external.name, custom_artifact.path)
                self.assertEqual(
                    external.read_bytes(),
                    (external.parent / custom_artifact.path).read_bytes(),
                )
                self.assertEqual(
                    hashlib.sha256(external.read_bytes()).hexdigest(),
                    custom_artifact.sha256,
                )
                revision, canonical_sha = _single_view_identity(external)
                self.assertEqual(result.data["saved_revision"], revision)
                self.assertEqual(result.data["saved_sha256"], canonical_sha)
                self.assertEqual(
                    fixed_before,
                    {
                        suffix: (reports / f"test_spec.{suffix}").read_bytes()
                        for suffix in ("md", "csv")
                    },
                )
                self.assertFalse(
                    list(external.parent.glob(f".{external.name}.*.tmp"))
                )

    def test_explicit_custom_views_render_writer_a_snapshot_and_inventory(self):
        for output_format in ("md", "csv"):
            for location in ("reports", "separate"):
                with self.subTest(
                    output_format=output_format,
                    location=location,
                ), tempfile.TemporaryDirectory(
                    prefix=WINDOWS_8DOT3_PREFIX
                ) as temp_dir:
                    root = Path(temp_dir)
                    if os.name == "nt":
                        root = require_windows_path_alias_pair(self, root).short
                    out = root / "Control_Update"
                    dossier_workflow.analyze_function_workflow(
                        FIXTURE,
                        FIXTURE / "Product.dsw",
                        "src/control.c",
                        "Control_Update",
                        "Win32 Debug",
                        out,
                        "Control",
                        phase="design",
                    )
                    reports = out / "reports"
                    canonical = reports / "test_spec.json"
                    save_name, save_hook, state = _interleaving_save(
                        dossier_workflow,
                        canonical,
                    )
                    destination_dir = (
                        reports if location == "reports" else out / "custom-views"
                    )
                    custom = destination_dir / f"writer-a.{output_format}"

                    with mock_patch.object(
                        dossier_workflow,
                        save_name,
                        save_hook,
                    ):
                        result = commands_module.handle_generate_test_design(
                            Namespace(
                                dossier=None,
                                function_signature=str(
                                    reports / "function_signature.json"
                                ),
                                global_access=str(reports / "global_access.json"),
                                call_report=str(reports / "call_report.json"),
                                coverage_design=str(
                                    reports / "coverage_design.json"
                                ),
                                boundary_candidates=str(
                                    reports
                                    / "boundary_equivalence_candidates.json"
                                ),
                                format=output_format,
                                out=str(custom),
                                command="generate-test-design",
                            )
                        )

                    custom_revision, custom_sha = _single_view_identity(custom)
                    fixed_revision, fixed_sha = _view_identity(
                        reports / "test_spec.md", reports / "test_spec.csv"
                    )
                    self.assertEqual(2, custom_revision)
                    self.assertEqual(state["writer_a"].sha256, custom_sha)
                    view_kind = f"test_spec_{'markdown' if output_format == 'md' else 'csv'}"
                    produced_view = next(
                        item for item in result.artifacts if item.kind == view_kind
                    )
                    self.assertEqual(
                        state["writer_a"].sha256,
                        result.data["saved_sha256"],
                    )
                    self.assertEqual(
                        custom.read_bytes(),
                        (out / produced_view.path).read_bytes(),
                    )
                    self.assertEqual(3, fixed_revision)
                    self.assertEqual(state["writer_b"].sha256, fixed_sha)
                    self.assertNotIn(
                        state["writer_b"].sha256,
                        {item.sha256 for item in result.artifacts},
                    )

    def test_generate_design_cli_reports_writer_a_without_claiming_writer_b_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "Control_Update"
            dossier_workflow.analyze_function_workflow(
                FIXTURE,
                FIXTURE / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out,
                "Control",
                phase="design",
            )
            reports = out / "reports"
            canonical = reports / "test_spec.json"
            save_name, save_hook, state = _interleaving_save(
                dossier_workflow,
                canonical,
            )

            with mock_patch.object(dossier_workflow, save_name, save_hook):
                result = commands_module.handle_generate_test_design(
                    Namespace(
                        dossier=None,
                        function_signature=str(reports / "function_signature.json"),
                        global_access=str(reports / "global_access.json"),
                        call_report=str(reports / "call_report.json"),
                        coverage_design=str(reports / "coverage_design.json"),
                        boundary_candidates=str(
                            reports / "boundary_equivalence_candidates.json"
                        ),
                        format="all",
                        out=None,
                        command="generate-test-design",
                    )
                )

            fixed_revision, fixed_sha = _view_identity(
                reports / "test_spec.md", reports / "test_spec.csv"
            )
            self.assertEqual(2, result.data["saved_revision"])
            self.assertEqual(state["writer_a"].sha256, result.data["saved_sha256"])
            self.assertFalse(result.data["views_written_by_operation"])
            self.assertEqual(1, len(result.artifacts))
            self.assertEqual("test_spec", result.artifacts[0].kind)
            self.assertEqual(state["writer_a"].sha256, result.artifacts[0].sha256)
            self.assertEqual(3, fixed_revision)
            self.assertEqual(state["writer_b"].sha256, fixed_sha)

    def test_cli_update_does_not_claim_newer_writers_fixed_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "Control_Update"
            dossier_workflow.analyze_function_workflow(
                FIXTURE,
                FIXTURE / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out,
                "Control",
                phase="design",
            )
            canonical = out / "reports" / "test_spec.json"
            initial = load_test_spec(canonical, mode=ContractMode.STRICT)
            cases = initial.test_cases + initial.additional_case_candidates
            self.assertTrue(cases)
            patch_path = out / "patch.json"
            patch_path.write_text(
                json.dumps(
                    {
                        "operations": [
                            {
                                "op": "replace",
                                "case_id": cases[0]["test_case_id"],
                                "path": "/title",
                                "value": "writer-a",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            original_update = commands_module.update_test_spec_snapshot
            state = {}

            def update_then_interleave(*args, **kwargs):
                writer_a_snapshot, artifact = original_update(*args, **kwargs)
                state["writer_a"] = writer_a_snapshot
                writer_b = load_test_spec(canonical, mode=ContractMode.STRICT)
                writer_b_snapshot, _writer_b_artifact = save_test_spec_snapshot(
                    canonical,
                    writer_b,
                    expected_revision=2,
                    current_context=kwargs["current_context"],
                )
                state["writer_b"] = writer_b_snapshot
                _export_snapshot(writer_b_snapshot, canonical.parent, canonical)
                return writer_a_snapshot, artifact

            with mock_patch.object(
                commands_module,
                "update_test_spec_snapshot",
                update_then_interleave,
            ):
                result = commands_module.handle_update_test_spec(
                    Namespace(
                        workspace=str(out),
                        patch=str(patch_path),
                        expected_revision=1,
                        command="update-test-spec",
                    )
                )

            fixed_revision, fixed_sha = _view_identity(
                canonical.parent / "test_spec.md",
                canonical.parent / "test_spec.csv",
            )
            self.assertEqual(2, result.data["revision"])
            self.assertEqual(state["writer_a"].sha256, result.data["sha256"])
            self.assertFalse(result.data["views_written_by_operation"])
            self.assertEqual(1, len(result.artifacts))
            self.assertEqual("test_spec", result.artifacts[0].kind)
            self.assertEqual(state["writer_a"].sha256, result.artifacts[0].sha256)
            self.assertEqual(3, fixed_revision)
            self.assertEqual(state["writer_b"].sha256, fixed_sha)

    def test_fixed_views_never_end_older_after_newer_writer_completes(self):
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
            writer_a = load_test_spec(canonical, mode=ContractMode.STRICT)
            writer_a.test_cases[0]["title"] = "writer-a"
            writer_a_snapshot, _artifact = save_test_spec_snapshot(
                canonical,
                writer_a,
                expected_revision=1,
                current_context=context,
            )
            a_rendering = threading.Event()
            release_a = threading.Event()
            b_complete = threading.Event()
            failures: list[BaseException] = []
            original_render = exporter_module._render_markdown
            original_open = repository_module.os.open
            lock_denials = 0

            def blocking_render(spec, canonical_sha):
                if threading.current_thread().name == "writer-a":
                    a_rendering.set()
                    if not release_a.wait(timeout=10):
                        raise TimeoutError("writer A was not released")
                return original_render(spec, canonical_sha)

            def transient_lock_open(path, flags):
                nonlocal lock_denials
                if (
                    threading.current_thread().name == "writer-b"
                    and Path(path) == canonical.parent / ".test_spec.json.lock"
                    and lock_denials == 0
                ):
                    lock_denials += 1
                    raise PermissionError(
                        13,
                        "injected Windows sharing denial",
                    )
                return original_open(path, flags)

            def export_a():
                try:
                    _export_snapshot(writer_a_snapshot, canonical.parent, canonical)
                except BaseException as error:  # pragma: no cover - surfaced below
                    failures.append(error)

            def save_and_export_b():
                try:
                    writer_b = load_test_spec(canonical, mode=ContractMode.STRICT)
                    writer_b.test_cases[0]["title"] = "writer-b"
                    writer_b_snapshot, _artifact = save_test_spec_snapshot(
                        canonical,
                        writer_b,
                        expected_revision=2,
                        current_context=context,
                    )
                    _export_snapshot(writer_b_snapshot, canonical.parent, canonical)
                    b_complete.set()
                except BaseException as error:  # pragma: no cover - surfaced below
                    failures.append(error)

            with mock_patch.object(
                exporter_module,
                "_render_markdown",
                blocking_render,
            ), mock_patch.object(
                repository_module,
                "_running_on_windows",
                return_value=True,
            ), mock_patch.object(
                repository_module.os,
                "open",
                side_effect=transient_lock_open,
            ):
                thread_a = threading.Thread(target=export_a, name="writer-a")
                thread_a.start()
                self.assertTrue(a_rendering.wait(timeout=5))
                thread_b = threading.Thread(target=save_and_export_b, name="writer-b")
                thread_b.start()
                b_complete.wait(timeout=2)
                release_a.set()
                thread_a.join(timeout=15)
                thread_b.join(timeout=15)

            self.assertFalse(thread_a.is_alive())
            self.assertFalse(thread_b.is_alive())
            if failures:
                raise failures[0]
            self.assertEqual(1, lock_denials)
            revision, _sha256 = _view_identity(
                canonical.parent / "test_spec.md",
                canonical.parent / "test_spec.csv",
            )
            self.assertEqual(3, revision)
            self.assertFalse((canonical.parent / ".test_spec.json.lock").exists())
            self.assertEqual(
                [],
                [
                    item.name
                    for item in canonical.parent.iterdir()
                    if item.name.endswith(".tmp")
                ],
            )

    def test_dossier_analyze_uses_its_rev2_snapshot_after_rev3_interleave(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "Control_Update"
            dossier_workflow.analyze_function_workflow(
                FIXTURE,
                FIXTURE / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out,
                "Control",
                phase="design",
            )
            canonical = out / "reports" / "test_spec.json"
            save_name, save_hook, state = _interleaving_save(
                dossier_workflow,
                canonical,
            )
            downstream_revisions: list[int] = []
            original_harness = dossier_workflow.generate_harness_skeleton

            def capture_harness(*args, **kwargs):
                downstream_revisions.append(int(args[3]["revision"]))
                return original_harness(*args, **kwargs)

            with mock_patch.object(dossier_workflow, save_name, save_hook), mock_patch.object(
                dossier_workflow,
                "generate_harness_skeleton",
                capture_harness,
            ):
                dossier_workflow.analyze_function_workflow(
                    FIXTURE,
                    FIXTURE / "Product.dsw",
                    "src/control.c",
                    "Control_Update",
                    "Win32 Debug",
                    out,
                    "Control",
                    phase="harness",
                )

            self.assertEqual(2, state["writer_a"].spec.revision)
            self.assertEqual(3, state["writer_b"].spec.revision)
            self.assertEqual([2], downstream_revisions)

    def test_report_to_spec_exports_its_rev2_snapshot_after_rev3_interleave(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "Control_Update"
            dossier_workflow.analyze_function_workflow(
                FIXTURE,
                FIXTURE / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out,
                "Control",
                phase="design",
            )
            reports = out / "reports"
            canonical = reports / "test_spec.json"
            save_name, save_hook, state = _interleaving_save(
                dossier_workflow,
                canonical,
            )
            operation_views = out / "operation-views"

            with mock_patch.object(dossier_workflow, save_name, save_hook):
                result = dossier_workflow.generate_test_design_from_reports(
                    reports / "function_signature.json",
                    reports / "global_access.json",
                    reports / "call_report.json",
                    reports / "coverage_design.json",
                    reports / "boundary_equivalence_candidates.json",
                    "all",
                    operation_views,
                )

            operation_revision, operation_sha = _view_identity(
                result["markdown"], result["csv"]
            )
            fixed_revision, fixed_sha = _view_identity(
                reports / "test_spec.md", reports / "test_spec.csv"
            )
            self.assertEqual(2, state["writer_a"].spec.revision)
            self.assertEqual(2, operation_revision)
            self.assertEqual(state["writer_a"].sha256, operation_sha)
            self.assertEqual(3, fixed_revision)
            self.assertEqual(state["writer_b"].sha256, fixed_sha)

    def test_reanalysis_returns_its_rev2_snapshot_after_rev3_interleave(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            product = root / "product"
            shutil.copytree(FIXTURE, product)
            out = root / "Control_Update"
            dossier_workflow.analyze_function_workflow(
                product,
                product / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out,
                "Control",
                phase="design",
            )
            source = product / "src" / "control.c"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    "sensor_value < SENSOR_MIN",
                    "sensor_value <= SENSOR_MIN",
                ),
                encoding="utf-8",
            )
            canonical = out / "reports" / "test_spec.json"
            save_name, save_hook, state = _interleaving_save(
                reanalysis_workflow,
                canonical,
            )

            with mock_patch.object(reanalysis_workflow, save_name, save_hook):
                result = reanalysis_workflow.reanalyze_function_workflow(
                    product,
                    product / "Product.dsw",
                    "src/control.c",
                    "Control_Update",
                    "Win32 Debug",
                    out,
                    project_name="Control",
                    policy=ReanalysisPolicy(
                        generate_updated_test_case_design=True,
                        overwrite_test_case_design=True,
                    ),
                )

            fixed_revision, fixed_sha = _view_identity(
                canonical.parent / "test_spec.md",
                canonical.parent / "test_spec.csv",
            )
            self.assertEqual(2, state["writer_a"].spec.revision)
            self.assertEqual(3, state["writer_b"].spec.revision)
            self.assertEqual(2, result["test_spec_revision"])
            self.assertEqual(3, fixed_revision)
            self.assertEqual(state["writer_b"].sha256, fixed_sha)


if __name__ == "__main__":
    unittest.main()
