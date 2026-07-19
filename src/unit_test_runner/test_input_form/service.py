from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from unit_test_runner.cli.artifacts import ProducedArtifact, build_produced_artifact
from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import (
    CurrentArtifactContext,
    TestSpec,
    TestSpecContractError,
    StaleRevisionError,
    TestSpecSnapshot,
    TestSpecViewDurabilityError,
    build_current_artifact_context,
    export_test_spec_snapshot_views,
    load_test_spec_snapshot,
    save_test_spec_snapshot,
    validate_test_spec,
)

from .field_catalog import (
    FIELD_RULES,
    editable_control_names,
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
    TestInputChange,
    TestInputChangeRequest,
    TestInputFormDocument,
    TestInputFormError,
)
from .suggestions import (
    SuggestionIndex,
    build_suggestion_index,
    suggestions_for_item,
    type_hint_for_item,
)
from .validation import (
    c_expression_warnings,
    is_unresolved,
    normalize_c_expression,
    normalize_enum,
    normalize_multiline,
)


@dataclass(frozen=True)
class CurrentFormSnapshot:
    workspace: Path
    path: Path
    snapshot: TestSpecSnapshot
    context: CurrentArtifactContext


@dataclass(frozen=True)
class TestInputApplyResult:
    revision: int
    spec_sha256: str
    updated_item_count: int
    confirmed_item_count: int
    promoted_case_ids: tuple[str, ...]
    demoted_case_ids: tuple[str, ...]
    summary: FormSummary
    views_written: bool
    warnings: tuple[Mapping[str, str], ...]
    artifacts: tuple[ProducedArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "spec_sha256": self.spec_sha256,
            "updated_item_count": self.updated_item_count,
            "confirmed_item_count": self.confirmed_item_count,
            "promoted_case_ids": list(self.promoted_case_ids),
            "demoted_case_ids": list(self.demoted_case_ids),
            "summary": self.summary.to_dict(),
            "views_written": self.views_written,
            "warnings": [dict(item) for item in self.warnings],
        }


@dataclass(frozen=True)
class _ResolvedChange:
    change: TestInputChange
    located: LocatedFormItem
    normalized_values: Mapping[str, str]


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


def _build_form_document(
    current: CurrentFormSnapshot,
    *,
    summary_only: bool,
) -> TestInputFormDocument:
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


def build_test_input_form(
    workspace: Path | str,
    summary_only: bool = False,
) -> TestInputFormDocument:
    if type(summary_only) is not bool:
        raise TestInputFormError(
            "test_input_form_invalid",
            "summary_only must be a boolean.",
        )
    return _build_form_document(
        load_current_form_snapshot(workspace),
        summary_only=summary_only,
    )


def _normalizer(control_rule, value: str) -> str:
    if control_rule.control_kind == "c_expression":
        return normalize_c_expression(value)
    if control_rule.control_kind == "multiline":
        return normalize_multiline(value)
    if control_rule.control_kind == "enum":
        return normalize_enum(value, control_rule.enum_values)
    raise TestInputFormError(
        "test_input_validation",
        f"Unsupported control kind: {control_rule.control_kind}",
    )


def _resolve_changes(
    current: CurrentFormSnapshot,
    request: TestInputChangeRequest,
) -> tuple[_ResolvedChange, ...]:
    by_id: dict[str, list[LocatedFormItem]] = defaultdict(list)
    for item in locate_form_items(current.snapshot.spec):
        by_id[item.item_id].append(item)
    resolved: list[_ResolvedChange] = []
    for change in request.changes:
        matches = by_id.get(change.item_id, [])
        if len(matches) != 1:
            raise TestInputFormError(
                "test_input_validation",
                f"Unknown or ambiguous test input item: {change.item_id}",
            )
        item = matches[0]
        if item.ambiguous or not item.editable:
            raise TestInputFormError(
                "test_input_validation",
                f"Test input item is not editable: {change.item_id}",
            )
        if item.subject_fingerprint != change.subject_fingerprint:
            raise TestInputFormError(
                "test_input_subject_conflict",
                f"Test input item changed after the form was loaded: {change.item_id}",
            )
        if type(item.parent.get("review_required")) is not bool:
            raise TestInputFormError(
                "test_input_validation",
                f"Test input item has invalid review_required authority: {change.item_id}",
            )
        allowed = editable_control_names(item.rule)
        unknown = set(change.values) - set(allowed)
        if unknown:
            raise TestInputFormError(
                "test_input_validation",
                f"Test input item contains noneditable fields: {', '.join(sorted(unknown))}",
            )
        controls = {control.name: control for control in item.rule.controls}
        normalized = {
            name: _normalizer(controls[name], value)
            for name, value in change.values.items()
        }
        resolved.append(_ResolvedChange(change, item, normalized))
    return tuple(resolved)


