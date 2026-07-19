from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import (
    CurrentArtifactContext,
    TestSpec,
    TestSpecContractError,
    TestSpecSnapshot,
    build_current_artifact_context,
    load_test_spec_snapshot,
    validate_test_spec,
)

from .field_catalog import (
    execution_value_required,
    label_for_parent,
    required_for_confirmation,
)
from .field_locator import LocatedFormItem, locate_form_items
from .models import (
    FormCase,
    FormControl,
    FormItem,
    FormSummary,
    TestInputFormDocument,
    TestInputFormError,
)
from .suggestions import (
    SuggestionIndex,
    build_suggestion_index,
    suggestions_for_item,
    type_hint_for_item,
)
from .validation import c_expression_warnings, is_unresolved


@dataclass(frozen=True)
class CurrentFormSnapshot:
    workspace: Path
    path: Path
    snapshot: TestSpecSnapshot
    context: CurrentArtifactContext


@dataclass(frozen=True)
class _BuiltItem:
    located: LocatedFormItem
    form: FormItem
    unresolved: bool


def _warning(code: str, message: str, *, severity: str = "warning") -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _contract_error_code(error: TestSpecContractError) -> str:
    return (
        "stale_test_spec"
        if any(item.code.startswith("stale_") for item in error.violations)
        else "test_input_form_invalid"
    )


def load_current_form_snapshot(workspace: Path | str) -> CurrentFormSnapshot:
    root = Path(workspace).resolve()
    path = root / "reports" / "test_spec.json"
    if not path.is_file():
        raise TestInputFormError(
            "test_input_form_invalid",
            f"Canonical TestSpec was not found: {path}",
        )
    try:
        snapshot = load_test_spec_snapshot(path, mode=ContractMode.STRICT)
    except TestSpecContractError as error:
        raise TestInputFormError(_contract_error_code(error), str(error)) from error
    try:
        context = build_current_artifact_context(root, snapshot.spec)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise TestInputFormError("stale_test_spec", str(error)) from error
    violations = validate_test_spec(snapshot.spec, current_context=context)
    if violations:
        error = TestSpecContractError(violations)
        raise TestInputFormError(_contract_error_code(error), str(error)) from error
    return CurrentFormSnapshot(root, path, snapshot, context)


def _review_state(parent: Mapping[str, Any]) -> tuple[bool, bool, tuple[dict[str, str], ...]]:
    review_required = parent.get("review_required")
    if type(review_required) is not bool:
        return (
            False,
            False,
            (
                _warning(
                    "invalid_review_required",
                    "This item has no boolean review_required value and is read-only until reanalysis repairs it.",
                    severity="error",
                ),
            ),
        )
    return review_required is False, True, ()


def _build_control(
    item: LocatedFormItem,
    control_rule,
    suggestion_index: SuggestionIndex,
) -> tuple[FormControl, tuple[dict[str, str], ...]]:
    suggestions = suggestions_for_item(suggestion_index, item, control_rule.name)
    required = required_for_confirmation(item.rule, control_rule, item.parent)
    value = item.parent.get(control_rule.name)
    warnings: tuple[dict[str, str], ...] = ()
    if control_rule.control_kind == "c_expression":
        warnings = c_expression_warnings(
            value,
            type_hint_for_item(suggestion_index, item),
            suggestions,
        )
    return (
        FormControl(
            name=control_rule.name,
            control_kind=control_rule.control_kind,
            required_for_confirmation=required,
            value=value,
            suggestions=suggestions,
            enum_values=tuple(sorted(control_rule.enum_values)),
        ),
        warnings,
    )


def _build_form_item(
    item: LocatedFormItem,
    suggestion_index: SuggestionIndex,
) -> _BuiltItem | None:
    confirmed, valid_review, review_warnings = _review_state(item.parent)
    controls: list[FormControl] = []
    warnings: list[dict[str, str]] = list(review_warnings)
    for control_rule in item.rule.controls:
        control, control_warnings = _build_control(item, control_rule, suggestion_index)
        controls.append(control)
        warnings.extend(control_warnings)
    required_unresolved = any(
        control.required_for_confirmation and is_unresolved(control.value)
        for control in controls
    )
    review_required = item.parent.get("review_required") is True
    if not (review_required or required_unresolved or not valid_review):
        return None
    if item.ambiguous:
        warnings.append(
            _warning(
                "ambiguous_item",
                "More than one object has the same semantic locator; reanalysis is required before saving.",
                severity="error",
            )
        )
    unique_warnings: dict[tuple[str, str], dict[str, str]] = {}
    for warning in warnings:
        unique_warnings.setdefault((warning["code"], warning["message"]), warning)
    return _BuiltItem(
        located=item,
        form=FormItem(
            item_id=item.item_id,
            subject_fingerprint=item.subject_fingerprint,
            kind=item.kind,
            label=label_for_parent(item.rule, item.parent),
            confirmed=confirmed,
            blocking=execution_value_required(item.rule, item.parent),
            editable=item.editable and valid_review,
            controls=tuple(controls),
            warnings=tuple(unique_warnings.values()),
        ),
        unresolved=required_unresolved,
    )


