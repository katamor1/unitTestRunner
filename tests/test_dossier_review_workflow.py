import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier import analyze_function_workflow
from unit_test_runner.contracts import ArtifactKind, ContractMode, load_artifact
from unit_test_runner.dossier.dossier_models import DossierNextAction, DossierUnresolvedItem
from unit_test_runner.dossier.finalizer import finalize_function_dossier, prepare_review_from_dossier
from unit_test_runner.dossier.review_workflow import build_review_items
from unit_test_runner.review_ids import build_function_id, build_review_id
from unit_test_runner.reports.next_actions_markdown import render_next_actions_markdown
from unit_test_runner.reports.unresolved_items_markdown import render_unresolved_items_markdown


class HostileString(str):
    def __contains__(self, _item):
        return False

    def replace(self, *_args, **_kwargs):
        return "src/attacker.c"

    def strip(self, *_args, **_kwargs):
        return "attacker"

    def lower(self):
        return "attacker"

    def encode(self, *_args, **_kwargs):
        return b"attacker"


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class DossierReviewWorkflowTests(unittest.TestCase):
    @staticmethod
    def review_artifact(kind, *, exists=True, status="valid", version="1.0.0"):
        return SimpleNamespace(
            artifact_kind=kind,
            exists=exists,
            contract_status=status,
            schema_version=version,
        )

    @staticmethod
    def strict_core_payloads():
        source = {"path": "src/control.c", "sha256": "1" * 64}
        return {
            "source_digest": {"source": dict(source)},
            "function_location": {
                "source": dict(source),
                "function": {"name": "Control_Update"},
            },
            "function_signature": {
                "source": dict(source),
                "function": {"name": "Control_Update"},
            },
        }

    @classmethod
    def strict_core_artifacts(cls):
        return [
            cls.review_artifact("source_digest"),
            cls.review_artifact("function_location"),
            cls.review_artifact("function_signature"),
        ]

    @staticmethod
    def strict_test_spec_payload():
        function_id = build_function_id("src/control.c", "Control_Update")
        return {
            "spec_id": "spec-control-update",
            "revision": 1,
            "source": {"path": "src/control.c", "sha256": "1" * 64},
            "function": {
                "function_id": function_id,
                "name": "Control_Update",
                "signature_sha256": "2" * 64,
            },
            "test_cases": [],
            "additional_case_candidates": [],
            "unresolved_items": [],
            "review_item_ids": [],
        }

    def test_semantic_review_ids_ignore_order_and_localized_display_text(self):
        function_id = build_function_id("src/control.c", "Control_Update")
        base_unresolved = [
            {
                "item_id": "legacy-1",
                "item_kind": "expected_return_unknown",
                "description": "English display text",
                "related_test_case_ids": ["TC-01"],
                "suggested_action": "Review it",
            },
            {
                "item_id": "legacy-2",
                "item_kind": "expected_global_unknown",
                "description": "Another display text",
                "related_test_case_ids": ["TC-02"],
                "suggested_action": "Review that",
            },
        ]
        first_payload = {
            "test_spec": {
                "function": {"function_id": function_id, "name": "Control_Update"},
                "source": {"path": "src/control.c"},
                "unresolved_items": base_unresolved,
                "test_cases": [],
            }
        }
        localized = [dict(item) for item in reversed(base_unresolved)]
        localized[0]["description"] = "表示文言を変更"
        localized[0]["suggested_action"] = "仕様を確認"
        second_payload = {
            "test_spec": {
                **first_payload["test_spec"],
                "unresolved_items": localized,
            }
        }

        first, _ = build_review_items(first_payload)
        second, _ = build_review_items(second_payload)
        first_ids = {item.review_id for item in first}
        second_ids = {item.review_id for item in second}

        self.assertEqual(first_ids, second_ids)
        self.assertEqual(
            {
                build_review_id(
                    "expected_result_review",
                    function_id,
                    "TC-01",
                    "expected_return_unknown",
                ),
                build_review_id(
                    "expected_result_review",
                    function_id,
                    "TC-02",
                    "expected_global_unknown",
                ),
            },
            first_ids,
        )

        changed = [dict(item) for item in base_unresolved]
        changed[0]["item_kind"] = "expected_buffer_unknown"
        changed_items, _ = build_review_items(
            {
                "test_spec": {
                    **first_payload["test_spec"],
                    "unresolved_items": changed,
                }
            }
        )
        self.assertNotEqual(first_ids, {item.review_id for item in changed_items})

    def test_direct_test_spec_associates_equivalent_case_spellings_once(self):
        function_id = build_function_id("src/control.c", "Control_Update")
        expected_review_id = build_review_id(
            "expected_result_review",
            function_id,
            "TC-01",
            "expected_return_unknown",
        )
        for label, related_case_id in (
            ("outer_whitespace", " TC-01 "),
            ("nfkc_fullwidth_hyphen", "TC－01"),
            ("separator_equivalent", "TC_01"),
        ):
            with self.subTest(spelling=label):
                payload = self.strict_test_spec_payload()
                payload["unresolved_items"] = [
                    {
                        "item_kind": "expected_return_unknown",
                        "related_test_case_ids": [related_case_id],
                    }
                ]
                payload["additional_case_candidates"] = [
                    {
                        "test_case_id": "TC-01",
                        "review_item_ids": [expected_review_id],
                    }
                ]
                payload["review_item_ids"] = [expected_review_id]

                review_items, unresolved = build_review_items(
                    {"test_spec": payload}
                )

                self.assertEqual(
                    [expected_review_id],
                    [item.review_id for item in review_items],
                )
                self.assertEqual(1, len(unresolved))
                self.assertEqual(["TC-01"], review_items[0].related_test_cases)
                self.assertEqual(["TC-01"], unresolved[0].related_test_cases)

    def test_direct_test_spec_rejects_ambiguous_normalized_case_spellings(self):
        payload = self.strict_test_spec_payload()
        payload["additional_case_candidates"] = [
            {"test_case_id": "TC-01"},
            {"test_case_id": "TC_01"},
        ]

        with self.assertRaisesRegex(ValueError, "Ambiguous test case IDs"):
            build_review_items({"test_spec": payload})

    def test_harness_and_build_review_ids_ignore_order_and_display_text(self):
        function_id = build_function_id("src/control.c", "Control_Update")
        identity = {
            "function": {"function_id": function_id, "name": "Control_Update"},
            "source": {"path": "src/control.c"},
            "unresolved_items": [],
            "test_cases": [],
        }
        placeholders = [
            {
                "placeholder_id": "ordinal-1",
                "placeholder_kind": "expected_return",
                "name": "TBD_RETURN",
                "related_test_case_id": "TC-01",
                "related_stub_name": None,
                "reason": "display one",
                "suggested_action": "display action one",
            },
            {
                "placeholder_id": "ordinal-2",
                "placeholder_kind": "stub_return",
                "name": "TBD_STUB",
                "related_test_case_id": "TC-02",
                "related_stub_name": "ReadSensor",
                "reason": "display two",
                "suggested_action": "display action two",
            },
        ]
        manual = [
            {
                "item_id": "MANUAL_001",
                "item_kind": "include_path_review",
                "description": "display include",
                "reason": "display reason",
                "suggested_action": "display action",
                "related_diagnostic_raw": "fatal C1083: sensor.h",
            },
            {
                "item_id": "MANUAL_002",
                "item_kind": "target_source_issue",
                "description": "display target",
                "reason": "display reason",
                "suggested_action": "display action",
                "related_diagnostic_raw": "error C2065: symbol",
            },
        ]
        first_payload = {
            "test_spec": identity,
            "harness_skeleton_report": {"unresolved_placeholders": placeholders},
            "build_completion_plan": {"manual_action_items": manual},
        }
        localized_placeholders = [dict(item) for item in reversed(placeholders)]
        localized_placeholders[0]["reason"] = "表示理由"
        localized_placeholders[0]["suggested_action"] = "表示手順"
        localized_manual = [dict(item) for item in reversed(manual)]
        localized_manual[0]["description"] = "表示説明"
        localized_manual[0]["suggested_action"] = "表示手順"
        localized_manual[0]["related_diagnostic_raw"] = "診断テキストを変更"
        second_payload = {
            "test_spec": identity,
            "harness_skeleton_report": {
                "unresolved_placeholders": localized_placeholders
            },
            "build_completion_plan": {"manual_action_items": localized_manual},
        }

        first, _ = build_review_items(first_payload)
        second, _ = build_review_items(second_payload)

        self.assertEqual(
            {item.review_id for item in first},
            {item.review_id for item in second},
        )
        self.assertTrue(
            all(item.review_id.startswith("review-") for item in first),
            first,
        )

    def test_harness_semantic_subject_is_injective_and_null_preserving(self):
        function_id = build_function_id("src/control.c", "Control_Update")
        identity = {
            "function": {"function_id": function_id, "name": "Control_Update"},
            "source": {"path": "src/control.c"},
            "unresolved_items": [],
            "test_cases": [],
        }

        def review_id(*, kind, name, stub_marker):
            placeholder = {
                "placeholder_kind": kind,
                "name": name,
                "related_test_case_id": "TC-01",
                "suggested_action": "display only",
            }
            if stub_marker != "missing":
                placeholder["related_stub_name"] = stub_marker
            items, _ = build_review_items(
                {
                    "test_spec": identity,
                    "harness_skeleton_report": {
                        "unresolved_placeholders": [placeholder]
                    },
                }
            )
            self.assertEqual(1, len(items))
            return items[0].review_id

        self.assertNotEqual(
            review_id(kind="expected_return", name="TBD", stub_marker="missing"),
            review_id(kind="expected_return", name="TBD", stub_marker="none"),
        )
        self.assertNotEqual(
            review_id(kind="a|name=b", name="c", stub_marker="missing"),
            review_id(kind="a", name="b|name=c", stub_marker="missing"),
        )

    def test_workflow_rejects_string_subclasses_in_semantic_identity(self):
        function_id = build_function_id("src/control.c", "Control_Update")
        base = self.strict_test_spec_payload()
        mutations = (
            ("function_id", HostileString(function_id)),
            ("function_name", HostileString("Control_Update")),
            ("source_path", HostileString("src/control.c")),
            ("item_kind", HostileString("expected_return_unknown")),
            ("case_id", HostileString("TC-01")),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                payload = json.loads(json.dumps(base))
                payload["unresolved_items"] = [
                    {
                        "item_kind": (
                            value
                            if field == "item_kind"
                            else "expected_return_unknown"
                        ),
                        "related_test_case_ids": [
                            value if field == "case_id" else "TC-01"
                        ],
                    }
                ]
                if field == "function_id":
                    payload["function"]["function_id"] = value
                elif field == "function_name":
                    payload["function"]["name"] = value
                elif field == "source_path":
                    payload["source"]["path"] = value
                with self.assertRaises(TypeError):
                    build_review_items({"test_spec": payload})

    def test_workflow_rejects_subclasses_in_all_producer_semantic_fields(self):
        function_id = build_function_id("src/control.c", "Control_Update")
        identity = {
            "function": {"function_id": function_id, "name": "Control_Update"},
            "source": {"path": "src/control.c"},
            "unresolved_items": [],
            "test_cases": [],
        }
        harness_mutations = (
            ("placeholder_kind", HostileString("expected_return")),
            ("name", HostileString("TBD_RETURN")),
            ("related_stub_name", HostileString("ReadSensor")),
            ("related_test_case_id", HostileString("TC-01")),
        )
        for field, value in harness_mutations:
            with self.subTest(producer="harness", field=field):
                placeholder = {
                    "placeholder_kind": "expected_return",
                    "name": "TBD_RETURN",
                    "related_stub_name": "ReadSensor",
                    "related_test_case_id": "TC-01",
                }
                placeholder[field] = value
                with self.assertRaises(TypeError):
                    build_review_items(
                        {
                            "test_spec": identity,
                            "harness_skeleton_report": {
                                "unresolved_placeholders": [placeholder]
                            },
                        }
                    )

        with self.assertRaises(TypeError):
            build_review_items(
                {
                    "test_spec": identity,
                    "build_completion_plan": {
                        "manual_action_items": [
                            {
                                "item_kind": HostileString("include_path_review"),
                                "description": "display",
                            }
                        ]
                    },
                }
            )

        with self.assertRaises(TypeError):
            build_review_items(
                {
                    "test_spec": identity,
                    "test_execution_report": {
                        "status": HostileString("failed")
                    },
                }
            )

    def test_artifact_metadata_rejects_duplicates_and_malformed_records(self):
        payloads = {
            **self.strict_core_payloads(),
            "test_spec": self.strict_test_spec_payload(),
        }
        valid = self.review_artifact("test_spec", version="1.1.0")
        invalid = self.review_artifact(
            "test_spec",
            status="schema_error",
            version="1.1.0",
        )
        for records in ((valid, invalid), (invalid, valid)):
            with self.subTest(order=[item.contract_status for item in records]):
                with self.assertRaises(ValueError):
                    build_review_items(payloads, artifacts=records)

        malformed_records = (
            SimpleNamespace(),
            SimpleNamespace(
                artifact_kind=HostileString("extra"),
                exists=True,
                contract_status="valid",
                schema_version=None,
            ),
            SimpleNamespace(
                artifact_kind="extra",
                exists=1,
                contract_status="valid",
                schema_version=None,
            ),
            SimpleNamespace(
                artifact_kind="extra",
                exists=True,
                contract_status=HostileString("valid"),
                schema_version=None,
            ),
            SimpleNamespace(
                artifact_kind="extra",
                exists=True,
                contract_status="valid",
                schema_version=1,
            ),
        )
        for malformed in malformed_records:
            with self.subTest(record=repr(malformed)):
                with self.assertRaises((TypeError, ValueError)):
                    build_review_items(
                        payloads,
                        artifacts=(valid, malformed),
                    )

        items, _ = build_review_items(
            payloads,
            artifacts=(
                valid,
                self.review_artifact("test_result_csv", version=None),
            ),
        )
        self.assertEqual(1, len(items))

    def test_generic_review_prefers_strict_current_test_spec_subject(self):
        test_spec = self.strict_test_spec_payload()
        artifacts = self.strict_core_artifacts() + [
            self.review_artifact("test_spec", version="1.1.0")
        ]

        items, _ = build_review_items(
            {**self.strict_core_payloads(), "test_spec": test_spec},
            artifacts=artifacts,
        )

        self.assertEqual(1, len(items))
        self.assertEqual(["test_spec"], items[0].related_artifacts)
        self.assertEqual(
            build_review_id(
                "evidence_review",
                test_spec["function"]["function_id"],
                None,
                "final_dossier_review",
            ),
            items[0].review_id,
        )

    def test_generic_review_uses_strict_core_only_when_test_spec_is_absent(self):
        artifacts = self.strict_core_artifacts() + [
            self.review_artifact(
                "test_spec", exists=False, status="missing", version=None
            )
        ]

        items, _ = build_review_items(
            self.strict_core_payloads(),
            artifacts=artifacts,
        )

        function_id = build_function_id("src/control.c", "Control_Update")
        self.assertEqual(1, len(items))
        self.assertEqual(
            ["source_digest", "function_location", "function_signature"],
            items[0].related_artifacts,
        )
        self.assertEqual(
            build_review_id(
                "evidence_review",
                function_id,
                None,
                "final_dossier_review",
            ),
            items[0].review_id,
        )
        strict_items, _ = build_review_items(
            {
                **self.strict_core_payloads(),
                "test_spec": self.strict_test_spec_payload(),
            },
            artifacts=self.strict_core_artifacts()
            + [self.review_artifact("test_spec", version="1.1.0")],
        )
        self.assertEqual(strict_items[0].review_id, items[0].review_id)

    def test_generic_review_fails_closed_for_present_noncurrent_or_no_subject(self):
        core_payloads = self.strict_core_payloads()
        core_artifacts = self.strict_core_artifacts()
        test_spec = self.strict_test_spec_payload()
        test_spec["unresolved_items"] = [
            {
                "item_id": "LEGACY_RAW_001",
                "item_kind": "expected_return_unknown",
                "description": "must not become decisionable",
                "related_test_case_ids": ["TC-01"],
            }
        ]
        test_spec["additional_case_candidates"] = [
            {
                "test_case_id": "TC-01",
                "review_item_ids": ["LEGACY_RAW_001"],
                "coverage_links": [],
            }
        ]
        scenarios = {
            "invalid": self.review_artifact(
                "test_spec", status="schema_error", version="1.1.0"
            ),
            "legacy": self.review_artifact("test_spec", version="1.0.0"),
            "mismatched": self.review_artifact(
                "test_spec", status="stale", version="1.1.0"
            ),
        }

        for name, test_spec_artifact in scenarios.items():
            with self.subTest(name=name):
                items, _ = build_review_items(
                    {**core_payloads, "test_spec": test_spec},
                    artifacts=core_artifacts + [test_spec_artifact],
                )
                self.assertEqual([], items)

        absent = self.review_artifact(
            "test_spec", exists=False, status="missing", version=None
        )
        incomplete_core = core_artifacts[:-1] + [
            self.review_artifact(
                "function_signature", exists=False, status="missing", version=None
            )
        ]
        items, _ = build_review_items(
            core_payloads,
            artifacts=incomplete_core + [absent],
        )
        self.assertEqual([], items)

        mismatched_identity = self.strict_test_spec_payload()
        mismatched_identity["function"]["function_id"] = "fn_wrong_identity"
        items, _ = build_review_items(
            {**core_payloads, "test_spec": mismatched_identity},
            artifacts=core_artifacts
            + [self.review_artifact("test_spec", version="1.1.0")],
        )
        self.assertEqual([], items)

    def test_execution_outcome_is_normalized_before_dossier_persistence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "normalized-execution"
            execution = SimpleNamespace(
                status="passed",
                executed=False,
                parsed_result=SimpleNamespace(
                    total=0,
                    passed=0,
                    failed=0,
                    inconclusive=0,
                    crashed=0,
                    not_run=0,
                ),
                run_paths=None,
            )
            manifest = SimpleNamespace(
                summary=SimpleNamespace(test_execution_status="passed"),
                evidence_paths=None,
            )

            with mock.patch(
                "unit_test_runner.dossier.workflow.prepare_test_execution_evidence",
                return_value=(execution, manifest),
            ):
                returned = analyze_function_workflow(
                    VC6_FIXTURE_ROOT,
                    VC6_FIXTURE_ROOT / "Product.dsw",
                    "src/control.c",
                    "Control_Update",
                    "Win32 Debug",
                    out_dir,
                    "Control",
                    run_tests=True,
                    phase="execution",
                )

            persisted = json.loads(
                (out_dir / "reports" / "function_dossier.json").read_text(encoding="utf-8")
            )
            for dossier in (returned, persisted):
                self.assertEqual("inconclusive", dossier["test_execution"]["status"])
                self.assertFalse(dossier["test_execution"]["green"])
                self.assertEqual("inconclusive", dossier["evidence"]["status"])

    def prepare_workspace(self, temp_dir):
        out_dir = Path(temp_dir) / "Control_Update"
        analyze_function_workflow(
            VC6_FIXTURE_ROOT,
            VC6_FIXTURE_ROOT / "Product.dsw",
            "src/control.c",
            "Control_Update",
            "Win32 Debug",
            out_dir,
            "Control",
        )
        return out_dir

    def test_finalize_workspace_generates_review_artifacts_and_traceability(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)

            dossier = finalize_function_dossier(workspace)
            payload = dossier.to_dict()

            self.assertEqual("Control_Update", payload["function"]["name"])
            self.assertEqual("blocked", payload["function"]["status"])
            self.assertEqual("unknown", payload["readiness"]["mvp_level"])
            self.assertFalse(payload["readiness"]["ready_for_review"])
            self.assertTrue(payload["readiness"]["blocked"])
            self.assertTrue(
                any(
                    "Artifact contract" in reason
                    for reason in payload["readiness"]["blocked_reasons"]
                )
            )
            self.assertTrue(payload["artifact_index"])
            self.assertTrue(payload["traceability"])
            self.assertTrue(payload["review_items"])
            self.assertTrue(payload["unresolved_items"])
            self.assertTrue(payload["next_actions"])
            self.assertIn("function_signature", {item["artifact_kind"] for item in payload["artifact_index"]})
            self.assertIn(
                "schema_error",
                {item["contract_status"] for item in payload["artifact_index"]},
            )

            reports = workspace / "reports"
            for name in [
                "function_dossier.json",
                "function_dossier.md",
                "dossier_manifest.json",
                "traceability_matrix.csv",
                "review_checklist.md",
                "unresolved_items.md",
                "next_actions.md",
            ]:
                self.assertTrue((reports / name).exists(), name)

            markdown = (reports / "function_dossier.md").read_text(encoding="utf-8")
            review_markdown = (reports / "review_checklist.md").read_text(encoding="utf-8")
            unresolved_markdown = (reports / "unresolved_items.md").read_text(encoding="utf-8")
            next_actions_markdown = (reports / "next_actions.md").read_text(encoding="utf-8")
            self.assertIn("# 関数dossier: Control_Update", markdown)
            self.assertIn("## トレーサビリティ", markdown)
            self.assertIn("## 未解決項目", markdown)
            self.assertIn("## 次のアクション", markdown)
            self.assertIn("# レビュー確認リスト", review_markdown)
            self.assertIn("# 未解決項目", unresolved_markdown)
            self.assertIn("# 次のアクション", next_actions_markdown)
            traceability_csv = (reports / "traceability_matrix.csv").read_text(encoding="utf-8")
            self.assertIn("source_kind,source_id,relation,target_kind,target_id", traceability_csv)

    def test_review_report_renderers_localize_user_facing_values(self):
        unresolved_markdown = render_unresolved_items_markdown(
            [
                DossierUnresolvedItem(
                    "UNRESOLVED_EXPECTED_001",
                    "test_case_design_generation",
                    "expected_result_unknown",
                    "Expected result requires review for TC_Control_Update_001.",
                    "The generated test cannot be treated as approved until expected values are reviewed.",
                    ["test_spec"],
                    ["TC_Control_Update_001"],
                    "Review function specification and replace TBD expected values.",
                ),
                DossierUnresolvedItem(
                    "UNRESOLVED_EXPECTED_002",
                    "test_case_design_generation",
                    "expected_result_unknown",
                    "Expected return value must be reviewed from specification.",
                    "Expected return value must be reviewed from specification.",
                    ["test_spec"],
                    ["TC_Control_Update_002"],
                    "Review generated test case and replace TBD expected values.",
                ),
            ]
        )
        next_actions_markdown = render_next_actions_markdown(
            [
                DossierNextAction(
                    "NEXT_001",
                    "high",
                    "review_expected_result",
                    "Review expected result",
                    "Review function specification and replace TBD expected values.",
                    "spec_reviewer",
                    ["UNRESOLVED_EXPECTED_001"],
                    "Updated generated workspace artifacts or recorded human review decision.",
                ),
                DossierNextAction(
                    "NEXT_002",
                    "high",
                    "review_expected_result",
                    "Review function specification and source behavior.",
                    "Review function specification and source behavior.",
                    "spec_reviewer",
                    ["UNRESOLVED_EXPECTED_002"],
                    "Review function specification and source behavior.",
                ),
            ]
        )

        self.assertIn("期待結果未確認", unresolved_markdown)
        self.assertIn("生成テストは、期待値レビュー", unresolved_markdown)
        self.assertIn("関数仕様を確認し、TBD の期待値を置き換えてください。", unresolved_markdown)
        self.assertIn("期待戻り値を仕様から確認してください。", unresolved_markdown)
        self.assertIn("生成テストケースを確認し、TBD の期待値を置き換えてください。", unresolved_markdown)
        self.assertIn("期待結果を確認", next_actions_markdown)
        self.assertIn("仕様レビュー担当", next_actions_markdown)
        self.assertIn("関数仕様とソース上の挙動を確認してください。", next_actions_markdown)
        self.assertNotIn("The generated test cannot", unresolved_markdown)
        self.assertNotIn("Review function specification", unresolved_markdown + next_actions_markdown)
        self.assertNotIn("Expected return value must", unresolved_markdown)
        self.assertNotIn("Review generated test case", unresolved_markdown)

    def test_finalize_blocks_contract_invalid_and_missing_mvp1_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "mvp1"
            reports = workspace / "reports"
            reports.mkdir(parents=True)
            (reports / "source_digest.json").write_text(json.dumps({"schema_version": "0.1", "source": {"path": "src/control.c"}, "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_location.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update"}, "location": {"start_line": 10, "end_line": 20}}), encoding="utf-8")
            (reports / "function_signature.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update", "signature": "int Control_Update(void)"}}), encoding="utf-8")

            dossier = finalize_function_dossier(workspace, function_name="Control_Update")

            self.assertEqual("unknown", dossier.readiness.mvp_level)
            self.assertFalse(dossier.readiness.ready_for_review)
            self.assertTrue(dossier.readiness.blocked)
            self.assertIn(
                "No eligible decisionable review subject is available.",
                dossier.readiness.blocked_reasons,
            )
            self.assertEqual("blocked", dossier.status)
            self.assertEqual(
                {"schema_error"},
                {
                    item.contract_status
                    for item in dossier.artifact_index
                    if item.artifact_kind
                    in {"source_digest", "function_location", "function_signature"}
                },
            )
            self.assertTrue(
                any(
                    "Artifact contract source_digest is schema_error" in reason
                    for reason in dossier.readiness.blocked_reasons
                )
            )
            self.assertTrue(any(warning.code == "missing_artifact" for warning in dossier.warnings))

            blocked_workspace = Path(temp_dir) / "blocked"
            (blocked_workspace / "reports").mkdir(parents=True)
            blocked = finalize_function_dossier(blocked_workspace, function_name="Control_Update")
            self.assertTrue(blocked.readiness.blocked)
            self.assertEqual("blocked", blocked.status)
            self.assertTrue(blocked.readiness.blocked_reasons)

    def test_finalize_rejects_invalid_payloads_and_prepare_review_regenerates_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "mismatch"
            reports = workspace / "reports"
            reports.mkdir(parents=True)
            (reports / "source_digest.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_location.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_signature.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "test_spec.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Other_Function"}, "test_cases": []}), encoding="utf-8")

            dossier = finalize_function_dossier(workspace, function_name="Control_Update")
            test_design = next(
                item
                for item in dossier.artifact_index
                if item.artifact_kind == "test_spec"
            )
            self.assertEqual("schema_error", test_design.contract_status)
            self.assertTrue(dossier.readiness.blocked)
            self.assertNotIn(
                "function_name_mismatch",
                {warning.code for warning in dossier.warnings},
            )

            paths = prepare_review_from_dossier(reports / "function_dossier.json", reports)
            self.assertTrue(paths["review_checklist"].exists())
            self.assertTrue(paths["unresolved_items"].exists())
            self.assertTrue(paths["next_actions"].exists())
            self.assertTrue(paths["traceability_matrix"].exists())

    def test_finalize_keeps_timestamp_staleness_orthogonal_to_schema_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "stale"
            reports = workspace / "reports"
            inputs = workspace / "input"
            reports.mkdir(parents=True)
            inputs.mkdir(parents=True)
            (inputs / "request.json").write_text(json.dumps({"source": "src/control.c", "function": "Control_Update"}), encoding="utf-8")
            (reports / "source_digest.json").write_text(json.dumps({"schema_version": "0.1", "source": {"path": "src/control.c"}, "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_location.json").write_text(json.dumps({"schema_version": "0.1", "source": {"path": "src/control.c"}, "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_signature.json").write_text(json.dumps({"schema_version": "0.1", "source": {"path": "src/other.c"}, "function": {"name": "Control_Update"}}), encoding="utf-8")
            old_time = time.time() - 3600
            os.utime(reports / "source_digest.json", (old_time, old_time))

            dossier = finalize_function_dossier(workspace, function_name="Control_Update")
            payload = dossier.to_dict()

            stale = {item["artifact_kind"]: item for item in payload["artifact_index"] if item["stale_candidate"]}
            self.assertIn("source_digest", stale)
            self.assertEqual("schema_error", stale["source_digest"]["contract_status"])
            self.assertNotIn("function_signature", stale)
            warning_codes = {warning["code"] for warning in payload["warnings"]}
            self.assertIn("artifact_older_than_request", warning_codes)
            self.assertNotIn("source_path_mismatch", warning_codes)
            self.assertIn("modified_at", stale["source_digest"])

    def test_cli_finalize_prepare_review_and_analyze_function_dossier_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)

            finalize = run_module("--json", "finalize-dossier", "--workspace", str(workspace))
            self.assertEqual(0, finalize.returncode, finalize.stderr)
            finalize_payload = json.loads(finalize.stdout)
            self.assertEqual("passed", finalize_payload["data"]["outcome"])
            self.assertTrue(Path(finalize_payload["data"]["details"]["reports"]["function_dossier_md"]).exists())

            prepare = run_module("--json", "prepare-review", "--dossier", str(workspace / "reports" / "function_dossier.json"))
            self.assertEqual(0, prepare.returncode, prepare.stderr)
            prepare_payload = json.loads(prepare.stdout)
            self.assertEqual("passed", prepare_payload["data"]["outcome"])

            out_dir = Path(temp_dir) / "AnalyzeFunctionDossierReview"
            full = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(VC6_FIXTURE_ROOT),
                "--dsw",
                str(VC6_FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--phase",
                "execution",
                "--out",
                str(out_dir),
                "--finalize-dossier",
            )
            self.assertEqual(0, full.returncode, full.stderr)
            full_payload = json.loads(full.stdout)
            self.assertEqual("passed", full_payload["data"]["outcome"])
            self.assertIn("review", full_payload["data"]["details"])
            self.assertTrue((out_dir / "reports" / "review_checklist.md").exists())

            final_dossier_path = out_dir / "reports" / "function_dossier.json"
            final_dossier = json.loads(final_dossier_path.read_text(encoding="utf-8"))
            loaded_dossier = load_artifact(
                final_dossier_path,
                expected_kind=ArtifactKind.FUNCTION_DOSSIER,
                mode=ContractMode.COMPATIBLE,
            )
            self.assertTrue(loaded_dossier.migrated)
            self.assertIn(
                ("missing_provenance", "$.subject.source_sha256", "blocking"),
                {
                    (item.code, item.json_path, item.severity)
                    for item in loaded_dossier.violations
                },
            )
            self.assertNotIn(
                "0" * 64,
                json.dumps(loaded_dossier.payload, sort_keys=True),
            )
            self.assertNotIn(
                "invalid_relative_path",
                {item.code for item in loaded_dossier.violations},
            )
            self.assertEqual("src/control.c", final_dossier["target"]["source"])
            self.assertEqual("Control_Update", final_dossier["target"]["function"])
            self.assertIn("defines", final_dossier["build_context"])
            self.assertIn("branch_coverage_items", final_dossier["test_design"])

            probe = run_module("--json", "build-probe", "--dossier", str(final_dossier_path), "--dry-run")
            self.assertEqual(0, probe.returncode, probe.stderr)
            self.assertIn("extracted", json.loads(probe.stdout)["data"]["details"]["command"])

            design = run_module("--json", "generate-test-design", "--dossier", str(final_dossier_path))
            self.assertEqual(0, design.returncode, design.stderr)
            self.assertEqual("passed", json.loads(design.stdout)["data"]["outcome"])


if __name__ == "__main__":
    unittest.main()
