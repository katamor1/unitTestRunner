from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping

from .field_catalog import FIELD_RULES, FieldRule

CASE_COLLECTIONS = ("test_cases", "additional_case_candidates")


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _plain_copy(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class LocatedFormItem:
    item_id: str
    subject_fingerprint: str
    case_id: str
    case_location: str
    case_index: int
    collection: str
    item_index: int
    kind: str
    locator: Mapping[str, Any]
    parent: Mapping[str, Any]
    ambiguous: bool = False

    def __post_init__(self) -> None:
        locator = _plain_copy(self.locator)
        identity = locator.get("identity")
        if isinstance(identity, dict):
            locator["identity"] = MappingProxyType(identity)
        object.__setattr__(self, "locator", MappingProxyType(locator))
        object.__setattr__(self, "parent", MappingProxyType(_plain_copy(self.parent)))

    @property
    def editable(self) -> bool:
        return not self.ambiguous


def locate_form_items(spec: Any) -> tuple[LocatedFormItem, ...]:
    located: list[LocatedFormItem] = []
    for case_location in CASE_COLLECTIONS:
        cases = _case_collection(spec, case_location)
        for case_index, case in enumerate(cases):
            if not isinstance(case, Mapping):
                continue
            case_id = str(case.get("test_case_id") or "")
            for collection, rule in FIELD_RULES.items():
                parents = case.get(collection) or []
                if not isinstance(parents, list):
                    continue
                for item_index, parent in enumerate(parents):
                    if not isinstance(parent, Mapping):
                        continue
                    located.append(
                        _located_item(
                            case_id=case_id,
                            case_location=case_location,
                            case_index=case_index,
                            rule=rule,
                            item_index=item_index,
                            parent=parent,
                        )
                    )

    counts = Counter(item.item_id for item in located)
    return tuple(
        replace(item, ambiguous=counts[item.item_id] != 1)
        for item in located
    )


def _located_item(
    *,
    case_id: str,
    case_location: str,
    case_index: int,
    rule: FieldRule,
    item_index: int,
    parent: Mapping[str, Any],
) -> LocatedFormItem:
    locator = {
        "case_id": case_id,
        "collection": rule.collection,
        "kind": rule.kind,
        "identity": {
            name: copy.deepcopy(parent.get(name))
            for name in rule.locator_fields
        },
    }
    return LocatedFormItem(
        item_id="item-" + digest(locator),
        subject_fingerprint=digest(parent),
        case_id=case_id,
        case_location=case_location,
        case_index=case_index,
        collection=rule.collection,
        item_index=item_index,
        kind=rule.kind,
        locator=locator,
        parent=parent,
    )


def _case_collection(spec: Any, name: str) -> list[Any]:
    if hasattr(spec, name):
        value = getattr(spec, name)
    elif isinstance(spec, Mapping):
        data = spec.get("data")
        source = data if isinstance(data, Mapping) else spec
        value = source.get(name)
    else:
        value = None
    return value if isinstance(value, list) else []


def _plain_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_copy(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_plain_copy(item) for item in value)
    return copy.deepcopy(value)