def _parent_at(spec: TestSpec, item: LocatedFormItem) -> dict[str, Any]:
    cases = (
        spec.test_cases
        if item.case_location == "test_cases"
        else spec.additional_case_candidates
    )
    try:
        case = cases[item.case_index]
        parents = case[item.collection]
        parent = parents[item.item_index]
    except (IndexError, KeyError, TypeError) as error:
        raise TestInputFormError(
            "test_input_subject_conflict",
            f"Test input item location changed: {item.item_id}",
        ) from error
    if not isinstance(parent, dict):
        raise TestInputFormError(
            "test_input_subject_conflict",
            f"Test input item is no longer an object: {item.item_id}",
        )
    return parent


def _validate_confirmed_parent(item: LocatedFormItem, parent: Mapping[str, Any]) -> None:
    for control in item.rule.controls:
        if not required_for_confirmation(item.rule, control, parent):
            continue
        if is_unresolved(parent.get(control.name)):
            raise TestInputFormError(
                "test_input_validation",
                f"Confirmed item {item.item_id} still has an unresolved {control.name} value.",
            )


def _case_execution_parents(case: Mapping[str, Any]):
    for rule in FIELD_RULES.values():
        if rule.execution_control_name is None:
            continue
        parents = case.get(rule.collection, [])
        if not isinstance(parents, list):
            continue
        for parent in parents:
            if isinstance(parent, Mapping) and execution_value_required(rule, parent):
                yield rule, parent


def _case_ready(case: Mapping[str, Any]) -> bool:
    execution = tuple(_case_execution_parents(case))
    return bool(execution) and all(
        parent.get("review_required") is False
        and not is_unresolved(parent.get(rule.execution_control_name or ""))
        for rule, parent in execution
    )


def _ensure_unique_case_ids(spec: TestSpec) -> None:
    ids = [
        str(case.get("test_case_id") or "")
        for case in spec.test_cases + spec.additional_case_candidates
    ]
    if not all(ids) or len(ids) != len(set(ids)):
        raise TestInputFormError(
            "test_input_validation",
            "Test case IDs must be nonempty and unique before form changes can be saved.",
        )


def _preeligible_candidate_ids(spec: TestSpec) -> frozenset[str]:
    located = locate_form_items(spec)
    by_case: dict[tuple[str, int], list[LocatedFormItem]] = defaultdict(list)
    for item in located:
        by_case[(item.case_location, item.case_index)].append(item)
    result: set[str] = set()
    for index, case in enumerate(spec.additional_case_candidates):
        if _promotion_eligible(
            spec,
            "additional_case_candidates",
            index,
            tuple(by_case.get(("additional_case_candidates", index), ())),
        ):
            result.add(str(case.get("test_case_id") or ""))
    return frozenset(result)


