# Test Execution Blocker Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `run-tests --run` が終了コード35・`blocked` になった直後に、実行を直接止めた項目を履歴JSON／Markdownと最新レポートへ出力し、VS Codeで安全に自動表示してWorkflowから再表示できるようにする。

**Architecture:** ブロッカー原因の判定、正規化、契約検証、履歴保存、最新ビュー同期はPython execution coreへ集約する。VS Code拡張はv1 CLI envelopeと成果物ハッシュを検証し、既に生成されたレポートを開いて状態を表示するだけにする。TestSpecの項目探索と未確定値判定は既存のtest-input formサブシステムから読取専用APIとして共有する。

**Tech Stack:** Python 3.12、`dataclasses`、JSON Schema Draft 2020-12、`unittest`、TypeScript 5.4、Node.js 20、VS Code Extension API 1.85、GitHub Actions Windows CI。

## Global Constraints

- 対象は実際の `run-tests --run` の canonical outcome が厳密に `blocked` の場合だけとする。
- 終了コード35と `RunOutcome.BLOCKED` の意味を変更しない。
- `failed`、`inconclusive`、`timed_out`、`cancelled`、`passed`、`planned` にはブロッカーレポートを生成しない。
- `run-tests --plan` は既存の最新ブロッカーレポートを生成・削除・更新しない。
- 履歴側 `runs/<run_id>/test_execution_blockers.json` と `runs/<run_id>/test_execution_blockers.md` は一度公開したら上書きしない。
- 最新側 `reports/test_execution_blockers.json` と `reports/test_execution_blockers.md` は、後続の実実行が非blockedなら削除する。
- レポート生成失敗は本来のテスト終了状態を上書きしない。
- VS Codeはブロッカー原因を再推論しない。Pythonが返した契約済み成果物だけを表示する。
- VS Codeは終了コード35だけでhandled outcomeにしない。v1 envelope、`command == run-tests`、`outcome == blocked`、`exit_code == 35` をすべて検証する。
- 自動表示と復元にはworkspace containment、run ID、artifact kind、schema version、SHA-256、実行レポート参照の一致を要求する。
- レポートは直接原因だけを列挙し、背景レビュー項目や単なるwarningを混ぜない。
- TestSpec内の未確定値は既存 `test_input_form.validation.is_unresolved` を使用する。
- 動的文字列はMarkdownでエスケープし、製品ソース全文やログ全文をコピーしない。
- `current_value` は最大2,048文字、診断メッセージは最大4,096文字、runnerログ抜粋は最大8,192文字とする。
- 実装中は各タスクで「失敗テスト → 最小実装 → 対象テスト成功 → 関連回帰成功 → コミット」の順序を守る。

---

## Task 1: ブロッカーレポート契約とRunPathsを追加する

**Files:**
- Modify: `src/unit_test_runner/contracts/kinds.py`
- Modify: `src/unit_test_runner/contracts/path_policy.py`
- Modify: `src/unit_test_runner/contracts/validator.py`
- Modify: `src/unit_test_runner/schemas/common.schema.json`
- Modify: `src/unit_test_runner/schemas/latest_run_pointer.schema.json`
- Create: `src/unit_test_runner/schemas/test_execution_blocker_report.schema.json`
- Modify: `src/unit_test_runner/execution/run_paths.py`
- Create: `tests/test_execution_blocker_contract.py`
- Modify: `tests/test_contract_registry.py`
- Modify: `tests/test_cli_artifact_references.py`

- [ ] **Step 1: 失敗する契約テストを追加する**

`tests/test_execution_blocker_contract.py` を作成し、少なくとも以下を実装する。

```python
from __future__ import annotations

import unittest

from unit_test_runner.contracts import ArtifactKind, validate_payload
from unit_test_runner.execution.test_result_writer import build_artifact_payload


SUBJECT = {
    "function_id": "fn_control_update_001",
    "source_path": "src/control.c",
    "source_sha256": "1" * 64,
}


def blocker_payload() -> dict:
    return build_artifact_payload(
        ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT,
        {
            "run_id": "run-20260720T000000000000Z-1234abcd",
            "execution_status": "blocked",
            "execution_report": {
                "artifact_kind": ArtifactKind.TEST_EXECUTION_REPORT.value,
                "path": "runs/run-20260720T000000000000Z-1234abcd/test_execution_report.json",
                "sha256": "2" * 64,
            },
            "blocker_count": 1,
            "primary_action": {
                "code": "open_test_input_editor",
                "label": "未確定項目を入力",
                "affected_count": 1,
            },
            "blockers": [
                {
                    "blocker_id": "BLK-001",
                    "code": "unresolved_expected_value",
                    "category": "test_input",
                    "severity": "error",
                    "case_id": "TC_001",
                    "item_id": "item-" + "3" * 64,
                    "control_name": "expected_expression",
                    "summary": "期待値が未確定です。",
                    "current_value": "TBD_EXPECTED_VALUE",
                    "source_artifact": "reports/test_spec.json",
                    "source_pointer": "/additional_case_candidates/0/expected_observations/0/expected_expression",
                    "recommended_action": {
                        "code": "open_test_input_editor",
                        "label": "未確定項目を入力",
                    },
                    "next_steps": [
                        "値を入力する",
                        "項目を確認済みにする",
                        "テストハーネスを再生成する",
                        "ビルドを実行する",
                        "テストを再実行する",
                    ],
                    "truncated": False,
                }
            ],
        },
        subject=SUBJECT,
        producer_commit="test-commit",
    )


class ExecutionBlockerContractTests(unittest.TestCase):
    def test_valid_blocker_report_passes_contract(self):
        self.assertEqual(
            (),
            validate_payload(
                ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT,
                blocker_payload(),
            ),
        )

    def test_blocked_report_requires_at_least_one_blocker(self):
        payload = blocker_payload()
        payload["data"]["blockers"] = []
        payload["data"]["blocker_count"] = 0

        violations = validate_payload(
            ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT,
            payload,
        )

        self.assertTrue(violations)
        self.assertTrue(
            any(item.json_path.startswith("$.data") for item in violations)
        )

    def test_latest_run_pointer_accepts_matching_optional_blocker_reference(self):
        payload = build_artifact_payload(
            ArtifactKind.LATEST_RUN_POINTER,
            {
                "run_id": "run-20260720T000000000000Z-1234abcd",
                "execution_report": {
                    "artifact_kind": ArtifactKind.TEST_EXECUTION_REPORT.value,
                    "path": "runs/run-20260720T000000000000Z-1234abcd/test_execution_report.json",
                    "sha256": "2" * 64,
                },
                "blocker_report": {
                    "artifact_kind": ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT.value,
                    "path": "runs/run-20260720T000000000000Z-1234abcd/test_execution_blockers.json",
                    "markdown_path": "runs/run-20260720T000000000000Z-1234abcd/test_execution_blockers.md",
                    "sha256": "4" * 64,
                },
                "updated_at": "2026-07-20T00:00:00+00:00",
            },
            subject=SUBJECT,
            producer_commit="test-commit",
        )

        self.assertEqual(
            (),
            validate_payload(ArtifactKind.LATEST_RUN_POINTER, payload),
        )

    def test_latest_run_pointer_rejects_mismatched_blocker_run_id(self):
        payload = build_artifact_payload(
            ArtifactKind.LATEST_RUN_POINTER,
            {
                "run_id": "run-20260720T000000000000Z-1234abcd",
                "execution_report": {
                    "artifact_kind": ArtifactKind.TEST_EXECUTION_REPORT.value,
                    "path": "runs/run-20260720T000000000000Z-1234abcd/test_execution_report.json",
                    "sha256": "2" * 64,
                },
                "blocker_report": {
                    "artifact_kind": ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT.value,
                    "path": "runs/run-other/test_execution_blockers.json",
                    "markdown_path": "runs/run-other/test_execution_blockers.md",
                    "sha256": "4" * 64,
                },
                "updated_at": "2026-07-20T00:00:00+00:00",
            },
            subject=SUBJECT,
            producer_commit="test-commit",
        )

        violations = validate_payload(ArtifactKind.LATEST_RUN_POINTER, payload)

        self.assertTrue(
            any(item.code == "invalid_reference" for item in violations)
        )


if __name__ == "__main__":
    unittest.main()
```

`tests/test_contract_registry.py` のstable enum確認へ次を追加する。

```python
self.assertEqual(
    "test_execution_blocker_report",
    ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT.value,
)
```

- [ ] **Step 2: 契約テストが失敗することを確認する**

Run:

```powershell
python -m unittest tests.test_execution_blocker_contract tests.test_contract_registry -v
```

Expected: `ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT` が存在しない、またはschemaがないため失敗する。

- [ ] **Step 3: ArtifactKindとRunPathsを拡張する**

`src/unit_test_runner/contracts/kinds.py` の `TEST_EXECUTION_REPORT` 直後へ追加する。

```python
TEST_EXECUTION_BLOCKER_REPORT = "test_execution_blocker_report"
```

`src/unit_test_runner/execution/run_paths.py` の `RunPaths` と返却値へ追加する。

```python
@dataclass(frozen=True)
class RunPaths:
    run_id: str
    root: Path
    execution_report: Path
    blocker_report_json: Path
    blocker_report_markdown: Path
    result_json: Path
    result_csv: Path
    stdout_log: Path
    stderr_log: Path
    combined_log: Path
```

```python
return RunPaths(
    run_id=run_id,
    root=root,
    execution_report=root / "test_execution_report.json",
    blocker_report_json=root / "test_execution_blockers.json",
    blocker_report_markdown=root / "test_execution_blockers.md",
    result_json=root / "test_result.json",
    result_csv=root / "test_result.csv",
    stdout_log=logs / "stdout.log",
    stderr_log=logs / "stderr.log",
    combined_log=logs / "test_execution.log",
)
```

`tests/test_cli_artifact_references.py` の直接 `RunPaths(...)` を構築するfixtureにも次を追加する。

```python
blocker_report_json=run_root / "test_execution_blockers.json",
blocker_report_markdown=run_root / "test_execution_blockers.md",
```

- [ ] **Step 4: 完全なblocker schemaを追加する**

