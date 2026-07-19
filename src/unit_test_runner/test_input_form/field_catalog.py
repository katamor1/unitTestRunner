from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping


Parent = Mapping[str, Any]
RequiredPredicate = Callable[[Parent], bool]
LabelBuilder = Callable[[Parent], str]


def _always(_parent: Parent) -> bool:
    return True


def _never(_parent: Parent) -> bool:
    return False


def _stub_value_required(parent: Parent) -> bool:
    return str(parent.get("setup_kind") or "") not in {
        "call_count_observation",
        "argument_capture",
    }


def _explicit_dependency_mode(parent: Parent) -> bool:
    return str(parent.get("mode") or "inherit") in {"real", "stub"}


def _text(value: Any, fallback: str) -> str:
    normalized = str(value or "").strip()
    return normalized or fallback


def _input_label(parent: Parent) -> str:
    target = _text(parent.get("target_name"), "不明な入力")
    target_kind = _text(parent.get("target_kind"), "入力")
    return f"{target_kind}: {target}"


def _state_label(parent: Parent) -> str:
    variable = _text(parent.get("variable_name"), "不明な状態")
    scope = _text(parent.get("scope"), "state")
    return f"状態 {variable} ({scope})"


def _stub_label(parent: Parent) -> str:
    stub = _text(parent.get("stub_name"), "不明なスタブ")
    setup_kind = _text(parent.get("setup_kind"), "設定")
    return f"スタブ {stub}: {setup_kind}"


def _expected_label(parent: Parent) -> str:
    target = _text(parent.get("target_name"), "結果")
    observation = _text(parent.get("observation_kind"), "期待値")
    return f"期待値 {target}: {observation}"


def _precondition_label(parent: Parent) -> str:
    return f"前提条件: {_text(parent.get('source'), '由来不明')}"


def _execution_label(parent: Parent) -> str:
    order = parent.get("order")
    order_text = str(order) if isinstance(order, int) and not isinstance(order, bool) else "?"
    return f"実行手順 {order_text}: {_text(parent.get('action'), '操作不明')}"


def _dependency_label(parent: Parent) -> str:
    return f"依存関係: {_text(parent.get('callee'), '呼び出し先不明')}"


@dataclass(frozen=True)
class ControlRule:
    name: str
    control_kind: str
    required_when: RequiredPredicate
    enum_values: frozenset[str] = frozenset()


@dataclass(frozen=True)
class FieldRule:
    collection: str
    kind: str
    locator_fields: tuple[str, ...]
    controls: tuple[ControlRule, ...]
    label_builder: LabelBuilder
    execution_control_name: str | None = None
    execution_required_when: RequiredPredicate = _never


def _control(
    name: str,
    control_kind: str,
    *,
    required_when: RequiredPredicate = _never,
    enum_values: frozenset[str] = frozenset(),
) -> ControlRule:
    return ControlRule(
        name=name,
        control_kind=control_kind,
        required_when=required_when,
        enum_values=enum_values,
    )


_FIELD_RULES = {
    "input_assignments": FieldRule(
        collection="input_assignments",
        kind="input_assignment",
        locator_fields=("target_kind", "target_name", "source_candidate_id"),
        controls=(
            _control("value_expression", "c_expression", required_when=_always),
        ),
        label_builder=_input_label,
        execution_control_name="value_expression",
        execution_required_when=_always,
    ),
    "state_setups": FieldRule(
        collection="state_setups",
        kind="state_setup",
        locator_fields=("scope", "variable_name", "source_candidate_id"),
        controls=(
            _control("value_expression", "c_expression", required_when=_always),
            _control("setup_method_hint", "multiline"),
        ),
        label_builder=_state_label,
        execution_control_name="value_expression",
        execution_required_when=_always,
    ),
    "stub_setups": FieldRule(
        collection="stub_setups",
        kind="stub_setup",
        locator_fields=(
            "stub_name",
            "setup_kind",
            "related_call_id",
            "source_candidate_id",
        ),
        controls=(
            _control(
                "value_expression",
                "c_expression",
                required_when=_stub_value_required,
            ),
            _control("call_behavior", "multiline"),
        ),
        label_builder=_stub_label,
        execution_control_name="value_expression",
        execution_required_when=_stub_value_required,
    ),
    "expected_observations": FieldRule(
        collection="expected_observations",
        kind="expected_observation",
        locator_fields=("observation_kind", "target_name", "source"),
        controls=(
            _control("expected_expression", "c_expression", required_when=_always),
            _control("note", "multiline"),
        ),
        label_builder=_expected_label,
        execution_control_name="expected_expression",
        execution_required_when=_always,
    ),
    "preconditions": FieldRule(
        collection="preconditions",
        kind="precondition",
        locator_fields=("source",),
        controls=(
            _control("description", "multiline", required_when=_always),
        ),
        label_builder=_precondition_label,
    ),
    "execution_steps": FieldRule(
        collection="execution_steps",
        kind="execution_step",
        locator_fields=("order", "action"),
        controls=(
            _control("detail", "multiline", required_when=_always),
        ),
        label_builder=_execution_label,
    ),
    "dependency_overrides": FieldRule(
        collection="dependency_overrides",
        kind="dependency_override",
        locator_fields=("callee",),
        controls=(
            _control(
                "mode",
                "enum",
                required_when=_always,
                enum_values=frozenset({"inherit", "real", "stub"}),
            ),
            _control(
                "rationale",
                "multiline",
                required_when=_explicit_dependency_mode,
            ),
        ),
        label_builder=_dependency_label,
    ),
}

FIELD_RULES: Mapping[str, FieldRule] = MappingProxyType(_FIELD_RULES)
ALL_EDITABLE_CONTROL_NAMES = frozenset(
    control.name
    for rule in FIELD_RULES.values()
    for control in rule.controls
)


def required_for_confirmation(
    rule: FieldRule,
    control: ControlRule,
    parent: Parent,
) -> bool:
    if control not in rule.controls:
        raise ValueError(
            f"Control {control.name!r} does not belong to {rule.collection!r}."
        )
    return bool(control.required_when(parent))


def execution_value_required(rule: FieldRule, parent: Parent) -> bool:
    return bool(
        rule.execution_control_name is not None
        and rule.execution_required_when(parent)
    )


def label_for_parent(rule: FieldRule, parent: Parent) -> str:
    label = str(rule.label_builder(parent)).strip()
    if not label:
        raise ValueError(f"Field rule {rule.collection!r} produced an empty label.")
    return label


def editable_control_names(rule: FieldRule) -> frozenset[str]:
    return frozenset(control.name for control in rule.controls)
