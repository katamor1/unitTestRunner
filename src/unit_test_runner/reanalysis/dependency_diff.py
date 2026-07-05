from __future__ import annotations

from typing import Any

from .reanalysis_models import DependencyChange


def compare_dependencies(
    previous_global: dict[str, Any],
    current_global: dict[str, Any],
    previous_call: dict[str, Any],
    current_call: dict[str, Any],
    affected_test_case_ids: list[str],
) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    changes.extend(_compare_global_access(previous_global, current_global, affected_test_case_ids))
    changes.extend(_compare_named_items("call", previous_call.get("calls", []), current_call.get("calls", []), affected_test_case_ids))
    changes.extend(
        _compare_named_items(
            "stub_candidate",
            previous_call.get("stub_candidates", []),
            current_call.get("stub_candidates", []),
            affected_test_case_ids,
        )
    )
    changes.extend(
        _compare_named_items(
            "side_effect",
            previous_call.get("side_effect_candidates", []),
            current_call.get("side_effect_candidates", []),
            affected_test_case_ids,
            name_key="call_name",
        )
    )
    return changes


def _compare_global_access(previous: dict[str, Any], current: dict[str, Any], affected: list[str]) -> list[DependencyChange]:
    old = {_global_key(item): item for item in previous.get("global_accesses", [])}
    new = {_global_key(item): item for item in current.get("global_accesses", [])}
    changes: list[DependencyChange] = []
    for key in sorted(new.keys() - old.keys()):
        item = new[key]
        changes.append(
            DependencyChange(
                _global_change_kind(item, "added"),
                item.get("access_path") or item.get("name") or key,
                None,
                item.get("access_kind"),
                "medium",
                affected,
                "Review state setup or expected global observations.",
            )
        )
    for key in sorted(old.keys() - new.keys()):
        item = old[key]
        changes.append(
            DependencyChange(
                _global_change_kind(item, "removed"),
                item.get("access_path") or item.get("name") or key,
                item.get("access_kind"),
                None,
                "medium",
                affected,
                "Remove or review obsolete state setup or expected global observations.",
            )
        )
    return changes


def _compare_named_items(
    prefix: str,
    previous_items: list[dict[str, Any]],
    current_items: list[dict[str, Any]],
    affected: list[str],
    name_key: str = "name",
) -> list[DependencyChange]:
    old = {_item_name(item, name_key): item for item in previous_items if _item_name(item, name_key)}
    new = {_item_name(item, name_key): item for item in current_items if _item_name(item, name_key)}
    changes: list[DependencyChange] = []
    for name in sorted(new.keys() - old.keys()):
        item = new[name]
        changes.append(
            DependencyChange(
                f"{prefix}_added",
                name,
                None,
                item.get("target_kind") or item.get("kind"),
                "medium",
                affected,
                f"Review {prefix.replace('_', ' ')} setup.",
            )
        )
    for name in sorted(old.keys() - new.keys()):
        item = old[name]
        changes.append(
            DependencyChange(
                f"{prefix}_removed",
                name,
                item.get("target_kind") or item.get("kind"),
                None,
                "medium",
                affected,
                f"Remove obsolete {prefix.replace('_', ' ')} setup.",
            )
        )
    return changes


def _global_key(item: dict[str, Any]) -> str:
    return "|".join(str(item.get(key) or "") for key in ("name", "access_kind", "access_path"))


def _global_change_kind(item: dict[str, Any], suffix: str) -> str:
    access_kind = str(item.get("access_kind") or "")
    if "write" in access_kind:
        return f"global_write_{suffix}"
    return f"global_read_{suffix}"


def _item_name(item: dict[str, Any], name_key: str) -> str:
    return str(item.get(name_key) or item.get("name") or item.get("call_name") or "")
