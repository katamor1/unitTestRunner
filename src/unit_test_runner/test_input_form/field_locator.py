from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from .field_catalog import FIELD_RULES, FieldRule
from .models import TestInputFormError


CASE_LOCATIONS = ("test_cases", "additional_case_candidates")


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class LocatedFormItem:
    case_id: str
    case_location: str
    case_index: int
    collection: str
    item_index: int
    rule: FieldRule
    parent: Mapping[str, Any]
    locator: Mapping[str, Any]
    item_id: str
    subject_fingerprint: str
    ambiguous: bool = False
    editable: bool = True

    @property
    def kind(self) -> str:
        return self.rule.kind


def _spec_data(spec: Any) -> Any:
    if isinstance(spec, Mapping):
        data = spec.get("data")
        if isinstance(data, Mapping) and any(
            location in data for location in CASE_LOCATIONS
        ):
            return data
        return spec
    return spec


def _cases_for_location(spec: Any, location: str) -> list[Any]:
    data = _spec_data(spec)
    if isinstance(data, Mapping):
        value = data.get(location, [])
    else:
        value = getattr(data, location, [])
    if not isinstance(value, list):
        raise TestInputFormError(
            "test_input_form_invalid",
            f"Canonical TestSpec {location} must be an array.",
        )
    return value


def _parent_items(case: Mapping[str, Any], rule: FieldRule) -> list[Any]:
    value = case.get(rule.collection, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise TestInputFormError(
            "test_input_form_invalid",
            f"Test case field {rule.collection} must be an array.",
        )
    return value


def _locator(
    case_id: str,
    rule: FieldRule,
    parent: Mapping[str, Any],
) -> Mapping[str, Any]:
    identity = {
        name: _json_value(parent.get(name))
        for name in rule.locator_fields
    }
    return MappingProxyType(
        {
            "case_id": case_id,
            "collection": rule.collection,
            "kind": rule.kind,
            "identity": MappingProxyType(identity),
        }
    )


def locate_form_items(spec: Any) -> tuple[LocatedFormItem, ...]:
    located: list[LocatedFormItem] = []
    for case_location in CASE_LOCATIONS:
        for case_index, raw_case in enumerate(_cases_for_location(spec, case_location)):
            if not isinstance(raw_case, Mapping):
                raise TestInputFormError(
                    "test_input_form_invalid",
                    f"Canonical TestSpec {case_location}[{case_index}] must be an object.",
                )
            case_id = str(raw_case.get("test_case_id") or "").strip()
            if not case_id:
                raise TestInputFormError(
                    "test_input_form_invalid",
                    f"Canonical TestSpec {case_location}[{case_index}] has no test_case_id.",
                )
            for rule in FIELD_RULES.values():
                for item_index, raw_parent in enumerate(_parent_items(raw_case, rule)):
                    if not isinstance(raw_parent, Mapping):
                        raise TestInputFormError(
                            "test_input_form_invalid",
                            f"{case_id}.{rule.collection}[{item_index}] must be an object.",
                        )
                    locator = _locator(case_id, rule, raw_parent)
                    located.append(
                        LocatedFormItem(
                            case_id=case_id,
                            case_location=case_location,
                            case_index=case_index,
                            collection=rule.collection,
                            item_index=item_index,
                            rule=rule,
                            parent=raw_parent,
                            locator=locator,
                            item_id="item-" + digest(locator),
                            subject_fingerprint=digest(raw_parent),
                        )
                    )

    counts = Counter(item.item_id for item in located)
    return tuple(
        replace(item, ambiguous=True, editable=False)
        if counts[item.item_id] > 1
        else item
        for item in located
    )
