from __future__ import annotations

from typing import Any

from .reanalysis_models import InterfaceChange


def compare_signatures(previous: dict[str, Any], current: dict[str, Any], affected_test_case_ids: list[str]) -> list[InterfaceChange]:
    previous_function = previous.get("function", {})
    current_function = current.get("function", {})
    changes: list[InterfaceChange] = []
    previous_return = _type_text(previous_function.get("return_type"))
    current_return = _type_text(current_function.get("return_type"))
    if previous_return != current_return:
        changes.append(
            InterfaceChange(
                "return_type_changed",
                "return",
                previous_return,
                current_return,
                "high",
                affected_test_case_ids,
                "Review expected return observations and target invocation.",
            )
        )
    previous_calling = previous_function.get("calling_convention")
    current_calling = current_function.get("calling_convention")
    if previous_calling != current_calling:
        changes.append(
            InterfaceChange(
                "calling_convention_changed",
                "calling_convention",
                str(previous_calling) if previous_calling is not None else None,
                str(current_calling) if current_calling is not None else None,
                "high",
                affected_test_case_ids,
                "Review generated harness invocation and compiler settings.",
            )
        )
    previous_parameters = list(previous_function.get("parameters", []))
    current_parameters = list(current_function.get("parameters", []))
    shared = min(len(previous_parameters), len(current_parameters))
    for index in range(shared):
        old = previous_parameters[index]
        new = current_parameters[index]
        old_type = _type_text(old.get("type"))
        new_type = _type_text(new.get("type"))
        old_name = old.get("name") or f"param_{index}"
        new_name = new.get("name") or f"param_{index}"
        if old_type != new_type:
            changes.append(
                InterfaceChange(
                    "parameter_type_changed",
                    str(old_name),
                    _parameter_text(old),
                    _parameter_text(new),
                    "high",
                    affected_test_case_ids,
                    "Review input assignments, boundary candidates, and target invocation.",
                )
            )
        elif old_name != new_name:
            changes.append(
                InterfaceChange(
                    "parameter_name_changed",
                    str(old_name),
                    _parameter_text(old),
                    _parameter_text(new),
                    "medium",
                    affected_test_case_ids,
                    "Review remapped input assignments and documentation labels.",
                )
            )
    for old in previous_parameters[shared:]:
        changes.append(
            InterfaceChange(
                "parameter_removed",
                str(old.get("name") or f"param_{old.get('index', shared)}"),
                _parameter_text(old),
                None,
                "high",
                affected_test_case_ids,
                "Remove obsolete input assignments and update invocation.",
            )
        )
    for new in current_parameters[shared:]:
        changes.append(
            InterfaceChange(
                "parameter_added",
                str(new.get("name") or f"param_{new.get('index', shared)}"),
                None,
                _parameter_text(new),
                "high",
                affected_test_case_ids,
                "Add input assignment and review all existing test cases.",
            )
        )
    return changes


def _type_text(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("normalized") or value.get("raw") or value.get("base_type")
    return str(value) if value is not None else None


def _parameter_text(parameter: dict[str, Any]) -> str:
    return str(parameter.get("raw") or " ".join(item for item in [_type_text(parameter.get("type")), parameter.get("name")] if item))