`src/unit_test_runner/schemas/test_execution_blocker_report.schema.json` を次の内容で作成する。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://unit-test-runner.local/schemas/test_execution_blocker_report.schema.json",
  "title": "Test Execution Blocker Report",
  "allOf": [
    {
      "$ref": "common.schema.json"
    },
    {
      "type": "object",
      "properties": {
        "artifact_kind": {
          "const": "test_execution_blocker_report"
        },
        "schema_version": {
          "const": "1.0.0"
        }
      }
    },
    {
      "properties": {
        "data": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "run_id",
            "execution_status",
            "execution_report",
            "blocker_count",
            "primary_action",
            "blockers"
          ],
          "properties": {
            "run_id": {
              "$ref": "common.schema.json#/$defs/identifier"
            },
            "execution_status": {
              "const": "blocked"
            },
            "execution_report": {
              "$ref": "common.schema.json#/$defs/artifact_reference"
            },
            "blocker_count": {
              "type": "integer",
              "minimum": 1,
              "maximum": 10000
            },
            "primary_action": {
              "$ref": "#/$defs/primaryAction"
            },
            "blockers": {
              "type": "array",
              "minItems": 1,
              "maxItems": 10000,
              "items": {
                "$ref": "#/$defs/blocker"
              }
            }
          }
        }
      }
    }
  ],
  "$defs": {
    "actionCode": {
      "enum": [
        "open_test_input_editor",
        "open_build_probe_report",
        "generate_harness",
        "run_build_probe",
        "choose_or_build_executable",
        "open_execution_log",
        "open_execution_report"
      ]
    },
    "action": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "code",
        "label"
      ],
      "properties": {
        "code": {
          "$ref": "#/$defs/actionCode"
        },
        "label": {
          "type": "string",
          "minLength": 1,
          "maxLength": 256
        }
      }
    },
    "primaryAction": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "code",
        "label",
        "affected_count"
      ],
      "properties": {
        "code": {
          "$ref": "#/$defs/actionCode"
        },
        "label": {
          "type": "string",
          "minLength": 1,
          "maxLength": 256
        },
        "affected_count": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10000
        }
      }
    },
    "blocker": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "blocker_id",
        "code",
        "category",
        "severity",
        "summary",
        "recommended_action",
        "next_steps",
        "truncated"
      ],
      "properties": {
        "blocker_id": {
          "type": "string",
          "pattern": "^BLK-[0-9]{3,6}$"
        },
        "code": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "category": {
          "enum": [
            "build",
            "executable",
            "harness",
            "test_case",
            "test_input",
            "runner",
            "unknown"
          ]
        },
        "severity": {
          "enum": [
            "warning",
            "error",
            "blocking"
          ]
        },
        "case_id": {
          "$ref": "common.schema.json#/$defs/identifier"
        },
        "item_id": {
          "type": "string",
          "pattern": "^item-[0-9a-f]{64}$"
        },
        "control_name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "summary": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4096
        },
        "current_value": {
          "type": "string",
          "maxLength": 2048
        },
        "source_artifact": {
          "$ref": "common.schema.json#/$defs/relativePath"
        },
        "source_pointer": {
          "type": "string",
          "minLength": 1,
          "maxLength": 2048
        },
        "related_file": {
          "$ref": "common.schema.json#/$defs/relativePath"
        },
        "line_number": {
          "type": "integer",
          "minimum": 0
        },
        "log_excerpt": {
          "type": "string",
          "maxLength": 8192
        },
        "recommended_action": {
          "$ref": "#/$defs/action"
        },
        "next_steps": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1024
          }
        },
        "truncated": {
          "type": "boolean"
        }
      }
    }
  }
}
```

- [ ] **Step 5: latest-run pointer契約を拡張する**

`src/unit_test_runner/schemas/common.schema.json` の `$defs` に追加する。

```json
"testExecutionBlockerReference": {
  "type": "object",
  "additionalProperties": false,
  "required": [
    "artifact_kind",
    "path",
    "markdown_path",
    "sha256"
  ],
  "properties": {
    "artifact_kind": {
      "const": "test_execution_blocker_report"
    },
    "path": {
      "$ref": "#/$defs/relativePath"
    },
    "markdown_path": {
      "$ref": "#/$defs/relativePath"
    },
    "sha256": {
      "$ref": "#/$defs/sha256"
    }
  }
}
```

同ファイルの `$defs.latestRunPointerData.properties` に追加する。

```json
"blocker_report": {
  "$ref": "#/$defs/testExecutionBlockerReference"
}
```

`src/unit_test_runner/schemas/latest_run_pointer.schema.json` の最後のoverlayで、既存 `data.properties.execution_report` と同じ階層へ次を追加する。

```json
{
  "properties": {
    "data": {
      "properties": {
        "execution_report": {
          "properties": {
            "path": {
              "pattern": "^runs/[^/]+/test_execution_report\\.json$"
            }
          }
        },
        "blocker_report": {
          "properties": {
            "path": {
              "pattern": "^runs/[^/]+/test_execution_blockers\\.json$"
            },
            "markdown_path": {
              "pattern": "^runs/[^/]+/test_execution_blockers\\.md$"
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 6: semantic validationとpath policyを追加する**

`src/unit_test_runner/contracts/path_policy.py` へ追加する。

```python
_BLOCKER_POLICY = ContractPathPolicy(
    scalar_fields=_DEFAULT_SCALAR_FIELDS
    | frozenset({"markdown_path", "source_artifact"}),
    list_fields=_DEFAULT_LIST_FIELDS,
    nullable_scalar_fields=_DEFAULT_NULLABLE_SCALAR_FIELDS,
)
```

```python
def path_policy_for(kind: ArtifactKind) -> ContractPathPolicy:
    if kind in _BUILD_ARTIFACT_KINDS:
        return _BUILD_POLICY
    if kind is ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT:
        return _BLOCKER_POLICY
    return _DEFAULT_POLICY
```

`markdown_path` はlatest-run pointerでも検証対象にするため `_DEFAULT_SCALAR_FIELDS` にも追加する。`source_artifact` はblocker専用policyだけに置く。

`src/unit_test_runner/contracts/validator.py` へ次の関数を追加する。

```python
def _test_execution_blocker_report_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    violations: list[ContractViolation] = []
    blockers = data.get("blockers")
    blocker_count = data.get("blocker_count")
    if isinstance(blockers, list) and blocker_count != len(blockers):
        violations.append(
            ContractViolation(
                "inconsistent_summary",
                "$.data.blocker_count",
                "blocker_count must equal the number of blockers.",
            )
        )
    run_id = str(data.get("run_id") or "")
    execution_report = data.get("execution_report")
    if isinstance(execution_report, Mapping):
        actual_kind = execution_report.get("artifact_kind")
        if actual_kind != ArtifactKind.TEST_EXECUTION_REPORT.value:
            violations.append(
                ContractViolation(
                    "invalid_reference",
                    "$.data.execution_report.artifact_kind",
                    "execution_report must reference test_execution_report.",
                )
            )
        expected_path = f"runs/{run_id}/test_execution_report.json"
        if execution_report.get("path") != expected_path:
            violations.append(
                ContractViolation(
                    "invalid_reference",
                    "$.data.execution_report.path",
                    "execution_report path must belong to report run_id.",
                )
            )
    if isinstance(blockers, list):
        blocker_ids = [
            item.get("blocker_id")
            for item in blockers
            if isinstance(item, Mapping)
        ]
        if len(blocker_ids) != len(set(blocker_ids)):
            violations.append(
                ContractViolation(
                    "duplicate_id",
                    "$.data.blockers",
                    "blocker_id values must be unique within the report.",
                )
            )
    primary = data.get("primary_action")
    if isinstance(primary, Mapping) and isinstance(blockers, list):
        code = primary.get("code")
        affected = sum(
            1
            for blocker in blockers
            if isinstance(blocker, Mapping)
            and isinstance(blocker.get("recommended_action"), Mapping)
            and blocker["recommended_action"].get("code") == code
        )
        if primary.get("affected_count") != affected:
            violations.append(
                ContractViolation(
                    "inconsistent_summary",
                    "$.data.primary_action.affected_count",
                    "affected_count must equal blockers using the primary action.",
                )
            )
        first = blockers[0] if blockers else None
        first_action = (
            first.get("recommended_action")
            if isinstance(first, Mapping)
            else None
        )
        if isinstance(first_action, Mapping) and first_action.get("code") != code:
            violations.append(
                ContractViolation(
                    "inconsistent_summary",
                    "$.data.primary_action.code",
                    "primary_action must match the first ordered blocker.",
                )
            )
    return violations
```

`_latest_run_pointer_semantic_violations` を次の条件で拡張する。

```python
blocker = data.get("blocker_report") if isinstance(data, Mapping) else None
if isinstance(blocker, Mapping):
    actual_kind = blocker.get("artifact_kind")
    if actual_kind != ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT.value:
        violations.append(
            ContractViolation(
                "invalid_reference",
                "$.data.blocker_report.artifact_kind",
                "blocker_report must reference test_execution_blocker_report.",
            )
        )
    run_id = str(data.get("run_id") or "")
    expected_json = f"runs/{run_id}/test_execution_blockers.json"
    expected_markdown = f"runs/{run_id}/test_execution_blockers.md"
    if blocker.get("path") != expected_json:
        violations.append(
            ContractViolation(
                "invalid_reference",
                "$.data.blocker_report.path",
                "blocker_report path must belong to the latest run_id.",
            )
        )
    if blocker.get("markdown_path") != expected_markdown:
        violations.append(
            ContractViolation(
                "invalid_reference",
                "$.data.blocker_report.markdown_path",
                "blocker_report markdown_path must belong to the latest run_id.",
            )
        )
```

semantic mapへ追加する。

```python
ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT.value: (
    _test_execution_blocker_report_semantic_violations
),
```

- [ ] **Step 7: 契約テストを通す**

Run:

```powershell
python -m unittest tests.test_execution_blocker_contract tests.test_contract_registry -v
```

Expected: 全件成功。

- [ ] **Step 8: 関連契約回帰を実行する**

Run:

```powershell
python -m unittest tests.test_contract_validation tests.test_cli_result_contract tests.test_contract_migrations tests.test_cli_artifact_references -v
```

Expected: 全件成功。

- [ ] **Step 9: コミットする**

```powershell
git add src/unit_test_runner/contracts src/unit_test_runner/schemas src/unit_test_runner/execution/run_paths.py tests/test_execution_blocker_contract.py tests/test_contract_registry.py tests/test_cli_artifact_references.py
git commit -m "feat: register test execution blocker artifact"
```

---

## Task 2: TestSpec項目の読取専用location APIを追加する

**Files:**
- Create: `src/unit_test_runner/test_input_form/read_model.py`
- Modify: `src/unit_test_runner/test_input_form/__init__.py`
- Create: `tests/test_test_input_form_read_model.py`

- [ ] **Step 1: JSON Pointerと項目属性を固定する失敗テストを書く**

`tests/test_test_input_form_read_model.py` を作成する。

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.spec_support import write_test_input_form_fixture
from unit_test_runner.test_input_form import (
    load_current_form_snapshot,
    locate_editable_test_spec_fields,
)


class TestInputFormReadModelTests(unittest.TestCase):
    def test_read_model_exposes_stable_ids_pointers_and_execution_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            current = load_current_form_snapshot(fixture.workspace)

            fields = locate_editable_test_spec_fields(current.snapshot.spec)

        expected = next(
            field
            for field in fields
            if field.case_id == fixture.unresolved_case_id
            and field.kind == "expected_observation"
        )
        self.assertRegex(expected.item_id, r"^item-[0-9a-f]{64}$")
        self.assertEqual("additional_case_candidates", expected.case_location)
        self.assertTrue(expected.execution_blocking)
        self.assertFalse(expected.confirmed)
        self.assertEqual(
            "/additional_case_candidates/0/expected_observations/0",
            expected.parent_pointer,
        )
        control = next(
            item
            for item in expected.controls
            if item.name == "expected_expression"
        )
        self.assertTrue(control.required_for_confirmation)
        self.assertEqual(
            "/additional_case_candidates/0/expected_observations/0/expected_expression",
            control.json_pointer,
        )

    def test_read_model_builds_index_based_json_pointers(self):
        spec = {
            "test_cases": [
                {
                    "test_case_id": "TC_1",
                    "input_assignments": [
                        {
                            "target_kind": "parameter",
                            "target_name": "mode/with~token",
                            "source_candidate_id": "CAND_1",
                            "value_expression": "0",
                            "review_required": True,
                        }
                    ],
                }
            ],
            "additional_case_candidates": [],
        }

        fields = locate_editable_test_spec_fields(spec)

        self.assertEqual(
            "/test_cases/0/input_assignments/0/value_expression",
            fields[0].controls[0].json_pointer,
        )

    def test_read_model_does_not_mutate_the_spec(self):
        spec = {
            "test_cases": [],
            "additional_case_candidates": [],
        }
        before = repr(spec)

        self.assertEqual((), locate_editable_test_spec_fields(spec))
        self.assertEqual(before, repr(spec))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストがimport errorで失敗することを確認する**

Run:

```powershell
python -m unittest tests.test_test_input_form_read_model -v
```

Expected: `locate_editable_test_spec_fields` が未実装のため失敗。

- [ ] **Step 3: 読取専用モデルを実装する**

`src/unit_test_runner/test_input_form/read_model.py` を次のインターフェースで作成する。

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .field_catalog import (
    execution_value_required,
    label_for_parent,
    required_for_confirmation,
)
from .field_locator import locate_form_items


@dataclass(frozen=True)
class LocatedEditableControl:
    name: str
    value: Any
    required_for_confirmation: bool
    json_pointer: str


@dataclass(frozen=True)
class LocatedEditableField:
    case_id: str
    case_location: str
    case_index: int
    collection: str
    item_index: int
    item_id: str
    subject_fingerprint: str
    kind: str
    label: str
    parent_pointer: str
    confirmed: bool
    execution_blocking: bool
    editable: bool
    controls: tuple[LocatedEditableControl, ...]


def locate_editable_test_spec_fields(
    spec: Any,
) -> tuple[LocatedEditableField, ...]:
    result: list[LocatedEditableField] = []
    for item in locate_form_items(spec):
        parent_pointer = _pointer(
            item.case_location,
            item.case_index,
            item.collection,
            item.item_index,
        )
        controls = tuple(
            LocatedEditableControl(
                name=control.name,
                value=item.parent.get(control.name),
                required_for_confirmation=required_for_confirmation(
                    item.rule,
                    control,
                    item.parent,
                ),
                json_pointer=_pointer(
                    item.case_location,
                    item.case_index,
                    item.collection,
                    item.item_index,
                    control.name,
                ),
            )
            for control in item.rule.controls
        )
        review_required = item.parent.get("review_required")
        result.append(
            LocatedEditableField(
                case_id=item.case_id,
                case_location=item.case_location,
                case_index=item.case_index,
                collection=item.collection,
                item_index=item.item_index,
                item_id=item.item_id,
                subject_fingerprint=item.subject_fingerprint,
                kind=item.kind,
                label=label_for_parent(item.rule, item.parent),
                parent_pointer=parent_pointer,
                confirmed=review_required is False,
                execution_blocking=execution_value_required(
                    item.rule,
                    item.parent,
                ),
                editable=item.editable and type(review_required) is bool,
                controls=controls,
            )
        )
    return tuple(result)


def _pointer(*parts: str | int) -> str:
    return "/" + "/".join(_escape_pointer_token(str(part)) for part in parts)


def _escape_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
```

`src/unit_test_runner/test_input_form/__init__.py` から公開する。

```python
from .read_model import (
    LocatedEditableControl,
    LocatedEditableField,
    locate_editable_test_spec_fields,
)
```

`__all__` が存在する場合は3シンボルを追加する。

- [ ] **Step 4: 新規テストと既存フォームテストを通す**

Run:

```powershell
python -m unittest tests.test_test_input_form_read_model tests.test_test_input_form_field_locator tests.test_test_input_form_service -v
```

Expected: 全件成功。

- [ ] **Step 5: コミットする**

```powershell
git add src/unit_test_runner/test_input_form tests/test_test_input_form_read_model.py
git commit -m "refactor: expose test input field read model"
```

---

## Task 3: ブロッカーモデル、切り詰め、重複排除、安定順序を実装する

**Files:**
- Create: `src/unit_test_runner/execution/blocker_models.py`
- Modify: `src/unit_test_runner/execution/__init__.py`
- Create: `tests/test_execution_blocker_models.py`

- [ ] **Step 1: 正規化規則の失敗テストを書く**

`tests/test_execution_blocker_models.py` に次を実装する。

```python
from __future__ import annotations

import unittest

from unit_test_runner.execution.blocker_models import (
    BlockerCandidate,
    RecommendedAction,
    build_blocker_report,
)


class ExecutionBlockerModelTests(unittest.TestCase):
    def test_deduplicates_sorts_assigns_ids_and_aggregates_primary_action(self):
        input_action = RecommendedAction(
            "open_test_input_editor",
            "未確定項目を入力",
        )
        build_action = RecommendedAction(
            "open_build_probe_report",
            "ビルド結果を開く",
        )
        candidates = [
            BlockerCandidate(
                priority=50,
                code="unresolved_expected_value",
                category="test_input",
                severity="error",
                summary="期待値が未確定です。",
                recommended_action=input_action,
                case_id="TC_B",
                item_id="item-" + "b" * 64,
                control_name="expected_expression",
                source_artifact="reports/test_spec.json",
                source_pointer="/additional_case_candidates/1/expected_observations/0/expected_expression",
                next_steps=("値を入力する",),
            ),
            BlockerCandidate(
                priority=10,
                code="build_error",
                category="build",
                severity="error",
                summary="リンクに失敗しました。",
                recommended_action=build_action,
                source_artifact="reports/build_probe_report.json",
                source_pointer="/diagnostics/0",
                next_steps=("ビルド診断を解消する",),
            ),
            BlockerCandidate(
                priority=50,
                code="unresolved_expected_value",
                category="test_input",
                severity="error",
                summary="期待値が未確定です。",
                recommended_action=input_action,
                case_id="TC_B",
                item_id="item-" + "b" * 64,
                control_name="expected_expression",
                source_artifact="reports/test_spec.json",
                source_pointer="/additional_case_candidates/1/expected_observations/0/expected_expression",
                next_steps=("値を入力する",),
            ),
        ]

        report = build_blocker_report(
            run_id="run-1",
            execution_report_path="runs/run-1/test_execution_report.json",
            execution_report_sha256="1" * 64,
            candidates=candidates,
        )

        self.assertEqual(2, report.blocker_count)
        self.assertEqual(["BLK-001", "BLK-002"], [item.blocker_id for item in report.blockers])
        self.assertEqual("build_error", report.blockers[0].code)
        self.assertEqual("open_build_probe_report", report.primary_action.code)
        self.assertEqual(1, report.primary_action.affected_count)

    def test_empty_candidate_set_gets_unknown_fallback(self):
        report = build_blocker_report(
            run_id="run-1",
            execution_report_path="runs/run-1/test_execution_report.json",
            execution_report_sha256="1" * 64,
            candidates=(),
        )

        self.assertEqual(1, report.blocker_count)
        self.assertEqual("execution_blocked_unknown", report.blockers[0].code)
        self.assertEqual("open_execution_report", report.primary_action.code)

    def test_bounds_dynamic_values_and_marks_truncation(self):
        candidate = BlockerCandidate(
            priority=50,
            code="unresolved_test_input",
            category="test_input",
            severity="error",
            summary="x" * 5000,
            current_value="y" * 3000,
            log_excerpt="z" * 9000,
            recommended_action=RecommendedAction(
                "open_test_input_editor",
                "未確定項目を入力",
            ),
            next_steps=("値を入力する",),
        )

        report = build_blocker_report(
            run_id="run-1",
            execution_report_path="runs/run-1/test_execution_report.json",
            execution_report_sha256="1" * 64,
            candidates=(candidate,),
        )
        blocker = report.blockers[0]

        self.assertEqual(4096, len(blocker.summary))
        self.assertEqual(2048, len(blocker.current_value or ""))
        self.assertEqual(8192, len(blocker.log_excerpt or ""))
        self.assertTrue(blocker.truncated)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが未実装で失敗することを確認する**

Run:

```powershell
python -m unittest tests.test_execution_blocker_models -v
```

Expected: import error。

- [ ] **Step 3: モデルと正規化処理を実装する**

`src/unit_test_runner/execution/blocker_models.py` の公開APIを次で固定する。

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable


MAX_CURRENT_VALUE = 2048
MAX_SUMMARY = 4096
MAX_LOG_EXCERPT = 8192

ACTION_LABELS = {
    "open_test_input_editor": "未確定項目を入力",
    "open_build_probe_report": "ビルド結果を開く",
    "generate_harness": "テストハーネスを生成",
    "run_build_probe": "ビルドを実行",
    "choose_or_build_executable": "実行ファイルを準備",
    "open_execution_log": "テスト実行ログを開く",
    "open_execution_report": "テスト実行レポートを開く",
}


@dataclass(frozen=True)
class RecommendedAction:
    code: str
    label: str
    affected_count: int = 1

    def to_dict(self, *, include_count: bool = False) -> dict[str, object]:
        value: dict[str, object] = {
            "code": self.code,
            "label": self.label,
        }
        if include_count:
            value["affected_count"] = self.affected_count
        return value


@dataclass(frozen=True)
class BlockerCandidate:
    priority: int
    code: str
    category: str
    severity: str
    summary: str
    recommended_action: RecommendedAction
    next_steps: tuple[str, ...]
    case_id: str | None = None
    item_id: str | None = None
    control_name: str | None = None
    current_value: str | None = None
    source_artifact: str | None = None
    source_pointer: str | None = None
    related_file: str | None = None
    line_number: int | None = None
    log_excerpt: str | None = None
    truncated: bool = False


@dataclass(frozen=True)
class ExecutionBlocker:
    blocker_id: str
    code: str
    category: str
    severity: str
    summary: str
    recommended_action: RecommendedAction
    next_steps: tuple[str, ...]
    case_id: str | None = None
    item_id: str | None = None
    control_name: str | None = None
    current_value: str | None = None
    source_artifact: str | None = None
    source_pointer: str | None = None
    related_file: str | None = None
    line_number: int | None = None
    log_excerpt: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "blocker_id": self.blocker_id,
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "summary": self.summary,
            "recommended_action": self.recommended_action.to_dict(),
            "next_steps": list(self.next_steps),
            "truncated": self.truncated,
        }
        for key, item in (
            ("case_id", self.case_id),
            ("item_id", self.item_id),
            ("control_name", self.control_name),
            ("current_value", self.current_value),
            ("source_artifact", self.source_artifact),
            ("source_pointer", self.source_pointer),
            ("related_file", self.related_file),
            ("line_number", self.line_number),
            ("log_excerpt", self.log_excerpt),
        ):
            if item is not None:
                value[key] = item
        return value


@dataclass(frozen=True)
class TestExecutionBlockerReport:
    run_id: str
    execution_report_path: str
    execution_report_sha256: str
    blockers: tuple[ExecutionBlocker, ...]
    primary_action: RecommendedAction

    @property
    def blocker_count(self) -> int:
        return len(self.blockers)

    def to_data(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "execution_status": "blocked",
            "execution_report": {
                "artifact_kind": "test_execution_report",
                "path": self.execution_report_path,
                "sha256": self.execution_report_sha256,
            },
            "blocker_count": self.blocker_count,
            "primary_action": self.primary_action.to_dict(include_count=True),
            "blockers": [item.to_dict() for item in self.blockers],
        }


def build_blocker_report(
    *,
    run_id: str,
    execution_report_path: str,
    execution_report_sha256: str,
    candidates: Iterable[BlockerCandidate],
) -> TestExecutionBlockerReport:
    normalized = [_bounded(item) for item in candidates]
    unique: dict[tuple[str, ...], BlockerCandidate] = {}
    for item in normalized:
        unique.setdefault(_deduplication_key(item), item)
    ordered = sorted(unique.values(), key=_sort_key)
    if not ordered:
        ordered = [_unknown_candidate()]
    blockers = tuple(
        ExecutionBlocker(
            blocker_id=f"BLK-{index:03d}",
            code=item.code,
            category=item.category,
            severity=item.severity,
            summary=item.summary,
            recommended_action=item.recommended_action,
            next_steps=item.next_steps,
            case_id=item.case_id,
            item_id=item.item_id,
            control_name=item.control_name,
            current_value=item.current_value,
            source_artifact=item.source_artifact,
            source_pointer=item.source_pointer,
            related_file=item.related_file,
            line_number=item.line_number,
            log_excerpt=item.log_excerpt,
            truncated=item.truncated,
        )
        for index, item in enumerate(ordered, start=1)
    )
    primary_code = blockers[0].recommended_action.code
    primary_label = blockers[0].recommended_action.label
    affected = sum(
        1
        for item in blockers
        if item.recommended_action.code == primary_code
    )
    return TestExecutionBlockerReport(
        run_id=run_id,
        execution_report_path=execution_report_path,
        execution_report_sha256=execution_report_sha256,
        blockers=blockers,
        primary_action=RecommendedAction(
            primary_code,
            primary_label,
            affected,
        ),
    )
```

同ファイルへ `_bounded`、`_deduplication_key`、`_sort_key`、`_unknown_candidate` を実装し、次の規則を固定する。

```python
def _deduplication_key(item: BlockerCandidate) -> tuple[str, ...]:
    return (
        item.code,
        item.case_id or "",
        item.item_id or "",
        item.control_name or "",
        item.source_artifact or "",
        item.source_pointer or "",
    )


def _sort_key(item: BlockerCandidate) -> tuple[object, ...]:
    return (
        item.priority,
        item.case_id or "",
        item.item_id or "",
        item.control_name or "",
        item.source_pointer or "",
        item.code,
    )
```

`_bounded` は各上限で文字列をsliceし、どれかが切り詰められた場合だけ `truncated=True` にする。`_unknown_candidate` は `open_execution_report` を推奨し、`source_artifact="runs/<run_id>..."` はここで捏造せず未設定にする。

`src/unit_test_runner/execution/__init__.py` から公開する。

- [ ] **Step 4: モデルテストを通す**

Run:

```powershell
python -m unittest tests.test_execution_blocker_models -v
```

Expected: 全件成功。

- [ ] **Step 5: コミットする**

```powershell
git add src/unit_test_runner/execution/blocker_models.py src/unit_test_runner/execution/__init__.py tests/test_execution_blocker_models.py
git commit -m "feat: model normalized execution blockers"
```

---

## Task 4: build、実行ファイル、harnessの直接ブロッカーを抽出する

**Files:**
- Create: `src/unit_test_runner/execution/blocker_analyzer.py`
- Create: `tests/test_execution_blocker_preconditions.py`

- [ ] **Step 1: build診断と実行ファイル不足の失敗テストを書く**

`tests/test_execution_blocker_preconditions.py` で、`TestExecutionReport` を直接組み立てて以下を検証する。

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.execution.blocker_analyzer import analyze_test_execution_blockers
from unit_test_runner.execution.execution_models import (
    ExecutableInfo,
    TestExecutionPolicy,
    TestExecutionReport,
    TestExecutionWarning,
    TestResultSummary,
)
from unit_test_runner.execution.run_paths import create_run_paths


def execution_report(*, executable_exists: bool) -> TestExecutionReport:
    return TestExecutionReport(
        source_path=Path("src/control.c"),
        function_name="Control_Update",
        status="blocked",
        executed=False,
        executable=ExecutableInfo(
            path=Path("bin/utr_probe.exe"),
            exists=executable_exists,
            sha256=None,
            generated_from="build-probe",
            build_probe_status="failed" if not executable_exists else "succeeded",
            warnings=[
                TestExecutionWarning(
                    "executable_not_found",
                    "テスト実行ファイルが見つかりません。",
                )
            ],
        ),
        command=None,
        command_result=None,
        parsed_result=TestResultSummary(),
        case_results=[],
        unresolved_review_items=[],
        evidence_files=[],
        warnings=[],
        policy=TestExecutionPolicy(run_tests=True, dry_run=False),
        schema_version="1.0.0",
    )


class ExecutionBlockerPreconditionTests(unittest.TestCase):
    def test_build_errors_are_concrete_and_suppress_broad_build_message(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, "run-build")
            reports = workspace / "reports"
            reports.mkdir()
            (workspace / "src").mkdir()
            (workspace / "src" / "control.c").write_text(
                "int Control_Update(void) { return 0; }\n",
                encoding="utf-8",
            )
            (reports / "build_probe_report.json").write_text(
                json.dumps(
                    {
                        "function": {"name": "Control_Update", "status": "failed"},
                        "diagnostics": [
                            {
                                "code": "unresolved_symbol",
                                "severity": "error",
                                "message": "_ReadSensor が未解決です。",
                                "file": "generated/tests/test_Control_Update.c",
                                "line_number": 12,
                                "raw": "LNK2019 _ReadSensor",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (reports / "harness_skeleton_report.json").write_text(
                json.dumps({"function": {"status": "generated"}, "unresolved_placeholders": []}),
                encoding="utf-8",
            )
            (reports / "build_workspace_report.json").write_text(
                json.dumps({"function": {"name": "Control_Update"}}),
                encoding="utf-8",
            )

            result = analyze_test_execution_blockers(
                workspace,
                paths,
                execution_report(executable_exists=False),
                "1" * 64,
            )

        self.assertEqual(1, result.blocker_count)
        blocker = result.blockers[0]
        self.assertEqual("unresolved_symbol", blocker.code)
        self.assertEqual("build", blocker.category)
        self.assertEqual("reports/build_probe_report.json", blocker.source_artifact)
        self.assertEqual("/diagnostics/0", blocker.source_pointer)
        self.assertEqual("open_build_probe_report", result.primary_action.code)

    def test_missing_executable_is_reported_after_successful_build_probe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, "run-exe")
            reports = workspace / "reports"
            reports.mkdir()
            (workspace / "src").mkdir()
            (workspace / "src" / "control.c").write_text(
                "int Control_Update(void) { return 0; }\n",
                encoding="utf-8",
            )
            (reports / "build_probe_report.json").write_text(
                json.dumps(
                    {
                        "function": {"name": "Control_Update", "status": "succeeded"},
                        "diagnostics": [],
                    }
                ),
                encoding="utf-8",
            )
            (reports / "harness_skeleton_report.json").write_text(
                json.dumps({"function": {"status": "generated"}, "unresolved_placeholders": []}),
                encoding="utf-8",
            )
            (reports / "build_workspace_report.json").write_text(
                json.dumps({"function": {"name": "Control_Update"}}),
                encoding="utf-8",
            )

            result = analyze_test_execution_blockers(
                workspace,
                paths,
                execution_report(executable_exists=False),
                "1" * 64,
            )

        self.assertEqual("executable_not_found", result.blockers[0].code)
        self.assertEqual("choose_or_build_executable", result.primary_action.code)
```

- [ ] **Step 2: テストが未実装で失敗することを確認する**

Run:

```powershell
python -m unittest tests.test_execution_blocker_preconditions -v
```

Expected: import error。

- [ ] **Step 3: analyzerの入口と前提条件優先順位を実装する**

`src/unit_test_runner/execution/blocker_analyzer.py` に次の公開関数を作る。

```python
def analyze_test_execution_blockers(
    workspace: Path | str,
    run_paths: RunPaths,
    execution_report: TestExecutionReport,
    execution_report_sha256: str,
) -> TestExecutionBlockerReport:
```

入口では、まずbuild probeと実行ファイルに必要なreportだけをlazy loadする。後段の判定へ進んだ場合に限りTestSpecとharnessを読む。contract envelopeなら `data` をunwrapする。

```text
常時: reports/build_probe_report.json
必要時: reports/build_workspace_report.json
必要時: reports/harness_skeleton_report.json
必要時: reports/test_spec.json
```

最初の実装では次の優先順位で早期returnする。

```python
build_status = str(build_probe.get("function", {}).get("status") or "unknown")
if build_status != "succeeded":
    candidates = _build_probe_candidates(build_probe)
elif execution_report.executable is not None and not execution_report.executable.exists:
    candidates = [_missing_executable_candidate(execution_report)]
else:
    candidates = []
```

`_build_probe_candidates` は `severity == "error"` のdiagnosticを1件ずつ候補化する。具体的diagnosticが0件なら `build_probe_not_successful` を1件生成する。`file` はworkspace内に解決できる場合だけ `related_file` として保存する。

`_missing_executable_candidate` は次を保持する。

```python
BlockerCandidate(
    priority=20,
    code="executable_not_found",
    category="executable",
    severity="error",
    summary="テスト実行ファイルが見つかりません。",
    current_value=_workspace_relative_if_safe(
        workspace,
        execution_report.executable.path,
    ),
    source_artifact="reports/build_probe_report.json",
    recommended_action=RecommendedAction(
        "choose_or_build_executable",
        "実行ファイルを準備",
    ),
    next_steps=(
        "ビルド結果を確認する",
        "ビルドを成功させるか実行ファイルを指定する",
        "テストを再実行する",
    ),
)
```

`_read_payload`、`_workspace_relative_if_safe` はworkspace escape、絶対外部パス、symlink/junctionをopenable pathとして返さない。

- [ ] **Step 4: harness blockerのテストと実装を追加する**

同テストfileへ、build成功・executable存在・`test_cases` はあるがharness statusが `partial` で、生成テストfileが存在しないケースを追加する。期待値:

```python
self.assertEqual("harness_missing_or_stale", result.blockers[0].code)
self.assertEqual("generate_harness", result.primary_action.code)
```

analyzerでは次の場合だけharness blockerを直接原因として扱う。

```text
- build probeはsucceeded
- executableは存在
- execution reportはblockedかつ未実行
- canonical TestSpecには実行対象ケースがある
- harnessのtest_skeletonsが空、またはrequired generated test fileが欠落
```

背景warningだけでharness blockerを作らない。

- [ ] **Step 5: 前提条件テストを通す**

Run:

```powershell
python -m unittest tests.test_execution_blocker_preconditions -v
```

Expected: 全件成功。

- [ ] **Step 6: 既存build/execution回帰を通す**

Run:

```powershell
python -m unittest tests.test_build_workspace_generation tests.test_execution_evidence tests.test_cli_execution_outcome -v
```

Expected: 全件成功。

- [ ] **Step 7: コミットする**

```powershell
git add src/unit_test_runner/execution/blocker_analyzer.py tests/test_execution_blocker_preconditions.py
git commit -m "feat: analyze execution prerequisite blockers"
```

---

## Task 5: TestSpec項目とrunner由来の直接ブロッカーを抽出する

**Files:**
- Modify: `src/unit_test_runner/execution/blocker_analyzer.py`
- Create: `tests/test_execution_blocker_test_inputs.py`
- Create: `tests/test_execution_blocker_runner.py`

- [ ] **Step 1: leaf単位の未確定値と親単位の未確認を固定するテストを書く**

`tests/test_execution_blocker_test_inputs.py` でfixtureを使い、次を検証する。

```python
self.assertEqual(
    {
        (
            "TC_candidate",
            "expected_expression",
            "TBD_EXPECTED_VALUE",
            "/additional_case_candidates/0/expected_observations/0/expected_expression",
        )
    },
    {
        (
            blocker.case_id,
            blocker.control_name,
            blocker.current_value,
            blocker.source_pointer,
        )
        for blocker in report.blockers
        if blocker.code == "unresolved_expected_value"
    },
)
```

同じ親objectのrequired controlが具体値だが `review_required=True` の場合は、leafを複製せず次の1件だけになることを検証する。

```python
self.assertEqual(1, len(report.blockers))
self.assertEqual("unconfirmed_test_input", report.blockers[0].code)
self.assertIsNone(report.blockers[0].control_name)
self.assertEqual(
    "/additional_case_candidates/0/expected_observations/0",
    report.blockers[0].source_pointer,
)
```

- [ ] **Step 2: no-caseの一般理由が具体原因と二重計上されないテストを書く**

```python
self.assertNotIn(
    "no_executable_test_cases",
    {item.code for item in report.blockers},
)
```

具体的なblocking fieldがないcandidate-only specでは、逆にgeneric blockerを1件生成する。

- [ ] **Step 3: TestSpec抽出処理を実装する**

analyzerへ次の処理を追加する。

```python
fields = locate_editable_test_spec_fields(test_spec)
for field in fields:
    if not field.execution_blocking:
        continue
    unresolved_controls = [
        control
        for control in field.controls
        if control.required_for_confirmation and is_unresolved(control.value)
    ]
    if unresolved_controls:
        for control in unresolved_controls:
            candidates.append(
                _unresolved_control_candidate(field, control)
            )
    elif not field.confirmed:
        candidates.append(_unconfirmed_parent_candidate(field))
```

codeはkindとcontrol名から決定する。

```python
_CODE_BY_KIND = {
    "input_assignment": "unresolved_input_value",
    "state_setup": "unresolved_state_value",
    "stub_setup": "unresolved_stub_value",
    "expected_observation": "unresolved_expected_value",
}
```

すべてのTestSpec blockerは以下を持つ。

```text
case_id
item_id
control_name（未確認親では省略）
current_value
source_artifact = reports/test_spec.json
source_pointer
recommended_action = open_test_input_editor
```

`current_value` が `None` または空文字の場合は空文字を保存し、「未入力」とMarkdown側で表示する。

- [ ] **Step 4: placeholder禁止時のmapping fallbackをテスト・実装する**

`allow_placeholder_tests=False` かつharness placeholderがcanonical fieldへ一致する場合は、canonical field blockerだけを残す。対応fieldを特定できないplaceholderだけ、次を生成する。

```python
BlockerCandidate(
    priority=50,
    code="placeholder_tests_not_allowed",
    category="test_input",
    severity="error",
    summary="生成ハーネスに未解決プレースホルダーが残っています。",
    case_id=related_case_id,
    source_artifact="reports/harness_skeleton_report.json",
    source_pointer=f"/unresolved_placeholders/{index}",
    recommended_action=RecommendedAction(
        "open_test_input_editor",
        "未確定項目を入力",
    ),
    next_steps=(
        "未確定項目を入力する",
        "テストハーネスを再生成する",
        "ビルドを再実行する",
        "テストを再実行する",
    ),
)
```

- [ ] **Step 5: runner blockedの失敗テストを書く**

`tests/test_execution_blocker_runner.py` で、`executed=True`、status `blocked`、case warningとcombined logを持つreportを作る。

```python
self.assertEqual("runner_reported_blocked", result.blockers[0].code)
self.assertEqual("TC_002", result.blockers[0].case_id)
self.assertEqual("open_execution_log", result.primary_action.code)
self.assertLessEqual(len(result.blockers[0].log_excerpt or ""), 8192)
```

structured case messageがある場合はlog全体を別ブロッカーにしないことも検証する。

- [ ] **Step 6: runner blockerを実装する**

`executed=True` かつ最終statusがblockedの場合、次の順で候補を作る。

1. `case_results[*].warnings` の関連ケース付きメッセージ。
2. `execution_report.warnings` の関連ケース付きメッセージ。
3. どちらもない場合だけcombined log末尾から最大8,192文字の抜粋。
4. ログもない場合は `execution_blocked_unknown` fallbackへ委ねる。

runner候補のsourceは次を使う。

```text
structured case: runs/<run_id>/test_execution_report.json
fallback log: runs/<run_id>/logs/test_execution.log
```

- [ ] **Step 7: 新規テストを通す**

Run:

```powershell
python -m unittest tests.test_execution_blocker_test_inputs tests.test_execution_blocker_runner -v
```

Expected: 全件成功。

- [ ] **Step 8: input-formとexecutionの関連回帰を通す**

Run:

```powershell
python -m unittest tests.test_test_input_form_service tests.test_test_input_form_reclassification tests.test_execution_evidence -v
```

Expected: 全件成功。

- [ ] **Step 9: コミットする**

```powershell
git add src/unit_test_runner/execution/blocker_analyzer.py tests/test_execution_blocker_test_inputs.py tests/test_execution_blocker_runner.py
git commit -m "feat: explain test input and runner blockers"
```

---

## Task 6: 履歴／最新レポートの安全なpublication lifecycleを実装する

**Files:**
- Create: `src/unit_test_runner/execution/blocker_report_writer.py`
- Modify: `src/unit_test_runner/execution/blocker_models.py`
- Create: `tests/test_execution_blocker_writer.py`
- Create: `tests/test_execution_blocker_lifecycle.py`

- [ ] **Step 1: 4ファイルpublicationとMarkdown escapingの失敗テストを書く**

`tests/test_execution_blocker_writer.py` で次を検証する。

```python
result = publish_test_execution_blockers(
    workspace,
    run_paths,
    report,
    subject=SUBJECT,
    producer_commit="test-commit",
)

self.assertTrue(run_paths.blocker_report_json.is_file())
self.assertTrue(run_paths.blocker_report_markdown.is_file())
self.assertTrue((workspace / "reports/test_execution_blockers.json").is_file())
self.assertTrue((workspace / "reports/test_execution_blockers.md").is_file())
self.assertEqual((), result.diagnostics)
```

動的値に `` ` ``, `|`, `<script>` を含め、Markdownにraw HTMLが現れず、tableやcode spanが壊れないことをassertする。

- [ ] **Step 2: 非blocked cleanupと履歴保持の失敗テストを書く**

`tests/test_execution_blocker_lifecycle.py` で次を検証する。

```python
diagnostics = clear_latest_test_execution_blockers(workspace)

self.assertEqual((), diagnostics)
self.assertFalse((workspace / "reports/test_execution_blockers.json").exists())
self.assertFalse((workspace / "reports/test_execution_blockers.md").exists())
self.assertTrue(run_paths.blocker_report_json.exists())
self.assertTrue(run_paths.blocker_report_markdown.exists())
```

- [ ] **Step 3: publication result modelを追加する**

`blocker_models.py` へ追加する。

```python
@dataclass(frozen=True)
class BlockerPublicationDiagnostic:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True)
class BlockerPublicationResult:
    report: TestExecutionBlockerReport | None
    run_json: Path | None = None
    run_markdown: Path | None = None
    latest_json: Path | None = None
    latest_markdown: Path | None = None
    diagnostics: tuple[BlockerPublicationDiagnostic, ...] = ()

    def blocker_reference(self, workspace: Path) -> dict[str, str] | None:
        if self.report is None or self.run_json is None:
            return None
        digest = sha256_file(self.run_json)
        if digest is None:
            return None
        value = {
            "artifact_kind": "test_execution_blocker_report",
            "path": self.run_json.relative_to(workspace).as_posix(),
            "sha256": digest,
        }
        if self.run_markdown is not None:
            value["markdown_path"] = self.run_markdown.relative_to(workspace).as_posix()
        return value
```

`blocker_reference` はpointer schema上Markdown必須なので、run Markdownがない場合は `None` を返す。CLIはrun JSONだけを別途成果物として返せる。

- [ ] **Step 4: writerを実装する**

公開APIを次で固定する。

```python
def publish_test_execution_blockers(
    workspace: Path | str,
    run_paths: RunPaths,
    report: TestExecutionBlockerReport,
    *,
    subject: Mapping[str, str],
    producer_commit: str,
) -> BlockerPublicationResult:
```

```python
def clear_latest_test_execution_blockers(
    workspace: Path | str,
) -> tuple[BlockerPublicationDiagnostic, ...]:
```

```python
def render_test_execution_blockers_markdown(
    report: TestExecutionBlockerReport,
) -> str:
```

publication順序をコードで固定する。

```text
1. build_artifact_payload(TEST_EXECUTION_BLOCKER_REPORT, report.to_data())
2. write_validated_artifact(run_json, atomic=True)
3. Markdownをtemporary fileへ書きos.replace
4. run JSON/Markdownの存在確認
5. latest JSON/Markdownをそれぞれtemporary fileへcopyしos.replace
6. どちらかのlatest同期に失敗したらlatest両方を削除
```

履歴JSON失敗時は履歴Markdownを作らず、latest両方を削除し、`blocker_report_write_failed` diagnosticを返す。履歴Markdownだけ失敗した場合は履歴JSONを保持し、latestは同期せず、`blocker_report_markdown_failed` を返す。

- [ ] **Step 5: writerとlifecycleテストを通す**

Run:

```powershell
python -m unittest tests.test_execution_blocker_writer tests.test_execution_blocker_lifecycle -v
```

Expected: 全件成功。

- [ ] **Step 6: failure injectionテストを追加する**

`unittest.mock.patch` で `os.replace` とMarkdown writerを失敗させ、次を検証する。

```text
- report objectは失われない
- diagnosticが返る
- 古いlatest 2ファイルは残らない
- 成功済みrun JSONは保持される
- run履歴は上書きされない
```

- [ ] **Step 7: コミットする**

```powershell
git add src/unit_test_runner/execution/blocker_models.py src/unit_test_runner/execution/blocker_report_writer.py tests/test_execution_blocker_writer.py tests/test_execution_blocker_lifecycle.py
git commit -m "feat: publish execution blocker reports"
```

---

## Task 7: execution orchestrationとlatest_run pointerへ統合する

**Files:**
- Modify: `src/unit_test_runner/execution/execution_models.py`
- Modify: `src/unit_test_runner/execution/precondition_validator.py`
- Modify: `src/unit_test_runner/execution/test_execution.py`
- Modify: `src/unit_test_runner/execution/report_loader.py`
- Create: `tests/test_execution_blocker_orchestration.py`

- [ ] **Step 1: blocked実行がpublication metadataを保持する失敗テストを書く**

`tests/test_execution_blocker_orchestration.py` で、既存fixtureを使って `execute_test_run` をblockedにし、次をassertする。

```python
self.assertEqual("blocked", report.status)
self.assertIsNotNone(report.blocker_publication)
self.assertIsNotNone(report.blocker_publication.report)
self.assertGreater(report.blocker_publication.report.blocker_count, 0)
self.assertTrue(report.run_paths.blocker_report_json.is_file())
```

`latest_run.json` について次をassertする。

```python
pointer = json.loads((workspace / "reports/latest_run.json").read_text(encoding="utf-8"))
self.assertEqual(
    report.run_paths.run_id,
    pointer["data"]["run_id"],
)
self.assertEqual(
    "test_execution_blocker_report",
    pointer["data"]["blocker_report"]["artifact_kind"],
)
```

- [ ] **Step 2: nonblocked実行が最新だけ消す失敗テストを書く**

先にblocked reportをpublishしてからrunnerをpassedにmockし、後続実行後に次をassertする。

```python
self.assertFalse((workspace / "reports/test_execution_blockers.json").exists())
self.assertFalse((workspace / "reports/test_execution_blockers.md").exists())
self.assertNotIn("blocker_report", latest_run["data"])
self.assertTrue(old_run_json.exists())
self.assertTrue(old_run_markdown.exists())
```

- [ ] **Step 3: TestExecutionReportへnonserialized publication fieldを追加する**

`execution_models.py` のTYPE_CHECKINGへ追加する。

```python
if TYPE_CHECKING:
    from .blocker_models import BlockerPublicationResult
```

`TestExecutionReport` 末尾へ追加する。`to_dict()` には含めない。

```python
blocker_publication: BlockerPublicationResult | None = field(
    default=None,
    repr=False,
    compare=False,
)
```

- [ ] **Step 4: harness readinessを実行前提へ追加する**

`execute_test_run` と `validate_test_run_preflight` では、harness reportだけをoptional readへ変更する。

```python
harness_report = _read_optional_json(
    reports / "harness_skeleton_report.json"
) or {}
```

TestSpec、build probe、build workspaceは引き続き必須入力として扱う。harness report欠落はこの機能で説明可能なblocked前提へ変換する。

`precondition_validator.py` に次を追加する。

```python
def validate_harness_preconditions(
    workspace: Path,
    harness_report: dict[str, Any],
    test_spec: dict[str, Any],
) -> tuple[str, list[TestExecutionWarning], list[ExecutionReviewItem]]:
    test_cases = list(test_spec.get("test_cases") or [])
    if not test_cases:
        return "ready", [], []
    generated = [
        item
        for item in harness_report.get("generated_files") or []
        if isinstance(item, dict) and item.get("file_kind") == "test_source"
    ]
    missing = [
        item
        for item in generated
        if not (workspace / str(item.get("path") or "")).is_file()
    ]
    status = str((harness_report.get("function") or {}).get("status") or "unknown")
    if generated and not missing and status in {"generated", "partial"}:
        return "ready", [], []
    message = "現在のテスト仕様に対応するテストハーネスがありません。"
    return (
        "blocked",
        [TestExecutionWarning("harness_missing_or_stale", message)],
        [
            ExecutionReviewItem(
                "REVIEW_HARNESS_001",
                "harness_missing_or_stale",
                None,
                message,
                "テストハーネスを再生成してください。",
                "error",
            )
        ],
    )
```

`execute_test_run` は既存 `validate_execution_preconditions` が `ready` を返した後にこのharness判定を実行する。build probeと実行ファイルのblockerを優先し、そこがreadyの場合だけharnessを確認する。harnessがblockedならrunnerを起動しない。`test_spec` と `harness_report` はすでに読込済みのpayloadを使う。これによりTask 4のharness blockerが実際のexit 35経路から到達可能になる。

- [ ] **Step 5: execute_test_runへpublicationを統合する**

通常のimmutable execution report保存とhash計算の後に追加する。

```python
publication: BlockerPublicationResult
if report.status == RunOutcome.BLOCKED.value:
    try:
        blocker_report = analyze_test_execution_blockers(
            workspace,
            paths,
            report,
            execution_hash,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        blocker_report = build_blocker_report(
            run_id=paths.run_id,
            execution_report_path=paths.execution_report.relative_to(workspace).as_posix(),
            execution_report_sha256=execution_hash,
            candidates=(
                BlockerCandidate(
                    priority=90,
                    code="execution_blocked_unknown",
                    category="unknown",
                    severity="blocking",
                    summary=f"ブロック理由の詳細解析に失敗しました: {error}",
                    source_artifact=paths.execution_report.relative_to(workspace).as_posix(),
                    recommended_action=RecommendedAction(
                        "open_execution_report",
                        "テスト実行レポートを開く",
                    ),
                    next_steps=("テスト実行レポートを確認する",),
                ),
            ),
        )
    publication = publish_test_execution_blockers(
        workspace,
        paths,
        blocker_report,
        subject=subject,
        producer_commit=producer_commit,
    )
else:
    publication = BlockerPublicationResult(
        report=None,
        diagnostics=clear_latest_test_execution_blockers(workspace),
    )
report.blocker_publication = publication
```

latest pointer dataをhelperで構築する。

```python
pointer_data = {
    "run_id": paths.run_id,
    "execution_report": {
        "artifact_kind": ArtifactKind.TEST_EXECUTION_REPORT.value,
        "path": paths.execution_report.relative_to(workspace).as_posix(),
        "sha256": execution_hash,
    },
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
blocker_reference = publication.blocker_reference(workspace)
if blocker_reference is not None:
    pointer_data["blocker_report"] = blocker_reference
```

- [ ] **Step 6: evidence再読込後もpublication metadataを引き継ぐ**

`prepare_test_execution_evidence` のactual run経路で次を追加する。

```python
loaded_report.run_paths = report.run_paths
loaded_report.blocker_publication = report.blocker_publication
```

`report_loader.py` のlegacy importはblocker referenceを追加しない。既存runの読込時も `blocker_publication` は `None` のままとし、後続TaskのVS Code restorationはpointerとartifactから独立して復元する。

- [ ] **Step 7: publication failureがstatusを変えないテストを追加する**

writerをmockしてdiagnostic resultを返し、次をassertする。

```python
self.assertEqual("blocked", report.status)
self.assertFalse(report.executed)
self.assertIsNotNone(report.blocker_publication)
self.assertTrue(report.blocker_publication.diagnostics)
```

- [ ] **Step 8: orchestrationテストを通す**

Run:

```powershell
python -m unittest tests.test_execution_blocker_orchestration tests.test_execution_evidence tests.test_evidence_integrity -v
```

Expected: 全件成功。

- [ ] **Step 9: コミットする**

```powershell
git add src/unit_test_runner/execution tests/test_execution_blocker_orchestration.py
git commit -m "feat: integrate blocker reports into test runs"
```

---

## Task 8: CLIのblockedメッセージ、details、diagnostics、成果物を追加する

**Files:**
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `src/unit_test_runner/cli/result.py`
- Create: `tests/test_cli_execution_blockers.py`
- Modify: `tests/test_cli_execution_exit_codes.py`
- Modify: `tests/test_execution_evidence.py`

- [ ] **Step 1: exit 35を維持したaction-oriented envelopeテストを書く**

`tests/test_cli_execution_blockers.py` にblocked workspace fixtureを作り、CLIを実行する。

```python
completed = run_module(
    "--json",
    "run-tests",
    "--workspace",
    str(workspace),
    "--run",
)
payload = json.loads(completed.stdout)
details = payload["data"]["details"]

self.assertEqual(35, completed.returncode)
self.assertEqual("blocked", payload["data"]["outcome"])
self.assertEqual("run-tests", payload["data"]["command"])
self.assertGreater(details["blockers"]["count"], 0)
self.assertIn(
    details["blockers"]["primary_action"],
    {
        "open_test_input_editor",
        "open_build_probe_report",
        "generate_harness",
        "choose_or_build_executable",
        "open_execution_log",
        "open_execution_report",
    },
)
self.assertIn("blocked by", payload["data"]["message"])
self.assertFalse(payload["data"]["errors"])
```

artifactsにcanonical JSONとMarkdown、latest viewsが含まれることを検証する。

- [ ] **Step 2: 非blocked結果にblockersがないテストを書く**

passed、failed、inconclusive、timed_out、cancelledは既存分類unitを使い、`details` に `blockers` がなく、blocker artifact kindがないことをassertする。

- [ ] **Step 3: CLI payload helperを実装する**

`commands.py` に追加する。

```python
def _blocker_payload(workspace: Path, report) -> dict[str, Any] | None:
    publication = getattr(report, "blocker_publication", None)
    blocker_report = getattr(publication, "report", None)
    if blocker_report is None:
        return None
    value: dict[str, Any] = {
        "count": blocker_report.blocker_count,
        "primary_action": blocker_report.primary_action.code,
    }
    for key, path in (
        ("run_json", publication.run_json),
        ("run_markdown", publication.run_markdown),
        ("latest_json", publication.latest_json),
        ("latest_markdown", publication.latest_markdown),
    ):
        if path is not None and path.is_file():
            value[key] = path.relative_to(workspace).as_posix()
    return value
```

`handle_run_tests` でblocked時だけ追加する。

```python
blockers = _blocker_payload(workspace, report)
if blockers is not None:
    payload["blockers"] = blockers
```

messageを切り替える。

```python
message = "Test execution evidence prepared with the reported terminal outcome."
if outcome.state is RunOutcome.BLOCKED and blockers is not None:
    report_path = blockers.get("latest_markdown") or blockers.get("run_markdown")
    suffix = f" See {report_path}." if report_path else ""
    message = (
        f"Test execution was blocked by {blockers['count']} items."
        f"{suffix}"
    )
```

- [ ] **Step 4: human outputを実装する**

`handle_run_tests` でblocked時に `human_output` を設定する。

```python
def _blocked_human_output(blockers: dict[str, Any]) -> str:
    lines = [
        f"テスト実行は{blockers['count']}件の項目でブロックされました。",
        "",
        "最初に行う操作:",
        f"  {_human_action_label(str(blockers['primary_action']))}",
    ]
    report_path = blockers.get("latest_markdown") or blockers.get("run_markdown")
    if report_path:
        lines.extend(["", "一覧:", f"  {report_path}"])
    return "\n".join(lines) + "\n"
```

`CLIResult.render_human` の一般ロジックは変更せず、既存 `human_output` fieldを利用する。

- [ ] **Step 5: publication diagnosticsをCLI diagnosticsへ渡す**

```python
diagnostics = [
    item.to_dict()
    for item in getattr(
        getattr(report, "blocker_publication", None),
        "diagnostics",
        (),
    )
]
```

blocked report生成失敗でも `errors` は空、exit 35、outcome blockedのままにする。

- [ ] **Step 6: `_run_artifacts`へblocker成果物を追加する**

publication resultに存在するpathだけ候補へ加える。

```python
publication = getattr(report, "blocker_publication", None)
if publication is not None:
    for path, kind in (
        (publication.run_json, ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT.value),
        (publication.run_markdown, "test_execution_blocker_view"),
        (publication.latest_json, ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT.value),
        (publication.latest_markdown, "test_execution_blocker_view"),
    ):
        if path is not None and path.is_file():
            candidates.append((path, kind))
```

latest JSONはrun JSONのcopyだが同じcontract identityを持つためclaim可能。Markdownには明示的view kindを使う。

- [ ] **Step 7: CLIテストを通す**

Run:

```powershell
python -m unittest tests.test_cli_execution_blockers tests.test_cli_execution_exit_codes tests.test_execution_evidence -v
```

Expected: 全件成功。

- [ ] **Step 8: コミットする**

```powershell
git add src/unit_test_runner/cli tests/test_cli_execution_blockers.py tests/test_cli_execution_exit_codes.py tests/test_execution_evidence.py
git commit -m "feat: expose blocked execution reports in cli"
```

---

## Task 9: VS Code用のstrict blocked envelope parserと成果物検証を実装する

**Files:**
- Modify: `vscode/extension/src/cli/cliEnvelope.ts`
- Modify: `vscode/extension/src/cli/cliResultParser.ts`
- Modify: `vscode/extension/src/reports/reportPathResolver.ts`
- Create: `vscode/extension/src/executionBlockers/contracts.ts`
- Create: `vscode/extension/src/executionBlockers/reportResolver.ts`
- Create: `vscode/extension/src/test/executionBlockerContracts.test.ts`
- Create: `vscode/extension/src/test/executionBlockerResolver.test.ts`

- [ ] **Step 1: strict parserの失敗テストを書く**

`executionBlockerContracts.test.ts` でv1 blocked envelopeを組み立て、次を検証する。

```typescript
const parsed = parseBlockedRunDetails(envelope);
assert.equal(parsed.runId, 'run-1');
assert.equal(parsed.count, 2);
assert.equal(parsed.primaryAction, 'open_test_input_editor');
assert.equal(parsed.latestMarkdown, 'reports/test_execution_blockers.md');
```

以下はthrowする。

```text
- commandがrun-tests以外
- outcomeがblocked以外
- exit_codeが35以外
- blockers.countが0以下
- unknown primary_action
- absolute path、backslash path、.. path
- detailsに余分なproperty
```

- [ ] **Step 2: report resolverの失敗テストを書く**

一時workspaceにexecution report、blocker JSON/Markdown、latest_runを配置し、SHAを一致させる。次をassertする。

```typescript
const resolved = await resolveBlockedRunArtifacts(workspace, parsed, producedArtifacts);
assert.equal(resolved.reportMarkdown, path.join(workspace, 'reports', 'test_execution_blockers.md'));
assert.equal(resolved.runId, 'run-1');
```

以下は `undefined` またはtyped errorにする。

```text
- blocker JSON hash mismatch
- Markdownがworkspace外symlink/junction
- latest_run run ID mismatch
- blocker JSONのexecution_report path mismatch
- stale reports fileだけ存在
- produced artifactに宣言されていないpath
```

- [ ] **Step 3: ReportPathsとartifact filename mappingを追加する**

`reportPathResolver.ts` へ追加する。

```typescript
testExecutionBlockersJson?: string;
testExecutionBlockersMd?: string;
testExecutionBlockersRunJson?: string;
testExecutionBlockersRunMd?: string;
```

conventional latest pathsを追加する。

```typescript
testExecutionBlockersJson: dialect.join(reports, 'test_execution_blockers.json'),
testExecutionBlockersMd: dialect.join(reports, 'test_execution_blockers.md'),
```

`cliEnvelope.ts` はbasenameだけでなくartifact path全体でkeyを決める。

```typescript
if (artifact.path.startsWith('reports/') && name === 'test_execution_blockers.md') {
  return 'test_execution_blockers_md';
}
if (artifact.path.startsWith('runs/') && name === 'test_execution_blockers.md') {
  return 'test_execution_blockers_run_md';
}
```

JSONも同様にする。

- [ ] **Step 4: blocked details contractを実装する**

`contracts.ts` の公開型を次で固定する。

```typescript
export type BlockerPrimaryAction =
  | 'open_test_input_editor'
  | 'open_build_probe_report'
  | 'generate_harness'
  | 'run_build_probe'
  | 'choose_or_build_executable'
  | 'open_execution_log'
  | 'open_execution_report';

export interface BlockedRunDetails {
  runId: string;
  count: number;
  primaryAction: BlockerPrimaryAction;
  runJson?: string;
  runMarkdown?: string;
  latestJson?: string;
  latestMarkdown?: string;
}

export function parseBlockedRunDetails(value: unknown): BlockedRunDetails;
```

`parseCliEnvelopeValue` を先に通し、`raw.data.details.blockers` をexact-key validationする。publication失敗時はpath propertiesを省略可能にするが、countとprimary actionは必須とする。

- [ ] **Step 5: report resolverを実装する**

`reportResolver.ts` の公開APIを次で固定する。

```typescript
export interface VerifiedBlockedRunArtifacts {
  runId: string;
  count: number;
  primaryAction: BlockerPrimaryAction;
  reportJson: string;
  reportMarkdown: string;
  reportSha256: string;
}

export async function resolveBlockedRunArtifacts(
  workspace: string,
  details: BlockedRunDetails,
  artifacts: readonly CliProducedArtifact[],
): Promise<VerifiedBlockedRunArtifacts | undefined>;

export async function restoreBlockedRunArtifacts(
  workspace: string,
): Promise<VerifiedBlockedRunArtifacts | undefined>;
```

検証順序を固定する。

```text
1. relative contract path validation
2. path.resolve後workspace containment
3. symlink/junctionの実体containment
4. produced artifactのpath/kind/hash照合
5. blocker JSONのartifact_kind/schema/data構造
6. blocker JSON自身のSHA-256
7. execution report参照とrun ID
8. Markdown存在・containment
9. latest候補が失敗した場合だけrun-history候補へfallback
```

restorationは `reports/latest_run.json` から始め、同じ検証を行う。stray latest Markdownだけでは復元しない。

- [ ] **Step 6: parser/resolverテストを通す**

Run:

```powershell
Set-Location vscode/extension
npm.cmd test -- --test-name-pattern="execution blocker"
```

このtest runnerがfilterをforwardしない場合は通常の `npm.cmd test` を実行する。

Expected: 新規テストを含め全件成功。

- [ ] **Step 7: コミットする**

```powershell
git add vscode/extension/src/cli vscode/extension/src/reports/reportPathResolver.ts vscode/extension/src/executionBlockers vscode/extension/src/test/executionBlockerContracts.test.ts vscode/extension/src/test/executionBlockerResolver.test.ts
git commit -m "feat: validate blocked execution artifacts in vscode"
```

---

## Task 10: exit 35をhandled blocked outcomeとして処理し、自動表示する

**Files:**
- Modify: `vscode/extension/src/extension.ts`
- Modify: `vscode/extension/src/workflow/workflowState.ts`
- Create: `vscode/extension/src/executionBlockers/workflowIntegration.ts`
- Create: `vscode/extension/src/test/blockedRunHandling.test.ts`
- Create: `vscode/extension/src/test/executionBlockerWorkflowIntegration.test.ts`

- [ ] **Step 1: valid exit35とinvalid exit35の失敗テストを書く**

`blockedRunHandling.test.ts` ではCLI runner、report resolver、openMarkdown、workspaceStateをdependency injectionできるpure handlerへ分離してテストする。

```typescript
const result = await classifyWorkspaceCliResult({
  invocation,
  cliResult: {
    exitCode: 35,
    stdout: JSON.stringify(blockedEnvelope),
    stderr: '',
    timedOut: false,
    commandLine: 'unit-test-runner --json run-tests --workspace C:\\out --run',
  },
  workspace: 'C:\\out',
  resolveArtifacts: async () => verified,
});

assert.equal(result.kind, 'blocked');
assert.equal(result.blocked?.count, 3);
```

invalid JSONでは次をassertする。

```typescript
assert.equal(result.kind, 'failure');
assert.match(result.message, /終了コード 35/);
```

- [ ] **Step 2: Workflow state reducerの失敗テストを書く**

`executionBlockerWorkflowIntegration.test.ts` で次を検証する。

```typescript
const blocked = applyExecutionBlockerState(
  createInitialWorkflowState(true),
  workspace,
  verified,
);
assert.equal(blocked.testExecutionBlockers?.status, 'blocked');
assert.equal(blocked.testExecutionBlockers?.count, 3);

const cleared = clearExecutionBlockerState(blocked, workspace);
assert.equal(cleared.testExecutionBlockers, undefined);
```

別workspaceの非blocked実行は現在workspaceのstateを消さない。

- [ ] **Step 3: Workflow state型を追加する**

`workflowState.ts` へ追加する。

```typescript
export interface TestExecutionBlockerState {
  status: 'blocked';
  workspace: string;
  runId: string;
  count: number;
  primaryAction: BlockerPrimaryAction;
  reportJson?: string;
  reportMarkdown?: string;
  reportSha256?: string;
  updatedAt: string;
}
```

`WorkflowState` へ追加する。

```typescript
testExecutionBlockers?: TestExecutionBlockerState;
```

workspace切替時は `testInputSummary` と同様にclearする。

- [ ] **Step 4: pure classificationを追加する**

`workflowIntegration.ts` に以下を実装する。

```typescript
export type WorkspaceCliTerminalResult =
  | { kind: 'success'; reports: ReportPaths; parsed: ParsedCliResult }
  | { kind: 'blocked'; reports: ReportPaths; parsed: ParsedCliResult; blocked: VerifiedBlockedRunArtifacts | BlockedRunDetails }
  | { kind: 'nonblocked-terminal'; reports: ReportPaths; parsed: ParsedCliResult; outcome: 'failed' | 'inconclusive' | 'timed_out' | 'cancelled'; message: string }
  | { kind: 'failure'; message: string };
```

`classifyWorkspaceCliResult` は先にprocess timeout、次にexit0、次にvalid v1 `run-tests --run` terminal envelopeを判定する。blockedは `kind: 'blocked'`、failed／inconclusive／timed_out／cancelledは `kind: 'nonblocked-terminal'` とする。structured blockedでpublication pathが検証できなくても `kind: 'blocked'` を返し、openable metadataだけ省略する。JSONが不正な非zeroは最後に一般failureへ落とす。

- [ ] **Step 5: `executeInvocation`をhandled blocked対応へ変更する**

戻り型を次へ変更する。

```typescript
interface BlockedExecutionOutcome {
  runId: string;
  count: number;
  primaryAction: BlockerPrimaryAction;
  reportJson?: string;
  reportMarkdown?: string;
  reportSha256?: string;
}

interface WorkspaceInvocationResult {
  reports: ReportPaths;
  terminalOutcome: CliRunOutcome;
  blocked?: BlockedExecutionOutcome;
  terminalMessage?: string;
}
```

`BlockedRunDetails` と `VerifiedBlockedRunArtifacts` は `normalizeBlockedExecutionOutcome` でこの型へ統一する。valid blockedでは `recordWorkflowError` を呼ばない。warning notificationを表示し、verified Markdownがある場合だけ自動で開く。

```typescript
if (classified.kind === 'blocked') {
  const blocked = classified.blocked;
  if (blocked.reportMarkdown && await shouldAutoOpenBlockerRun(context, blocked.runId)) {
    await openMarkdown(blocked.reportMarkdown);
    await context.workspaceState.update(
      LAST_AUTO_OPENED_BLOCKER_RUN_KEY,
      blocked.runId,
    );
  }
  void vscode.window.showWarningMessage(
    `UnitTestRunner: テスト実行は${blocked.count}件の項目でブロックされました。`,
  );
  return { reports: classified.reports, blocked };
}
```

publication diagnosticでreportがない場合はwarningだけを出し、通常CLI errorにはしない。

- [ ] **Step 6: `runWorkspaceCommand`でstateを反映する**

`kind === 'runTests'` の場合:

```text
- blockedならrunTests stepを実行済みとして記録し、blocker stateを保存
- passedならblocker stateをclearして通常successとして記録
- failed/inconclusive/timed_out/cancelledなら、まずblocker stateをclearして実行レポートpathを保存し、その後に既存と同等のerror/warning通知を表示
- plannedはこの経路へ入らない
```

非blocked terminal outcomeを通知上は失敗扱いにしても、state cleanupはthrowより前に完了させる。これにより過去の「実行ブロック項目を開く」ボタンが残らない。auto-openはblockedだけに限定する。

- [ ] **Step 7: handlingとstateテストを通す**

Run:

```powershell
Set-Location vscode/extension
npm.cmd test
```

Expected: 全件成功。

- [ ] **Step 8: コミットする**

```powershell
git add vscode/extension/src/extension.ts vscode/extension/src/workflow/workflowState.ts vscode/extension/src/executionBlockers/workflowIntegration.ts vscode/extension/src/test/blockedRunHandling.test.ts vscode/extension/src/test/executionBlockerWorkflowIntegration.test.ts
git commit -m "feat: handle blocked test runs in vscode"
```

---

## Task 11: Workflowボタン、primary action、再起動復元を追加する

**Files:**
- Modify: `vscode/extension/package.json`
- Modify: `vscode/extension/src/commands/commandRegistry.ts`
- Modify: `vscode/extension/src/extension.ts`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts`
- Modify: `vscode/extension/src/workflow/workflowState.ts`
- Create: `vscode/extension/src/executionBlockers/actions.ts`
- Create: `vscode/extension/src/executionBlockers/primaryAction.ts`
- Create: `vscode/extension/src/test/executionBlockerActions.test.ts`
- Modify: `vscode/extension/src/test/workflowPanel.test.ts`
- Modify: `vscode/extension/src/test/uiCopy.test.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`

- [ ] **Step 1: Workflow表示の失敗テストを書く**

`workflowPanel.test.ts` へ追加する。

```typescript
const action: WorkflowAction = {
  id: 'openExecutionBlockers',
  kind: 'command',
  label: '実行ブロック項目を開く',
  commandId: 'unitTestRunner.openTestExecutionBlockers',
};

const presentation = resolveWorkflowActionPresentation(
  action,
  'current',
  stateWithThreeBlockers,
);
assert.equal(presentation.label, '実行ブロック項目を開く（3件）');
assert.match(presentation.classes, /danger/);
assert.equal(presentation.hidden, false);
```

stateなし、またはverified report pathなしならhiddenになることをassertする。

- [ ] **Step 2: primary action routingの失敗テストを書く**

`executionBlockerActions.test.ts` では、stable codeを1つの専用commandへ渡すpresentationと、実行時routingを分離して検証する。

```typescript
assert.equal(
  primaryActionLabel('open_test_input_editor'),
  '未確定項目を入力',
);
assert.equal(
  primaryActionLabel('generate_harness'),
  'テストハーネスを生成',
);
```

`runPrimaryBlockerAction` のdependency injection testでは次を確認する。

```typescript
await runPrimaryBlockerAction('open_test_input_editor', context);
assert.deepEqual(executedCommands, ['unitTestRunner.openTestInputEditor']);

await runPrimaryBlockerAction('generate_harness', context);
assert.deepEqual(executedCommands, [
  'unitTestRunner.openTestInputEditor',
  'unitTestRunner.generateHarnessSkeleton',
]);
```

`open_build_probe_report`、`choose_or_build_executable` はcurrent build reportをverified workspace内から開く。`open_execution_log` と `open_execution_report` はrestored blocker artifactを読み、primary action blockerに記録されたworkspace相対pathだけを検証して開く。

- [ ] **Step 3: commandを登録する**

`package.json` のactivationEventsとcommandsへ追加する。

```json
"onCommand:unitTestRunner.openTestExecutionBlockers",
"onCommand:unitTestRunner.runExecutionBlockerPrimaryAction"
```

```json
{
  "command": "unitTestRunner.openTestExecutionBlockers",
  "title": "UnitTestRunner: 実行ブロック項目を開く"
},
{
  "command": "unitTestRunner.runExecutionBlockerPrimaryAction",
  "title": "UnitTestRunner: 実行ブロックの推奨操作を実行"
}
```

`commandRegistry.ts` のID一覧へ追加する。

- [ ] **Step 4: verified reportを再検証して開くcommandを実装する**

`extension.ts` handlerへ追加する。

```typescript
'unitTestRunner.openTestExecutionBlockers': async () => {
  const state = readWorkflowState(context).testExecutionBlockers;
  if (!state?.reportMarkdown) {
    throw new Error('現在の実行ブロック項目レポートはありません。');
  }
  const restored = await restoreBlockedRunArtifacts(state.workspace);
  if (!restored || restored.runId !== state.runId) {
    throw new Error('実行ブロック項目レポートが最新実行と一致しません。');
  }
  await openMarkdown(restored.reportMarkdown);
},
```

stateのpath文字列を無検証で開かない。

- [ ] **Step 5: Workflow actionsを追加する**

`workflowState.ts` のrunTestsまたはreviewEvidence actionsへ次を追加する。

```typescript
{
  id: 'openExecutionBlockers',
  kind: 'command',
  label: '実行ブロック項目を開く',
  commandId: 'unitTestRunner.openTestExecutionBlockers',
  danger: true,
}
```

`SIMPLE_SECONDARY_ACTIONS` にも同じactionを追加する。

`resolveWorkflowActionPresentation` へ次を追加する。

```typescript
if (action.id === 'openExecutionBlockers') {
  const blockers = state?.testExecutionBlockers;
  if (blockers?.reportMarkdown) {
    label = `実行ブロック項目を開く（${blockers.count}件）`;
    danger = true;
  }
}
```

hidden条件:

```typescript
action.id === 'openExecutionBlockers'
  && !state?.testExecutionBlockers?.reportMarkdown
```

- [ ] **Step 6: primary actionボタンと専用routerを実装する**

`actions.ts` はstable codeから固定日本語labelだけを返す。

```typescript
export function primaryActionLabel(code: BlockerPrimaryAction): string {
  return {
    open_test_input_editor: '未確定項目を入力',
    open_build_probe_report: 'ビルド結果を開く',
    generate_harness: 'テストハーネスを生成',
    run_build_probe: 'ビルドを実行',
    choose_or_build_executable: '実行ファイルを準備',
    open_execution_log: 'テスト実行ログを開く',
    open_execution_report: 'テスト実行レポートを開く',
  }[code];
}
```

`primaryAction.ts` は次の公開関数を持つ。

```typescript
export async function runPrimaryBlockerAction(
  code: BlockerPrimaryAction,
  dependencies: PrimaryActionDependencies,
): Promise<void>;
```

routingを固定する。

```text
open_test_input_editor -> unitTestRunner.openTestInputEditor
generate_harness -> unitTestRunner.generateHarnessSkeleton
run_build_probe -> unitTestRunner.runBuildProbe
open_build_probe_report / choose_or_build_executable -> verified current build_probe_report.md
open_execution_log -> blocker JSONのprimary blocker source_artifact/related_fileからverified run log
open_execution_report -> latest_runが参照するverified test_execution_report.json
```

Workflowは `unitTestRunner.runExecutionBlockerPrimaryAction` を1つだけ表示し、handlerがcurrent stateのstable codeをrouterへ渡す。localized labelをcommand routingに使わない。

- [ ] **Step 7: activation時復元を実装する**

`activate` の最後で、test-input summary refreshと並行して呼ぶ。

```typescript
void restoreExecutionBlockerWorkflowState(context, workflowPanel);
```

復元成功時のみstateへ格納し、auto-openは行わない。auto-openは新しい実行結果に対してだけ行う。復元失敗時は現在workspaceに属する古いstateをclearする。

- [ ] **Step 8: UI copy、Workflow、adapterテストを通す**

Run:

```powershell
Set-Location vscode/extension
npm.cmd test
npm.cmd run test:extension-host
```

Expected: unit testsとExtension Hostが成功。

- [ ] **Step 9: コミットする**

```powershell
git add vscode/extension/package.json vscode/extension/src/commands vscode/extension/src/extension.ts vscode/extension/src/workflow vscode/extension/src/executionBlockers/actions.ts vscode/extension/src/test
git commit -m "feat: surface execution blockers in workflow"
```

---

## Task 12: 結合テスト、ドキュメント、配布契約、全回帰を完成する

**Files:**
- Create: `tests/test_execution_blocker_end_to_end.py`
- Modify: `tests/test_distribution_build_script.py`
- Modify: `README.md`
- Modify: `docs/vscode_usage_guide.md`
- Modify: `docs/test_input_editor.md`
- Modify: `vscode/extension/README.md`

- [ ] **Step 1: blocked → 解消 → nonblocked lifecycle結合テストを書く**

`tests/test_execution_blocker_end_to_end.py` で次の流れを1テストにする。

```text
1. canonical TestSpecにcandidateとTBD_EXPECTED_VALUEを作成
2. build probeはsucceeded、runner fileは存在する状態にする
3. run-tests --runを実行しexit 35を確認
4. run履歴とlatestの4ファイルを確認
5. blocker JSONにcase ID、item ID、control、current value、pointerがあることを確認
6. apply-test-input-form相当のcanonical APIで値を入力・確認済みにする
7. harnessを再生成する
8. runnerをpassed結果へmockする
9. 再度actual runを行う
10. latest blocker filesが削除され、最初のrun履歴が残ることを確認
```

固定IDやfingerprintをテストへ直書きせず、`build_test_input_form` の現在出力から取得する。

- [ ] **Step 2: build-precondition結合テストを書く**

build probe reportに2件のerror診断を作り、CLI run後に次をassertする。

```python
self.assertEqual(35, completed.returncode)
self.assertEqual(2, blocker_data["data"]["blocker_count"])
self.assertEqual(
    "open_build_probe_report",
    blocker_data["data"]["primary_action"]["code"],
)
self.assertNotIn(
    "unresolved_expected_value",
    {item["code"] for item in blocker_data["data"]["blockers"]},
)
```

前提条件で早期blockされた場合に、後段の無関係なTestSpecレビュー項目を混ぜないことを保証する。

- [ ] **Step 3: 配布契約テストを拡張する**

`tests/test_distribution_build_script.py` で次を確認する。

```text
- build_distribution.ps1がschemasをcollectする既存設定を維持
- wheel内にtest_execution_blocker_report.schema.jsonがある
- VSIX manifestにunitTestRunner.openTestExecutionBlockersがある
- compiled extensionにtest_execution_blockers.mdのpath mappingがある
```

CI package-contractのinline Pythonは全ArtifactKind schemaを確認するため、新kind追加で自動的にcoverageされることも明記する。

- [ ] **Step 4: 利用手順を更新する**

`README.md` と `docs/vscode_usage_guide.md` に次の導線を追加する。

```text
run-testsがBLOCKED（終了コード35）
→ reports/test_execution_blockers.mdが自動で開く
→ 「最初に行う操作」に従う
→ Workflowの「実行ブロック項目を開く（N件）」から再表示可能
```

`docs/test_input_editor.md` には、primary actionが未確定入力の場合の手順を追加する。

```text
未確定項目を入力
→ 確認済みにする
→ 保存して反映
→ ハーネス再生成
→ ビルド
→ テスト再実行
```

`vscode/extension/README.md` のトラブルシューティングへ終了コード35を追加する。

- [ ] **Step 5: targeted Python testsを実行する**

Run:

```powershell
python -m compileall -q src tests
python -m unittest `
  tests.test_execution_blocker_contract `
  tests.test_test_input_form_read_model `
  tests.test_execution_blocker_models `
  tests.test_execution_blocker_preconditions `
  tests.test_execution_blocker_test_inputs `
  tests.test_execution_blocker_runner `
  tests.test_execution_blocker_writer `
  tests.test_execution_blocker_lifecycle `
  tests.test_execution_blocker_orchestration `
  tests.test_cli_execution_blockers `
  tests.test_execution_blocker_end_to_end -v
```

Expected: 全件成功。

- [ ] **Step 6: 全Python testsをCIと同じ分離プロセスで実行する**

Run from repository root in PowerShell:

```powershell
$failed = @()
$modules = Get-ChildItem -LiteralPath .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
foreach ($module in $modules) {
  & python -m unittest $module -v
  if ($LASTEXITCODE -ne 0) { $failed += $module }
}
if ($failed.Count -ne 0) {
  throw ('isolated Python failures: ' + ($failed -join ', '))
}
```

Expected: failure 0。

- [ ] **Step 7: VS Code全テストを実行する**

Run:

```powershell
Set-Location vscode/extension
npm.cmd ci
npm.cmd test
npm.cmd run test:extension-host
Set-Location ../..
```

Expected: compile、unit tests、Extension Hostすべて成功。

- [ ] **Step 8: fixture smokeとpackage contractを実行する**

Run:

```powershell
python -m unittest tests.test_fixture_cli_smoke tests.test_vc6_fixture_build_e2e -v
python -m unittest tests.test_contract_registry tests.test_distribution_build_script -v
```

Expected: 全件成功。

- [ ] **Step 9: Windows配布物を作成し、blocked成果物を実機確認する**

Run on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_distribution.ps1
```

生成された同梱CLIでfixture workspaceに対してblocked runを実行し、次を確認する。

```powershell
& .\dist\unit-test-runner.exe --json run-tests --workspace $workspace --run
if ($LASTEXITCODE -ne 35) {
  throw "Expected blocked exit code 35, got $LASTEXITCODE"
}
if (-not (Test-Path "$workspace\reports\test_execution_blockers.json")) {
  throw "Missing latest blocker JSON"
}
if (-not (Test-Path "$workspace\reports\test_execution_blockers.md")) {
  throw "Missing latest blocker Markdown"
}
```

VSIXを一時VS Code profileへインストールし、command manifestとExtension Host activationを確認する。

- [ ] **Step 10: 差分品質を確認する**

Run:

```powershell
git diff --check
git status --short
```

Expected: whitespace errorなし。意図したsource、tests、docs以外の一時fileなし。

- [ ] **Step 11: 最終コミットを作成する**

```powershell
git add README.md docs vscode/extension/README.md tests/test_execution_blocker_end_to_end.py tests/test_distribution_build_script.py
git commit -m "docs: explain blocked execution reports"
```

- [ ] **Step 12: branch全体の最終reviewを行う**

確認項目:

```text
- exit code 35が維持されている
- blocked以外ではレポートを生成しない
- plan modeはlatestを触らない
- direct blockersだけを列挙する
- fallbackでblocker_countが必ず1以上
- run履歴を上書きしない
- nonblocked後にlatestだけ消える
- publication failureでtrue outcomeが変わらない
- VS Codeはvalid v1 envelopeなしに35をhandledにしない
- auto-openはrun IDごとに1回
- restorationはlatest_run、schema、hash、containmentを検証する
- Workflow simple/fullで同じ件数を表示する
- stable action codeでroutingし、localized labelで分岐しない
- schemaがwheel／exe／VSIX配布に含まれる
```

---

## Implementation Order and Review Gates

1. Task 1–3完了後: 契約、read model、正規化モデルだけをreviewする。filesystem publicationやCLI/VS Code変更はまだ含めない。
2. Task 4–5完了後: direct-cause抽出のprecisionをreviewする。背景レビュー項目が混入していないことを重点確認する。
3. Task 6–8完了後: Pythonのpublication lifecycle、exit 35、CLI成果物をreviewする。
4. Task 9–11完了後: VS Codeのstrict parsing、path/hash検証、自動表示、Workflow復元をreviewする。
5. Task 12完了後: Windows配布物と全CI相当の結果を確認してからPRをreadyにする。

## Spec Traceability

| Approved requirement | Implemented by |
|---|---|
| blocked時だけ4ファイル生成 | Tasks 6–7 |
| run履歴保持、latest同期 | Tasks 6–7 |
| 非blocked後にlatest削除 | Tasks 6–7、12 |
| planは変更しない | Tasks 7–8、12 |
| 直接原因のみ | Tasks 4–5 |
| ケースID、item ID、control、現在値、原因元、pointer | Tasks 2、5 |
| deterministic primary action | Task 3、Tasks 4–5 |
| exit 35維持 | Tasks 7–8 |
| publication failureでoutcome維持 | Tasks 6–8 |
| VS Code自動表示 | Tasks 9–10 |
| Workflow再表示 | Task 11 |
| auto-openは1runにつき1回 | Task 10 |
| 再起動時の厳格復元 | Tasks 9、11 |
| stale/latest誤表示防止 | Tasks 6、9、11 |
| CLIとVS Codeの同一成果物 | Tasks 7–10 |
| Windows配布検証 | Task 12 |

