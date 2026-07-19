from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

FORM_SCHEMA_VERSION = "1.0"
MAX_CHANGES = 1000
MAX_CHANGED_LEAVES = 16
FORM_ERROR_CODES = frozenset(
    {
        "test_input_form_invalid",
        "test_input_revision_conflict",
        "test_input_subject_conflict",
        "test_input_validation",
        "stale_test_spec",
    }
)

_ITEM_ID = re.compile(r"^item-[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEAF_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TestInputFormError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        if code not in FORM_ERROR_CODES:
            raise ValueError(f"Unsupported test input form error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message


def _invalid(message: str) -> TestInputFormError:
    return TestInputFormError("test_input_form_invalid", message)


@dataclass(frozen=True)
class FormSuggestion:
    value: str
    label: str
    source: str
    confidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "value": self.value,
            "label": self.label,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class FormControl:
    name: str
    control_kind: str
    required_for_confirmation: bool
    value: Any
    suggestions: tuple[FormSuggestion, ...] = ()
    enum_values: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "control_kind": self.control_kind,
            "required_for_confirmation": self.required_for_confirmation,
            "value": self.value,
            "suggestions": [item.to_dict() for item in self.suggestions],
            "enum_values": list(self.enum_values),
        }


@dataclass(frozen=True)
class FormItem:
    item_id: str
    subject_fingerprint: str
    kind: str
    label: str
    confirmed: bool
    blocking: bool
    editable: bool
    controls: tuple[FormControl, ...]
    warnings: tuple[Mapping[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "warnings",
            tuple(MappingProxyType(dict(item)) for item in self.warnings),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "subject_fingerprint": self.subject_fingerprint,
            "kind": self.kind,
            "label": self.label,
            "confirmed": self.confirmed,
            "blocking": self.blocking,
            "editable": self.editable,
            "controls": [item.to_dict() for item in self.controls],
            "warnings": [dict(item) for item in self.warnings],
        }


@dataclass(frozen=True)
class FormCase:
    case_id: str
    location: str
    promotion_eligible: bool
    items: tuple[FormItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "location": self.location,
            "promotion_eligible": self.promotion_eligible,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class FormSummary:
    attention_count: int
    unresolved_count: int
    unconfirmed_count: int
    execution_blocking_count: int
    warning_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "attention_count": self.attention_count,
            "unresolved_count": self.unresolved_count,
            "unconfirmed_count": self.unconfirmed_count,
            "execution_blocking_count": self.execution_blocking_count,
            "warning_count": self.warning_count,
        }


@dataclass(frozen=True)
class TestInputFormDocument:
    revision: int
    spec_sha256: str
    function_name: str
    summary: FormSummary
    cases: tuple[FormCase, ...] | None
    schema_version: str = FORM_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "spec_sha256": self.spec_sha256,
            "function": {"name": self.function_name},
            "summary": self.summary.to_dict(),
        }
        if self.cases is not None:
            value["cases"] = [item.to_dict() for item in self.cases]
        return value


@dataclass(frozen=True)
class TestInputChange:
    item_id: str
    subject_fingerprint: str
    values: Mapping[str, str | None]
    confirmed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "subject_fingerprint": self.subject_fingerprint,
            "values": dict(self.values),
            "confirmed": self.confirmed,
        }


@dataclass(frozen=True)
class TestInputChangeRequest:
    changes: tuple[TestInputChange, ...]
    schema_version: str = FORM_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "changes": [item.to_dict() for item in self.changes],
        }


def parse_test_input_change_request(value: Any) -> TestInputChangeRequest:
    root = _exact_dict(value, {"schema_version", "changes"}, "request")
    if root["schema_version"] != FORM_SCHEMA_VERSION:
        raise _invalid(
            f"Unsupported test input form schema version: {root['schema_version']!r}."
        )
    raw_changes = root["changes"]
    if type(raw_changes) is not list:
        raise _invalid("Test input form changes must be an array.")
    if len(raw_changes) > MAX_CHANGES:
        raise _invalid(f"Test input form changes exceed the limit of {MAX_CHANGES}.")

    changes: list[TestInputChange] = []
    seen_ids: set[str] = set()
    for index, raw_change in enumerate(raw_changes):
        change = _exact_dict(
            raw_change,
            {"item_id", "subject_fingerprint", "values", "confirmed"},
            f"changes[{index}]",
        )
        item_id = change["item_id"]
        fingerprint = change["subject_fingerprint"]
        if type(item_id) is not str or not _ITEM_ID.fullmatch(item_id):
            raise _invalid(f"changes[{index}].item_id is not a valid opaque item ID.")
        if item_id in seen_ids:
            raise _invalid(f"Duplicate item_id in changes: {item_id}")
        seen_ids.add(item_id)
        if type(fingerprint) is not str or not _SHA256.fullmatch(fingerprint):
            raise _invalid(
                f"changes[{index}].subject_fingerprint must be a lowercase SHA-256 digest."
            )
        raw_values = change["values"]
        if type(raw_values) is not dict:
            raise _invalid(f"changes[{index}].values must be an object.")
        if len(raw_values) > MAX_CHANGED_LEAVES:
            raise _invalid(
                f"changes[{index}].values exceeds the limit of {MAX_CHANGED_LEAVES} leaves."
            )
        normalized_values: dict[str, str | None] = {}
        for name, raw_leaf_value in raw_values.items():
            if type(name) is not str or not _LEAF_NAME.fullmatch(name):
                raise _invalid(f"changes[{index}].values contains an invalid leaf name.")
            if raw_leaf_value is not None and type(raw_leaf_value) is not str:
                raise _invalid(
                    f"changes[{index}].values.{name} must be a string or null."
                )
            normalized_values[name] = raw_leaf_value
        confirmed = change["confirmed"]
        if type(confirmed) is not bool:
            raise _invalid(f"changes[{index}].confirmed must be a boolean.")
        changes.append(
            TestInputChange(
                item_id=item_id,
                subject_fingerprint=fingerprint,
                values=normalized_values,
                confirmed=confirmed,
            )
        )
    return TestInputChangeRequest(tuple(changes))


def _exact_dict(value: Any, keys: set[str], location: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise _invalid(f"Test input form {location} must be an object.")
    actual = set(value)
    missing = keys - actual
    extra = actual - keys
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing properties: " + ", ".join(sorted(missing)))
        if extra:
            details.append("unknown properties: " + ", ".join(sorted(extra)))
        raise _invalid(f"Test input form {location} has " + "; ".join(details) + ".")
    return value
