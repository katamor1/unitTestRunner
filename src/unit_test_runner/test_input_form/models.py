from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping
import re

from .field_catalog import ALL_EDITABLE_CONTROL_NAMES


FORM_SCHEMA_VERSION = "1.0"
MAX_CHANGES = 1000
MAX_CHANGED_LEAVES = 16
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ITEM_ID_RE = re.compile(r"^item-[0-9a-f]{64}$")
FORM_ERROR_CODES = frozenset(
    {
        "test_input_form_invalid",
        "test_input_revision_conflict",
        "test_input_subject_conflict",
        "test_input_validation",
        "stale_test_spec",
    }
)


class TestInputFormError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        if code not in FORM_ERROR_CODES:
            raise ValueError(f"Unknown test input form error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message


def _invalid(message: str) -> TestInputFormError:
    return TestInputFormError("test_input_form_invalid", message)


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], path: str) -> None:
    actual = frozenset(value)
    missing = expected - actual
    unknown = actual - expected
    details: list[str] = []
    if missing:
        details.append("missing properties: " + ", ".join(sorted(missing)))
    if unknown:
        details.append("unknown properties: " + ", ".join(sorted(unknown)))
    if details:
        raise _invalid(f"{path} has " + "; ".join(details) + ".")


def _require_string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise _invalid(f"{path} must be a string.")
    if not allow_empty and not value:
        raise _invalid(f"{path} must not be empty.")
    return value


def _require_nonnegative(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer.")
    return value


def _copy_string_mapping(value: Mapping[str, Any]) -> Mapping[str, str]:
    return MappingProxyType({str(key): str(item) for key, item in value.items()})


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

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Form control name must not be empty.")
        if self.control_kind not in {"c_expression", "multiline", "enum"}:
            raise ValueError(f"Unsupported form control kind: {self.control_kind}")
        if type(self.required_for_confirmation) is not bool:
            raise ValueError("required_for_confirmation must be a boolean.")
        object.__setattr__(self, "suggestions", tuple(self.suggestions))
        object.__setattr__(self, "enum_values", tuple(self.enum_values))

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
        if not _ITEM_ID_RE.fullmatch(self.item_id):
            raise ValueError("Form item_id must be item- followed by a lowercase SHA-256.")
        if not _SHA256_RE.fullmatch(self.subject_fingerprint):
            raise ValueError("Form subject_fingerprint must be a lowercase SHA-256.")
        if not self.kind or not self.label:
            raise ValueError("Form item kind and label must not be empty.")
        for name, value in (
            ("confirmed", self.confirmed),
            ("blocking", self.blocking),
            ("editable", self.editable),
        ):
            if type(value) is not bool:
                raise ValueError(f"{name} must be a boolean.")
        controls = tuple(self.controls)
        if not controls:
            raise ValueError("Form items require at least one control.")
        names = [control.name for control in controls]
        if len(names) != len(set(names)):
            raise ValueError("Form item control names must be unique.")
        warnings = tuple(_copy_string_mapping(item) for item in self.warnings)
        object.__setattr__(self, "controls", controls)
        object.__setattr__(self, "warnings", warnings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "subject_fingerprint": self.subject_fingerprint,
            "kind": self.kind,
            "label": self.label,
            "confirmed": self.confirmed,
            "blocking": self.blocking,
            "editable": self.editable,
            "controls": [control.to_dict() for control in self.controls],
            "warnings": [dict(item) for item in self.warnings],
        }


@dataclass(frozen=True)
class FormCase:
    case_id: str
    location: str
    promotion_eligible: bool
    items: tuple[FormItem, ...]

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("Form case_id must not be empty.")
        if self.location not in {"test_cases", "additional_case_candidates"}:
            raise ValueError(f"Unsupported form case location: {self.location}")
        if type(self.promotion_eligible) is not bool:
            raise ValueError("promotion_eligible must be a boolean.")
        object.__setattr__(self, "items", tuple(self.items))

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

    def __post_init__(self) -> None:
        for name in (
            "attention_count",
            "unresolved_count",
            "unconfirmed_count",
            "execution_blocking_count",
            "warning_count",
        ):
            _require_nonnegative(getattr(self, name), name)

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

    def __post_init__(self) -> None:
        if self.schema_version != FORM_SCHEMA_VERSION:
            raise ValueError(f"Unsupported form schema version: {self.schema_version}")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("Form revision must be a positive integer.")
        if not _SHA256_RE.fullmatch(self.spec_sha256):
            raise ValueError("Form spec_sha256 must be a lowercase SHA-256.")
        if not self.function_name:
            raise ValueError("Form function_name must not be empty.")
        if self.cases is not None:
            object.__setattr__(self, "cases", tuple(self.cases))

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "spec_sha256": self.spec_sha256,
            "function": {"name": self.function_name},
            "summary": self.summary.to_dict(),
        }
        if self.cases is not None:
            value["cases"] = [case.to_dict() for case in self.cases]
        return value


