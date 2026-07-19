from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Any

Parent = Mapping[str, Any]
Requirement = bool | Callable[[Parent], bool]


@dataclass(frozen=True)
class ControlRule:
    name: str
    control_kind: str
    required: Requirement
    enum_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class FieldRule:
    collection: str
    kind: str
    locator_fields: tuple[str, ...]
    controls: tuple[ControlRule, ...]
    execution_required: Callable[[Parent], bool]
    label_builder: Callable[[Parent], str]


def _always(_parent: Parent) -> bool:
    return True


def _never(_parent: Parent) -> bool:
    return False


def _stub_value_required(parent: Parent) -> bool:
    return parent.get("setup_kind") not in {
        "call_count_observation",
        "argument_capture",
    }


def _explicit_dependency_mode(parent: Parent) -> bool:
    return parent.get("mode") in {"real", "stub"}


def _text(parent: Parent, name: str, fallback: str) -> str:
    value = str(parent.get(name) or "").strip()
    return value or fallback


def _input_label(parent: Parent) -> str:
    return f"引数 {_text(parent, 'target_name', 'unknown')}"


def _state_label(parent: Parent) -> str:
    return f"状態 {_text(parent, 'variable_name', 'unknown')}"


def _stub_label(parent: Parent) -> str:
    name = _text(parent, "stub_name", "unknown")
    kind = _text(parent, "setup_kind", "setup")
    return f"スタブ {name} ({kind})"


def _expected_label(parent: Parent) -> str:
    target = _text(
        parent,
        "target_name",
        _text(parent, "observation_kind", "observation"),
    )
    return f"期待値 {target}"


def _precondition_label(parent: Parent) -> str:
    return f"前提条件 {_text(parent, 'source', 'unknown')}"


def _execution_label(parent: Parent) -> str:
    order = parent.get("order")
    order_text = str(order) if order is not None else "?"
    return f"実行手順 {order_text}: {_text(parent, 'action', 'unknown')}"


def _dependency_label(parent: Parent) -> str:
    return f"依存関係 {_text(parent, 'callee', 'unknown')}"


FIELD_RULES = MappingProxyType(
    {
        "input_assignments": FieldRule(
            collection="input_assignments",
            kind="input_assignment",
            locator_fields=("target_kind", "target_name", "source_candidate_id"),
            controls=(ControlRule("value_expression", "c_expression", True),),
            execution_required=_always,
            label_builder=_input_label,
        ),
        "state_setups": FieldRule(
            collection="state_setups",
            kind="state_setup",
            locator_fields=("scope", "variable_name", "source_candidate_id"),
            controls=(
                ControlRule("value_expression", "c_expression", True),
                ControlRule("setup_method_hint", "multiline_text", False),
            ),
            execution_required=_always,
            label_builder=_state_label,
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
                ControlRule("value_expression", "c_expression", _stub_value_required),
                ControlRule("call_behavior", "multiline_text", False),
            ),
            execution_required=_stub_value_required,
            label_builder=_stub_label,
        ),
        "expected_observations": FieldRule(
            collection="expected_observations",
            kind="expected_observation",
            locator_fields=("observation_kind", "target_name", "source"),
            controls=(
                ControlRule("expected_expression", "c_expression", True),
                ControlRule("note", "multiline_text", False),
            ),
            execution_required=_always,
            label_builder=_expected_label,
        ),
        "preconditions": FieldRule(
            collection="preconditions",
            kind="precondition",
            locator_fields=("source",),
            controls=(ControlRule("description", "multiline_text", True),),
            execution_required=_never,
            label_builder=_precondition_label,
        ),
        "execution_steps": FieldRule(
            collection="execution_steps",
            kind="execution_step",
            locator_fields=("order", "action"),
            controls=(ControlRule("detail", "multiline_text", True),),
            execution_required=_never,
            label_builder=_execution_label,
        ),
        "dependency_overrides": FieldRule(
            collection="dependency_overrides",
            kind="dependency_override",
            locator_fields=("callee",),
            controls=(
                ControlRule(
                    "mode",
                    "enum",
                    True,
                    enum_values=("inherit", "real", "stub"),
                ),
                ControlRule("rationale", "multiline_text", _explicit_dependency_mode),
            ),
            execution_required=_never,
            label_builder=_dependency_label,
        ),
    }
)


def required_for_confirmation(
    rule: FieldRule,
    control: ControlRule,
    parent: Parent,
) -> bool:
    requirement = control.required
    return bool(requirement(parent) if callable(requirement) else requirement)


def execution_value_required(rule: FieldRule, parent: Parent) -> bool:
    return bool(rule.execution_required(parent))


def label_for_parent(rule: FieldRule, parent: Parent) -> str:
    return str(rule.label_builder(parent))


def editable_control_names(rule: FieldRule) -> frozenset[str]:
    return frozenset(control.name for control in rule.controls)