def _reclassify_cases(
    spec: TestSpec,
    *,
    preeligible_candidate_ids: frozenset[str],
    touched_executable_execution_case_ids: frozenset[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    _ensure_unique_case_ids(spec)
    promoted = [
        case
        for case in spec.additional_case_candidates
        if str(case.get("test_case_id") or "") in preeligible_candidate_ids
        and _case_ready(case)
    ]
    promoted_ids = tuple(str(case["test_case_id"]) for case in promoted)
    remaining_candidates = [
        case
        for case in spec.additional_case_candidates
        if str(case.get("test_case_id") or "") not in set(promoted_ids)
    ]
    demoted = [
        case
        for case in spec.test_cases
        if str(case.get("test_case_id") or "")
        in touched_executable_execution_case_ids
        and not _case_ready(case)
    ]
    demoted_ids = tuple(str(case["test_case_id"]) for case in demoted)
    remaining_executable = [
        case
        for case in spec.test_cases
        if str(case.get("test_case_id") or "") not in set(demoted_ids)
    ]
    spec.test_cases = remaining_executable + promoted
    spec.additional_case_candidates = remaining_candidates + demoted
    _ensure_unique_case_ids(spec)
    return promoted_ids, demoted_ids


def _validate_candidate(spec: TestSpec, current: CurrentFormSnapshot) -> None:
    violations = validate_test_spec(spec, current_context=current.context)
    if violations:
        raise TestInputFormError(
            "test_input_validation",
            str(TestSpecContractError(violations)),
        )


def apply_test_input_form(
    workspace: Path | str,
    request: TestInputChangeRequest,
    expected_revision: int,
) -> TestInputApplyResult:
    if not isinstance(request, TestInputChangeRequest):
        raise TestInputFormError(
            "test_input_form_invalid",
            "request must be a parsed TestInputChangeRequest.",
        )
    if not request.changes:
        raise TestInputFormError(
            "test_input_validation",
            "At least one test input change is required.",
        )
    current = load_current_form_snapshot(workspace)
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision != current.snapshot.spec.revision
    ):
        raise TestInputFormError(
            "test_input_revision_conflict",
            f"Expected TestSpec revision {expected_revision!r}; current revision is {current.snapshot.spec.revision}.",
        )
    resolved = _resolve_changes(current, request)
    preeligible = _preeligible_candidate_ids(current.snapshot.spec)
    candidate = TestSpec.from_payload(current.snapshot.spec.to_payload())
    touched_executable_execution_ids: set[str] = set()
    changed_parents: list[tuple[_ResolvedChange, dict[str, Any]]] = []
    for resolved_change in resolved:
        parent = _parent_at(candidate, resolved_change.located)
        for name, value in resolved_change.normalized_values.items():
            parent[name] = value
        parent["review_required"] = not resolved_change.change.confirmed
        changed_parents.append((resolved_change, parent))
        if (
            resolved_change.located.case_location == "test_cases"
            and execution_value_required(
                resolved_change.located.rule,
                parent,
            )
        ):
            touched_executable_execution_ids.add(resolved_change.located.case_id)
    for resolved_change, parent in changed_parents:
        if resolved_change.change.confirmed:
            _validate_confirmed_parent(resolved_change.located, parent)
    promoted_ids, demoted_ids = _reclassify_cases(
        candidate,
        preeligible_candidate_ids=preeligible,
        touched_executable_execution_case_ids=frozenset(
            touched_executable_execution_ids
        ),
    )
    _validate_candidate(candidate, current)
    try:
        saved, canonical_artifact = save_test_spec_snapshot(
            current.path,
            candidate,
            expected_revision=expected_revision,
            current_context=current.context,
        )
    except StaleRevisionError as error:
        raise TestInputFormError("test_input_revision_conflict", str(error)) from error
    except TestSpecContractError as error:
        raise TestInputFormError("test_input_validation", str(error)) from error

    warnings: list[dict[str, str]] = []
    artifacts: list[ProducedArtifact] = [canonical_artifact]
    views_written = False
    try:
        view_export = export_test_spec_snapshot_views(
            saved,
            current.path.parent,
            canonical_path=current.path,
        )
        views_written = view_export.written
        if view_export.written:
            artifacts.extend(
                (
                    build_produced_artifact(
                        current.workspace,
                        view_export.markdown,
                        kind="test_spec_markdown",
                    ),
                    build_produced_artifact(
                        current.workspace,
                        view_export.csv,
                        kind="test_spec_csv",
                    ),
                )
            )
        else:
            warnings.append(
                _warning(
                    "test_spec_view_export_failed",
                    "Canonical TestSpec was saved, but its generated views were superseded before export.",
                )
            )
    except (OSError, ValueError, TestSpecViewDurabilityError) as error:
        warnings.append(
            _warning(
                "test_spec_view_export_failed",
                f"Canonical TestSpec was saved, but generated view export failed: {error}",
            )
        )

    saved_current = CurrentFormSnapshot(
        workspace=current.workspace,
        path=current.path,
        snapshot=saved,
        context=current.context,
    )
    latest = _build_form_document(saved_current, summary_only=True)
    return TestInputApplyResult(
        revision=saved.spec.revision,
        spec_sha256=saved.sha256,
        updated_item_count=len(resolved),
        confirmed_item_count=sum(
            1 for item in resolved if item.change.confirmed
        ),
        promoted_case_ids=promoted_ids,
        demoted_case_ids=demoted_ids,
        summary=latest.summary,
        views_written=views_written,
        warnings=tuple(warnings),
        artifacts=tuple(artifacts),
    )