def _case_lists(spec: TestSpec) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return spec.test_cases, spec.additional_case_candidates


def _promotion_eligible(
    spec: TestSpec,
    location: str,
    case_index: int,
    case_items: tuple[LocatedFormItem, ...],
) -> bool:
    if location != "additional_case_candidates":
        return False
    candidates = spec.additional_case_candidates
    if case_index >= len(candidates):
        return False
    case = candidates[case_index]
    case_id = str(case.get("test_case_id") or "")
    executable_ids = {
        str(item.get("test_case_id") or "")
        for item in spec.test_cases
    }
    if not case_id or case_id in executable_ids:
        return False
    execution_items = tuple(
        item
        for item in case_items
        if execution_value_required(item.rule, item.parent)
    )
    if not execution_items:
        return False
    return any(
        is_unresolved(item.parent.get(item.rule.execution_control_name or ""))
        or item.parent.get("review_required") is not False
        for item in execution_items
    )


def _summary(items: tuple[_BuiltItem, ...]) -> FormSummary:
    unresolved_ids = {
        item.form.item_id
        for item in items
        if item.unresolved
    }
    unconfirmed_ids = {
        item.form.item_id
        for item in items
        if not item.form.confirmed
    }
    blocking_ids = {
        item.form.item_id
        for item in items
        if item.form.blocking and item.unresolved
    }
    warning_ids = {
        item.form.item_id
        for item in items
        if item.form.warnings
    }
    attention_ids = unresolved_ids | unconfirmed_ids | blocking_ids | warning_ids
    return FormSummary(
        attention_count=len(attention_ids),
        unresolved_count=len(unresolved_ids),
        unconfirmed_count=len(unconfirmed_ids),
        execution_blocking_count=len(blocking_ids),
        warning_count=len(warning_ids),
    )


def build_test_input_form(
    workspace: Path | str,
    summary_only: bool = False,
) -> TestInputFormDocument:
    if type(summary_only) is not bool:
        raise TestInputFormError(
            "test_input_form_invalid",
            "summary_only must be a boolean.",
        )
    current = load_current_form_snapshot(workspace)
    try:
        suggestion_index = build_suggestion_index(current.workspace, current.snapshot.spec)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise TestInputFormError("stale_test_spec", str(error)) from error
    located = locate_form_items(current.snapshot.spec)
    all_case_items: dict[tuple[str, int], list[LocatedFormItem]] = defaultdict(list)
    visible_by_case: dict[tuple[str, int], list[_BuiltItem]] = defaultdict(list)
    built_items: list[_BuiltItem] = []
    for item in located:
        key = (item.case_location, item.case_index)
        all_case_items[key].append(item)
        built = _build_form_item(item, suggestion_index)
        if built is not None:
            visible_by_case[key].append(built)
            built_items.append(built)

    cases: list[FormCase] = []
    if not summary_only:
        for location, collection in zip(
            ("test_cases", "additional_case_candidates"),
            _case_lists(current.snapshot.spec),
            strict=True,
        ):
            for case_index, case in enumerate(collection):
                key = (location, case_index)
                visible = visible_by_case.get(key, [])
                if not visible:
                    continue
                cases.append(
                    FormCase(
                        case_id=str(case.get("test_case_id") or ""),
                        location=location,
                        promotion_eligible=_promotion_eligible(
                            current.snapshot.spec,
                            location,
                            case_index,
                            tuple(all_case_items.get(key, ())),
                        ),
                        items=tuple(item.form for item in visible),
                    )
                )
    return TestInputFormDocument(
        revision=current.snapshot.spec.revision,
        spec_sha256=current.snapshot.sha256,
        function_name=current.snapshot.spec.function.name,
        summary=_summary(tuple(built_items)),
        cases=None if summary_only else tuple(cases),
    )
