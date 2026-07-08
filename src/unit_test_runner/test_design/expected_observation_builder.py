from __future__ import annotations

import re

from .test_case_models import ExpectedObservation, TestCaseDesignWarning, UnresolvedTestDesignItem


def build_expected_observations(
    test_case_id: str,
    coverage_item: dict,
    global_access: dict | None = None,
    function_signature: dict | None = None,
) -> tuple[list[ExpectedObservation], list[TestCaseDesignWarning], list[UnresolvedTestDesignItem]]:
    coverage_id = coverage_item.get("coverage_id", "")
    observations = [
        ExpectedObservation(
            observation_kind="return_value",
            target_name="return",
            expected_expression="TBD_EXPECTED_RETURN",
            source="placeholder",
            review_required=True,
            confidence="low",
            note="期待戻り値を関数仕様に照らして確認してください。",
        ),
        ExpectedObservation(
            observation_kind="coverage_target",
            target_name=coverage_id,
            expected_expression="covered_by_design",
            source="coverage_design",
            review_required=True,
            confidence=coverage_item.get("confidence", "medium"),
            note=None,
        ),
    ]
    warnings = [
        TestCaseDesignWarning(
            "expected_result_not_determined",
            "期待戻り値はレビュー用プレースホルダです。",
            related_test_case_id=test_case_id,
            related_coverage_id=coverage_id,
        )
    ]
    unresolved = [
        UnresolvedTestDesignItem(
            item_id=f"UNRES_{test_case_id}_RET",
            item_kind="expected_return_unknown",
            description="期待戻り値を仕様から確認してください。",
            related_test_case_ids=[test_case_id],
            reason="静的解析では最終的な期待結果を確定できません。",
            suggested_action="関数仕様とソース上の挙動を確認してください。",
        )
    ]
    extra_observations, extra_warnings, extra_unresolved = _side_effect_observations(test_case_id, coverage_id, global_access or {}, function_signature or {})
    observations.extend(extra_observations)
    warnings.extend(extra_warnings)
    unresolved.extend(extra_unresolved)
    return observations, warnings, unresolved


def _side_effect_observations(
    test_case_id: str,
    coverage_id: str,
    global_access: dict,
    function_signature: dict,
) -> tuple[list[ExpectedObservation], list[TestCaseDesignWarning], list[UnresolvedTestDesignItem]]:
    observations: list[ExpectedObservation] = []
    warnings: list[TestCaseDesignWarning] = []
    unresolved: list[UnresolvedTestDesignItem] = []

    for access in _updated_accessible_globals(global_access):
        name = access.get("name")
        if not name:
            continue
        suffix = _placeholder_suffix(name)
        observations.append(
            ExpectedObservation(
                observation_kind="global_value",
                target_name=name,
                expected_expression=f"TBD_EXPECTED_GLOBAL_{suffix}",
                source="global_access",
                review_required=True,
                confidence=access.get("confidence", "medium"),
                note="期待グローバル値を関数仕様に照らして確認してください。",
            )
        )
        warnings.append(
            TestCaseDesignWarning(
                "expected_global_not_determined",
                f"{name} の期待グローバル値はレビュー用プレースホルダです。",
                related_test_case_id=test_case_id,
                related_coverage_id=coverage_id,
            )
        )
        unresolved.append(
            UnresolvedTestDesignItem(
                item_id=f"UNRES_{test_case_id}_GLOBAL_{suffix}",
                item_kind="expected_global_unknown",
                description=f"{name} の期待グローバル値を仕様から確認してください。",
                related_test_case_ids=[test_case_id],
                reason="静的解析ではグローバル書き込みを検出できますが、最終的な期待値は確定できません。",
                suggested_action="関数仕様を確認し、生成されたグローバル期待値を置き換えてください。",
            )
        )

    for parameter in _updated_char_buffers(global_access, function_signature):
        name = parameter.get("name")
        if not name:
            continue
        suffix = _placeholder_suffix(name)
        observations.append(
            ExpectedObservation(
                observation_kind="char_array_string",
                target_name=name,
                expected_expression=f"TBD_EXPECTED_STRING_{suffix}",
                source="parameter_access",
                review_required=True,
                confidence=parameter.get("confidence", "medium"),
                note="期待文字列を関数仕様に照らして確認してください。",
            )
        )
        warnings.append(
            TestCaseDesignWarning(
                "expected_char_array_string_not_determined",
                f"文字配列 {name} の期待文字列はレビュー用プレースホルダです。",
                related_test_case_id=test_case_id,
                related_coverage_id=coverage_id,
            )
        )
        unresolved.append(
            UnresolvedTestDesignItem(
                item_id=f"UNRES_{test_case_id}_STRING_{suffix}",
                item_kind="expected_char_array_string_unknown",
                description=f"文字配列 {name} の期待文字列を仕様から確認してください。",
                related_test_case_ids=[test_case_id],
                reason="静的解析では書き込み可能な文字バッファを検出できますが、最終的な期待文字列は確定できません。",
                suggested_action="関数仕様を確認し、生成された文字列期待値を置き換えてください。",
            )
        )

    return observations, warnings, unresolved


def _updated_accessible_globals(global_access: dict) -> list[dict]:
    declarations = {item.get("name"): item for item in global_access.get("file_scope_declarations", [])}
    result: list[dict] = []
    seen: set[str] = set()
    for access in global_access.get("global_accesses", []):
        name = access.get("name")
        if not name or name in seen:
            continue
        if access.get("access_kind") not in {"write", "read_write"}:
            continue
        declaration = access.get("related_declaration") or declarations.get(name) or {}
        if _is_static_file_scope(access, declaration):
            continue
        if declaration.get("is_array") or declaration.get("is_struct_like"):
            continue
        seen.add(name)
        result.append(access)
    return result


def _is_static_file_scope(access: dict, declaration: dict) -> bool:
    scope = access.get("scope") or declaration.get("scope")
    storage_class = declaration.get("storage_class")
    return scope == "file_static" or storage_class == "static"


def _updated_char_buffers(global_access: dict, function_signature: dict) -> list[dict]:
    written_parameters = {
        access.get("parameter_name")
        for access in global_access.get("parameter_accesses", [])
        if "write" in str(access.get("access_kind", ""))
    }
    result: list[dict] = []
    for parameter in function_signature.get("function", {}).get("parameters", []):
        name = parameter.get("name")
        if not name or name not in written_parameters:
            continue
        type_info = parameter.get("type", {})
        if not _is_char_buffer_type(type_info):
            continue
        result.append({"name": name, "confidence": type_info.get("confidence", parameter.get("confidence", "medium"))})
    return result


def _is_char_buffer_type(type_info: dict) -> bool:
    base_type = str(type_info.get("base_type") or type_info.get("normalized") or type_info.get("raw") or "").strip()
    compact_base = re.sub(r"\s+", " ", base_type)
    if compact_base not in {"char", "signed char", "unsigned char"}:
        return False
    return bool(type_info.get("is_array") or int(type_info.get("pointer_level") or 0) > 0)


def _placeholder_suffix(name: str) -> str:
    suffix = re.sub(r"\W+", "_", str(name)).strip("_").upper()
    return suffix or "VALUE"