@dataclass(frozen=True)
class TestInputChange:
    item_id: str
    subject_fingerprint: str
    values: Mapping[str, str]
    confirmed: bool

    def __post_init__(self) -> None:
        if not _ITEM_ID_RE.fullmatch(self.item_id):
            raise _invalid("change.item_id must be item- followed by a lowercase SHA-256.")
        if not _SHA256_RE.fullmatch(self.subject_fingerprint):
            raise _invalid("change.subject_fingerprint must be a lowercase SHA-256.")
        if type(self.confirmed) is not bool:
            raise _invalid("change.confirmed must be a boolean.")
        if not isinstance(self.values, Mapping):
            raise _invalid("change.values must be an object.")
        if len(self.values) > MAX_CHANGED_LEAVES:
            raise _invalid(f"change.values may contain at most {MAX_CHANGED_LEAVES} properties.")
        copied: dict[str, str] = {}
        for name, value in self.values.items():
            if not isinstance(name, str) or name not in ALL_EDITABLE_CONTROL_NAMES:
                raise _invalid(f"change.values contains an unknown editable control: {name!r}.")
            if not isinstance(value, str):
                raise _invalid(f"change.values.{name} must be a string.")
            copied[name] = value
        object.__setattr__(self, "values", MappingProxyType(copied))

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

    def __post_init__(self) -> None:
        if self.schema_version != FORM_SCHEMA_VERSION:
            raise _invalid(
                f"schema_version must be {FORM_SCHEMA_VERSION!r}; received {self.schema_version!r}."
            )
        changes = tuple(self.changes)
        if len(changes) > MAX_CHANGES:
            raise _invalid(f"changes may contain at most {MAX_CHANGES} items.")
        item_ids = [change.item_id for change in changes]
        if len(item_ids) != len(set(item_ids)):
            raise _invalid("changes contains a duplicate item_id.")
        object.__setattr__(self, "changes", changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "changes": [change.to_dict() for change in self.changes],
        }


def parse_test_input_change_request(value: Any) -> TestInputChangeRequest:
    if type(value) is not dict:
        raise _invalid("Test input change request must be an object.")
    _exact_keys(value, frozenset({"schema_version", "changes"}), "request")
    version = _require_string(value["schema_version"], "request.schema_version")
    if version != FORM_SCHEMA_VERSION:
        raise _invalid(
            f"request.schema_version must be {FORM_SCHEMA_VERSION!r}; received {version!r}."
        )
    changes_value = value["changes"]
    if type(changes_value) is not list:
        raise _invalid("request.changes must be an array.")
    if len(changes_value) > MAX_CHANGES:
        raise _invalid(f"request.changes may contain at most {MAX_CHANGES} items.")

    changes: list[TestInputChange] = []
    seen: set[str] = set()
    expected_change_keys = frozenset(
        {"item_id", "subject_fingerprint", "values", "confirmed"}
    )
    for index, raw_change in enumerate(changes_value):
        path = f"request.changes[{index}]"
        if type(raw_change) is not dict:
            raise _invalid(f"{path} must be an object.")
        _exact_keys(raw_change, expected_change_keys, path)
        item_id = _require_string(raw_change["item_id"], f"{path}.item_id")
        if item_id in seen:
            raise _invalid(f"request.changes contains a duplicate item_id: {item_id}.")
        seen.add(item_id)
        fingerprint = _require_string(
            raw_change["subject_fingerprint"],
            f"{path}.subject_fingerprint",
        )
        values = raw_change["values"]
        if type(values) is not dict:
            raise _invalid(f"{path}.values must be an object.")
        if len(values) > MAX_CHANGED_LEAVES:
            raise _invalid(
                f"{path}.values may contain at most {MAX_CHANGED_LEAVES} properties."
            )
        confirmed = raw_change["confirmed"]
        if type(confirmed) is not bool:
            raise _invalid(f"{path}.confirmed must be a boolean.")
        changes.append(
            TestInputChange(
                item_id=item_id,
                subject_fingerprint=fingerprint,
                values=values,
                confirmed=confirmed,
            )
        )
    return TestInputChangeRequest(tuple(changes), schema_version=version)
