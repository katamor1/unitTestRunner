from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from unit_test_runner import __version__
from unit_test_runner.contracts import ArtifactKind, ContractViolation, validate_payload
from unit_test_runner.execution.test_result_writer import current_producer_commit


@dataclass(frozen=True)
class SourceReference:
    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class FunctionReference:
    function_id: str
    name: str
    signature_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "function_id": self.function_id,
            "name": self.name,
            "signature_sha256": self.signature_sha256,
        }


@dataclass(frozen=True)
class ArtifactReference:
    artifact_kind: str
    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "artifact_kind": self.artifact_kind,
            "path": self.path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class CurrentArtifactContext:
    source_path: str
    source_sha256: str
    function_id: str
    function_name: str
    signature_sha256: str
    workspace_root: Path | None = None
    generated_from: tuple[ArtifactReference, ...] = ()


class TestSpecContractError(ValueError):
    def __init__(self, violations: tuple[ContractViolation, ...]) -> None:
        self.violations = violations
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}"
            for item in violations
        )
        super().__init__(detail or "Invalid test_spec contract.")


@dataclass
class TestSpec:
    spec_id: str
    revision: int
    source: SourceReference
    function: FunctionReference
    generated_from: list[ArtifactReference]
    generation_policy: dict[str, Any]
    test_cases: list[dict[str, Any]]
    additional_case_candidates: list[dict[str, Any]]
    coverage_summary: dict[str, Any]
    unresolved_items: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    review_item_ids: list[str]
    schema_version: str = "1.1.0"
    producer: dict[str, str] = field(default_factory=dict, repr=False)
    extensions: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        validate: bool = True,
    ) -> "TestSpec":
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise TestSpecContractError(
                (
                    ContractViolation(
                        "required_property",
                        "$.data",
                        "test_spec data must be an object.",
                    ),
                )
            )
        source = data.get("source")
        function = data.get("function")
        try:
            spec = cls(
                spec_id=str(data["spec_id"]),
                revision=int(data["revision"]),
                source=SourceReference(
                    path=str(source["path"]),
                    sha256=str(source["sha256"]),
                ),
                function=FunctionReference(
                    function_id=str(function["function_id"]),
                    name=str(function["name"]),
                    signature_sha256=str(function["signature_sha256"]),
                ),
                generated_from=[
                    ArtifactReference(
                        artifact_kind=str(item["artifact_kind"]),
                        path=str(item["path"]),
                        sha256=str(item["sha256"]),
                    )
                    for item in data.get("generated_from", [])
                ],
                generation_policy=copy.deepcopy(dict(data.get("generation_policy") or {})),
                test_cases=copy.deepcopy(list(data.get("test_cases") or [])),
                additional_case_candidates=copy.deepcopy(
                    list(data.get("additional_case_candidates") or [])
                ),
                coverage_summary=copy.deepcopy(dict(data.get("coverage_summary") or {})),
                unresolved_items=copy.deepcopy(list(data.get("unresolved_items") or [])),
                warnings=copy.deepcopy(list(data.get("warnings") or [])),
                review_item_ids=[str(item) for item in data.get("review_item_ids", [])],
                schema_version=str(payload.get("schema_version") or ""),
                producer=copy.deepcopy(dict(payload.get("producer") or {})),
                extensions=copy.deepcopy(dict(payload.get("extensions") or {})),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise TestSpecContractError(
                (ContractViolation("schema_error", "$.data", str(error)),)
            ) from error
        if validate:
            violations = validate_test_spec(spec)
            if violations:
                raise TestSpecContractError(violations)
        return spec

    def to_payload(self) -> dict[str, Any]:
        producer = self.producer or {
            "name": "unit-test-runner",
            "version": __version__,
            "commit": current_producer_commit(),
        }
        return {
            "artifact_kind": ArtifactKind.TEST_SPEC.value,
            "schema_version": self.schema_version,
            "producer": copy.deepcopy(producer),
            "subject": {
                "function_id": self.function.function_id,
                "source_path": self.source.path,
                "source_sha256": self.source.sha256,
            },
            "data": {
                "spec_id": self.spec_id,
                "revision": self.revision,
                "source": self.source.to_dict(),
                "function": self.function.to_dict(),
                "generated_from": [item.to_dict() for item in self.generated_from],
                "generation_policy": copy.deepcopy(self.generation_policy),
                "test_cases": copy.deepcopy(self.test_cases),
                "additional_case_candidates": copy.deepcopy(
                    self.additional_case_candidates
                ),
                "coverage_summary": copy.deepcopy(self.coverage_summary),
                "unresolved_items": copy.deepcopy(self.unresolved_items),
                "warnings": copy.deepcopy(self.warnings),
                "review_item_ids": list(self.review_item_ids),
            },
            "extensions": copy.deepcopy(self.extensions),
        }

    def with_revision(self, revision: int) -> "TestSpec":
        return replace(self, revision=revision)


_AUTHORITY_FIELDS = {
    "approved",
    "approval",
    "approval_status",
    "is_approved",
    "review_status",
    "review_decision",
}
_PLACEHOLDER_PREFIXES = ("TBD", "UNKNOWN", "UNRESOLVED", "TODO")


def validate_test_spec(
    spec: TestSpec,
    *,
    current_context: CurrentArtifactContext | None = None,
) -> tuple[ContractViolation, ...]:
    payload = spec.to_payload()
    violations = list(validate_payload(ArtifactKind.TEST_SPEC, payload))
    data = payload["data"]
    violations.extend(_authority_violations(data))
    violations.extend(_reference_violations(data))
    violations.extend(_executable_value_violations(data))
    if current_context is not None:
        violations.extend(_freshness_violations(spec, current_context))
    return _deduplicate(violations)


def _authority_violations(value: Any, path: str = "$.data") -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in _AUTHORITY_FIELDS:
                violations.append(
                    ContractViolation(
                        "embedded_review_authority",
                        child_path,
                        "Approval and review status belong only to review_decisions.json; store review-item references instead.",
                    )
                )
            violations.extend(_authority_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_authority_violations(child, f"{path}[{index}]"))
    return violations


def _reference_violations(data: Mapping[str, Any]) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    cases = [
        (collection, index, case)
        for collection in ("test_cases", "additional_case_candidates")
        for index, case in enumerate(data.get(collection) or [])
        if isinstance(case, Mapping)
    ]
    case_ids = [str(case.get("test_case_id") or "") for _, _, case in cases]
    seen: set[str] = set()
    for collection, index, case in cases:
        case_id = str(case.get("test_case_id") or "")
        if case_id and case_id in seen:
            violations.append(
                ContractViolation(
                    "duplicate_id",
                    f"$.data.{collection}[{index}].test_case_id",
                    f"Duplicate test_case_id: {case_id}",
                )
            )
        seen.add(case_id)

    summary = data.get("coverage_summary") or {}
    coverage_mapping = summary.get("coverage_to_test_cases") or {}
    coverage_ids = {str(key) for key in coverage_mapping}
    coverage_ids.update(str(item) for item in summary.get("uncovered_coverage_ids") or [])
    known_case_ids = set(case_ids)
    for coverage_id, references in coverage_mapping.items():
        for reference in references or []:
            if str(reference) not in known_case_ids:
                violations.append(
                    ContractViolation(
                        "invalid_case_reference",
                        f"$.data.coverage_summary.coverage_to_test_cases.{coverage_id}",
                        f"Unknown test_case_id reference: {reference}",
                    )
                )
    for collection, index, case in cases:
        for link_index, link in enumerate(case.get("coverage_links") or []):
            coverage_id = str(link.get("coverage_id") or "") if isinstance(link, Mapping) else ""
            if coverage_id and coverage_id not in coverage_ids:
                violations.append(
                    ContractViolation(
                        "invalid_coverage_reference",
                        f"$.data.{collection}[{index}].coverage_links[{link_index}].coverage_id",
                        f"Unknown coverage_id reference: {coverage_id}",
                    )
                )

    known_reviews = {str(item) for item in data.get("review_item_ids") or []}
    known_dependencies = {
        str(item)
        for item in (data.get("generation_policy") or {}).get("dependency_ids", [])
    }
    for json_path, key, reference in _iter_reference_values(data):
        if key in {"review_item_id", "review_item_ids"} and reference not in known_reviews:
            violations.append(
                ContractViolation(
                    "invalid_review_reference",
                    json_path,
                    f"Unknown review_item_id reference: {reference}",
                )
            )
        if key in {"dependency_id", "dependency_ids", "related_dependency_id"} and reference not in known_dependencies:
            violations.append(
                ContractViolation(
                    "invalid_dependency_reference",
                    json_path,
                    f"Unknown dependency_id reference: {reference}",
                )
            )
    return violations


def _iter_reference_values(value: Any, path: str = "$.data"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in {
                "review_item_id",
                "review_item_ids",
                "dependency_id",
                "dependency_ids",
                "related_dependency_id",
            }:
                values = child if isinstance(child, list) else [child]
                for index, item in enumerate(values):
                    if item is not None and str(item):
                        suffix = f"[{index}]" if isinstance(child, list) else ""
                        yield child_path + suffix, key, str(item)
            yield from _iter_reference_values(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_reference_values(child, f"{path}[{index}]")


def _executable_value_violations(data: Mapping[str, Any]) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    for case_index, case in enumerate(data.get("test_cases") or []):
        if not isinstance(case, Mapping):
            continue
        value_collections = (
            ("input_assignments", "value_expression"),
            ("state_setups", "value_expression"),
            ("stub_setups", "value_expression"),
            ("expected_observations", "expected_expression"),
        )
        for collection, field_name in value_collections:
            for item_index, item in enumerate(case.get(collection) or []):
                if not isinstance(item, Mapping):
                    continue
                if collection == "stub_setups" and item.get("setup_kind") in {
                    "call_count_observation",
                    "argument_capture",
                }:
                    continue
                value = item.get(field_name)
                if value is None or not str(value).strip() or str(value).upper().startswith(_PLACEHOLDER_PREFIXES):
                    violations.append(
                        ContractViolation(
                            "unresolved_executable_value",
                            f"$.data.test_cases[{case_index}].{collection}[{item_index}].{field_name}",
                            "Executable test cases require resolved values and oracles.",
                            "blocking",
                        )
                    )
    return violations


def _freshness_violations(
    spec: TestSpec,
    context: CurrentArtifactContext,
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if spec.source.path != context.source_path or spec.source.sha256 != context.source_sha256:
        violations.append(
            ContractViolation(
                "stale_source",
                "$.data.source",
                "Test spec source identity does not match the caller-supplied current source artifact.",
                "blocking",
            )
        )
    if (
        spec.function.function_id != context.function_id
        or spec.function.name != context.function_name
        or spec.function.signature_sha256 != context.signature_sha256
    ):
        violations.append(
            ContractViolation(
                "stale_signature",
                "$.data.function",
                "Test spec function identity does not match the caller-supplied current signature artifact.",
                "blocking",
            )
        )
    expected_references = {
        (item.artifact_kind, item.path, item.sha256)
        for item in context.generated_from
    }
    actual_references = {
        (item.artifact_kind, item.path, item.sha256)
        for item in spec.generated_from
    }
    if actual_references != expected_references:
        violations.append(
            ContractViolation(
                "stale_generated_from",
                "$.data.generated_from",
                "Test spec provenance references do not match the caller-supplied current artifacts.",
                "blocking",
            )
        )
    return violations


def _deduplicate(values: list[ContractViolation]) -> tuple[ContractViolation, ...]:
    result: list[ContractViolation] = []
    seen: set[tuple[str, str, str]] = set()
    for item in values:
        key = (item.code, item.json_path, item.message)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)
