from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from unit_test_runner.contracts import ArtifactKind, ContractViolation, validate_artifact


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
    project: str | None = None
    configuration: str | None = None


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
    project: str | None = None
    configuration: str | None = None
    schema_version: str = "1.0.0"

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        validate: bool = True,
    ) -> "TestSpec":
        if validate:
            contract_violations = validate_artifact(ArtifactKind.TEST_SPEC, payload)
            if contract_violations:
                raise TestSpecContractError(contract_violations)
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
        subject = payload.get("subject")
        if not isinstance(subject, Mapping):
            raise TestSpecContractError(
                (
                    ContractViolation(
                        "required_property",
                        "$.subject",
                        "test_spec subject must be an object.",
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
                project=_required_subject_text(subject, "project"),
                configuration=_required_subject_text(subject, "configuration"),
                schema_version=str(payload.get("schema_version") or ""),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise TestSpecContractError(
                (ContractViolation("schema_error", "$.data", str(error)),)
            ) from error
        subject_violations = _incoming_subject_violations(subject, spec)
        if subject_violations:
            raise TestSpecContractError(subject_violations)
        if validate:
            violations = validate_test_spec(spec)
            if violations:
                raise TestSpecContractError(violations)
        return spec

    def to_payload(self) -> dict[str, Any]:
        if self.schema_version != "1.0.0":
            raise TestSpecContractError(
                (
                    ContractViolation(
                        "unsupported_version",
                        "$.schema_version",
                        "test_spec requires schema version 1.0.0.",
                        "blocking",
                    ),
                )
            )
        unbound = _unbound_subject_violations(self)
        if unbound:
            raise TestSpecContractError(unbound)
        return {
            "schema_version": self.schema_version,
            "artifact_kind": ArtifactKind.TEST_SPEC.value,
            "subject": {
                "source_path": self.source.path,
                "source_sha256": self.source.sha256,
                "function": self.function.name,
                "project": self.project,
                "configuration": self.configuration,
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
        }

    def with_revision(self, revision: int) -> "TestSpec":
        return replace(self, revision=revision)

    def with_subject_context(
        self,
        *,
        project: str,
        configuration: str,
    ) -> "TestSpec":
        return replace(self, project=project, configuration=configuration)


def validate_test_spec(
    spec: TestSpec,
    *,
    current_context: CurrentArtifactContext | None = None,
) -> tuple[ContractViolation, ...]:
    violations: list[ContractViolation] = []
    if spec.schema_version != "1.0.0":
        violations.append(
            ContractViolation(
                "unsupported_version",
                "$.schema_version",
                "test_spec requires schema version 1.0.0.",
                "blocking",
            )
        )
    unbound = _unbound_subject_violations(spec)
    if not unbound:
        violations.extend(validate_artifact(ArtifactKind.TEST_SPEC, spec.to_payload()))
    elif current_context is not None:
        violations.extend(unbound)
    if current_context is not None:
        violations.extend(_freshness_violations(spec, current_context))
    violations.extend(_semantic_violations(spec))
    return _deduplicate(violations)


def _required_subject_text(subject: Mapping[str, Any], key: str) -> str:
    value = subject.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"test_spec subject {key} must be a non-empty string.")
    return value


def _unbound_subject_violations(spec: TestSpec) -> tuple[ContractViolation, ...]:
    result: list[ContractViolation] = []
    for field_name, label in (
        ("project", "project"),
        ("configuration", "full configuration"),
    ):
        value = getattr(spec, field_name)
        if not isinstance(value, str) or not value.strip():
            result.append(
                ContractViolation(
                    "unbound_subject",
                    f"$.subject.{field_name}",
                    f"test_spec {label} must be bound before public serialization.",
                    "blocking",
                )
            )
    return tuple(result)


def _incoming_subject_violations(
    subject: Mapping[str, Any],
    spec: TestSpec,
) -> tuple[ContractViolation, ...]:
    expected = {
        "source_path": spec.source.path,
        "source_sha256": spec.source.sha256,
        "function": spec.function.name,
    }
    return tuple(
        ContractViolation(
            "subject_mismatch",
            f"$.subject.{key}",
            f"test_spec subject {key} does not match data.",
            "blocking",
        )
        for key, value in expected.items()
        if subject.get(key) != value
    )


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
    if (
        context.project is not None
        and spec.project != context.project
    ):
        violations.append(
            ContractViolation(
                "stale_project",
                "$.subject.project",
                "Test spec project does not match the selected project.",
                "blocking",
            )
        )
    if (
        context.configuration is not None
        and spec.configuration != context.configuration
    ):
        violations.append(
            ContractViolation(
                "stale_configuration",
                "$.subject.configuration",
                "Test spec configuration does not match the selected full configuration.",
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


def _semantic_violations(spec: TestSpec) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    violations.extend(
        _embedded_review_authority_violations(
            spec.generation_policy,
            "$.data.generation_policy",
        )
    )
    collections = (
        ("test_cases", spec.test_cases),
        ("additional_case_candidates", spec.additional_case_candidates),
    )
    seen_case_ids: set[str] = set()
    executable_case_ids: set[str] = set()
    coverage_map = spec.coverage_summary.get("coverage_to_test_cases", {})
    known_coverage_ids = set(coverage_map) if isinstance(coverage_map, Mapping) else set()
    known_coverage_ids.update(
        str(value)
        for value in spec.coverage_summary.get("uncovered_coverage_ids", [])
        if isinstance(value, str)
    )
    known_review_ids = set(spec.review_item_ids)
    known_dependency_ids = {
        str(value)
        for value in spec.generation_policy.get("dependency_ids", [])
        if isinstance(value, str)
    }

    for collection_name, cases in collections:
        for index, case in enumerate(cases):
            if not isinstance(case, Mapping):
                continue
            path = f"$.data.{collection_name}[{index}]"
            case_id = case.get("test_case_id")
            if isinstance(case_id, str):
                if case_id in seen_case_ids:
                    violations.append(
                        ContractViolation(
                            "duplicate_id",
                            f"{path}.test_case_id",
                            f"Duplicate test_case_id: {case_id}",
                            "blocking",
                        )
                    )
                seen_case_ids.add(case_id)
                if collection_name == "test_cases":
                    executable_case_ids.add(case_id)
            target_function = case.get("target_function")
            if target_function not in {None, spec.function.name}:
                violations.append(
                    ContractViolation(
                        "target_function_mismatch",
                        f"{path}.target_function",
                        "Test case target_function does not match the TestSpec function.",
                        "blocking",
                    )
                )
            for reference_index, reference in enumerate(case.get("coverage_links", [])):
                if not isinstance(reference, Mapping):
                    continue
                coverage_id = reference.get("coverage_id")
                if coverage_id not in known_coverage_ids:
                    violations.append(
                        ContractViolation(
                            "invalid_coverage_reference",
                            f"{path}.coverage_links[{reference_index}].coverage_id",
                            f"Unknown coverage_id: {coverage_id!r}",
                            "blocking",
                        )
                    )
            for assignment_index, assignment in enumerate(case.get("input_assignments", [])):
                if not isinstance(assignment, Mapping):
                    continue
                _append_reference_violations(
                    violations,
                    assignment,
                    f"{path}.input_assignments[{assignment_index}]",
                    known_review_ids,
                )
                if collection_name == "test_cases" and _is_unresolved_value(
                    assignment.get("value_expression")
                ):
                    violations.append(
                        ContractViolation(
                            "unresolved_executable_value",
                            f"{path}.input_assignments[{assignment_index}].value_expression",
                            "Executable test input must have a concrete value.",
                            "blocking",
                        )
                    )
            observations = case.get("expected_observations", [])
            if collection_name == "test_cases" and not observations:
                violations.append(
                    ContractViolation(
                        "missing_executable_oracle",
                        f"{path}.expected_observations",
                        "Executable test case requires at least one expected observation.",
                        "blocking",
                    )
                )
            for observation_index, observation in enumerate(observations):
                if not isinstance(observation, Mapping):
                    continue
                _append_reference_violations(
                    violations,
                    observation,
                    f"{path}.expected_observations[{observation_index}]",
                    known_review_ids,
                )
                if collection_name == "test_cases" and _is_unresolved_value(
                    observation.get("expected_expression")
                ):
                    violations.append(
                        ContractViolation(
                            "unresolved_executable_value",
                            f"{path}.expected_observations[{observation_index}].expected_expression",
                            "Executable test oracle must have a concrete value.",
                            "blocking",
                        )
                    )
            for stub_index, stub in enumerate(case.get("stub_setups", [])):
                if not isinstance(stub, Mapping):
                    continue
                dependency_id = stub.get("related_dependency_id")
                if dependency_id and dependency_id not in known_dependency_ids:
                    violations.append(
                        ContractViolation(
                            "invalid_dependency_reference",
                            f"{path}.stub_setups[{stub_index}].related_dependency_id",
                            f"Unknown dependency_id: {dependency_id!r}",
                            "blocking",
                        )
                    )
            violations.extend(_embedded_review_authority_violations(case, path))

    for index, item in enumerate(spec.unresolved_items):
        if not isinstance(item, Mapping) or item.get("severity") != "blocking":
            continue
        related = set(item.get("related_test_case_ids", []))
        if related & executable_case_ids:
            violations.append(
                ContractViolation(
                    "blocking_unresolved_executable",
                    f"$.data.unresolved_items[{index}]",
                    "Blocking unresolved item cannot reference an executable test case.",
                    "blocking",
                )
            )
    return violations


def _append_reference_violations(
    violations: list[ContractViolation],
    value: Mapping[str, Any],
    path: str,
    known_review_ids: set[str],
) -> None:
    for index, review_id in enumerate(value.get("review_item_ids", [])):
        if review_id not in known_review_ids:
            violations.append(
                ContractViolation(
                    "invalid_review_reference",
                    f"{path}.review_item_ids[{index}]",
                    f"Unknown review_item_id: {review_id!r}",
                    "blocking",
                )
            )


def _is_unresolved_value(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    normalized = value.strip().upper()
    return not normalized or normalized.startswith(("TBD", "UNKNOWN", "REVIEW_REQUIRED"))


def _embedded_review_authority_violations(
    value: Any,
    path: str,
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in {"approved", "approval", "approval_status", "review_status"}:
                violations.append(
                    ContractViolation(
                        "embedded_review_authority",
                        child_path,
                        "Approval state belongs only to review_record.",
                        "blocking",
                    )
                )
            violations.extend(_embedded_review_authority_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(
                _embedded_review_authority_violations(child, f"{path}[{index}]")
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
