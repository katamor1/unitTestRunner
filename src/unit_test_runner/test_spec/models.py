from __future__ import annotations

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


def _required_exact_string(value: Any, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact string.")
    if not value:
        raise ValueError(f"{field_name} must not be empty.")
    if "\x00" in value:
        raise ValueError(f"{field_name} must not contain NUL.")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field_name} must be strict UTF-8.") from error
    return value


def _required_exact_integer(value: Any, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an exact integer.")
    return value


def materialize_test_spec_containers(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: materialize_test_spec_containers(child)
            for key, child in dict.items(value)
        }
    if isinstance(value, list):
        return [
            materialize_test_spec_containers(child)
            for child in list.__iter__(value)
        ]
    return value


def _invalid_unresolved_case_id_list_indices(value: Any) -> tuple[int, ...]:
    if not isinstance(value, dict):
        return ()
    unresolved_items = dict.get(value, "unresolved_items")
    if not isinstance(unresolved_items, list):
        return ()
    missing = object()
    invalid_indices: list[int] = []
    for index, item in enumerate(list.__iter__(unresolved_items)):
        if not isinstance(item, dict):
            continue
        related_case_ids = dict.get(item, "related_test_case_ids", missing)
        if related_case_ids is not missing and type(related_case_ids) is not list:
            invalid_indices.append(index)
    return tuple(invalid_indices)


def require_exact_unresolved_case_id_lists(value: Any) -> None:
    if _invalid_unresolved_case_id_list_indices(value):
        raise TypeError("related_test_case_ids must be an exact list.")


def _required_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be an object.")
    return value


def _required_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list.")
    return value


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
        if validate:
            raw_violations = validate_payload(ArtifactKind.TEST_SPEC, payload)
            if raw_violations:
                raise TestSpecContractError(raw_violations)
        try:
            raw_data = (
                dict.get(payload, "data")
                if isinstance(payload, dict)
                else payload.get("data")
            )
            require_exact_unresolved_case_id_lists(raw_data)
            payload = materialize_test_spec_containers(payload)
            data = _required_dict(payload.get("data"), "test_spec data")
            source = _required_dict(data.get("source"), "test_spec source")
            function = _required_dict(
                data.get("function"),
                "test_spec function",
            )
            generated_from = _required_list(
                data.get("generated_from"),
                "test_spec generated_from",
            )
            review_item_ids = _required_list(
                data.get("review_item_ids"),
                "test_spec review_item_ids",
            )
            producer = _required_dict(
                payload.get("producer"),
                "test_spec producer",
            )
            extensions = _required_dict(
                payload["extensions"] if "extensions" in payload else {},
                "test_spec extensions",
            )
            spec = cls(
                spec_id=_required_exact_string(data["spec_id"], "test_spec spec_id"),
                revision=_required_exact_integer(
                    data["revision"],
                    "test_spec revision",
                ),
                source=SourceReference(
                    path=_required_exact_string(
                        source["path"],
                        "test_spec source path",
                    ),
                    sha256=_required_exact_string(
                        source["sha256"],
                        "test_spec source sha256",
                    ),
                ),
                function=FunctionReference(
                    function_id=_required_exact_string(
                        function["function_id"],
                        "test_spec function_id",
                    ),
                    name=_required_exact_string(
                        function["name"],
                        "test_spec function name",
                    ),
                    signature_sha256=_required_exact_string(
                        function["signature_sha256"],
                        "test_spec function signature sha256",
                    ),
                ),
                generated_from=[
                    ArtifactReference(
                        artifact_kind=_required_exact_string(
                            _required_dict(
                                item,
                                "test_spec generated artifact",
                            )["artifact_kind"],
                            "test_spec generated artifact kind",
                        ),
                        path=_required_exact_string(
                            item["path"],
                            "test_spec generated artifact path",
                        ),
                        sha256=_required_exact_string(
                            item["sha256"],
                            "test_spec generated artifact sha256",
                        ),
                    )
                    for item in generated_from
                ],
                generation_policy=_required_dict(
                    data.get("generation_policy"),
                    "test_spec generation_policy",
                ),
                test_cases=_required_list(
                    data.get("test_cases"),
                    "test_spec test_cases",
                ),
                additional_case_candidates=_required_list(
                    data.get("additional_case_candidates"),
                    "test_spec additional_case_candidates",
                ),
                coverage_summary=_required_dict(
                    data.get("coverage_summary"),
                    "test_spec coverage_summary",
                ),
                unresolved_items=_required_list(
                    data.get("unresolved_items"),
                    "test_spec unresolved_items",
                ),
                warnings=_required_list(
                    data.get("warnings"),
                    "test_spec warnings",
                ),
                review_item_ids=[
                    _required_exact_string(item, "test_spec review_item_id")
                    for item in review_item_ids
                ],
                schema_version=_required_exact_string(
                    payload.get("schema_version"),
                    "test_spec schema_version",
                ),
                producer=producer,
                extensions=extensions,
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
        require_exact_unresolved_case_id_lists(
            {"unresolved_items": self.unresolved_items}
        )
        return self._to_payload_unchecked()

    def _to_payload_unchecked(self) -> dict[str, Any]:
        producer = materialize_test_spec_containers(self.producer)
        if type(producer) is dict and not producer:
            producer = {
                "name": "unit-test-runner",
                "version": __version__,
                "commit": current_producer_commit(),
            }
        generated_from = materialize_test_spec_containers(
            self.generated_from
        )
        return materialize_test_spec_containers(
            {
                "artifact_kind": ArtifactKind.TEST_SPEC.value,
                "schema_version": self.schema_version,
                "producer": producer,
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
                    "generated_from": [
                        item.to_dict() for item in generated_from
                    ],
                    "generation_policy": self.generation_policy,
                    "test_cases": self.test_cases,
                    "additional_case_candidates": (
                        self.additional_case_candidates
                    ),
                    "coverage_summary": self.coverage_summary,
                    "unresolved_items": self.unresolved_items,
                    "warnings": self.warnings,
                    "review_item_ids": self.review_item_ids,
                },
                "extensions": self.extensions,
            }
        )

    def with_revision(self, revision: int) -> "TestSpec":
        return replace(self, revision=revision)


def validate_test_spec(
    spec: TestSpec,
    *,
    current_context: CurrentArtifactContext | None = None,
) -> tuple[ContractViolation, ...]:
    invalid_indices = _invalid_unresolved_case_id_list_indices(
        {"unresolved_items": spec.unresolved_items}
    )
    payload = spec._to_payload_unchecked()
    violations = list(validate_payload(ArtifactKind.TEST_SPEC, payload))
    violations.extend(
        [
            ContractViolation(
                "invalid_unresolved_case_references",
                (
                    f"$.data.unresolved_items[{index}]"
                    ".related_test_case_ids"
                ),
                "related_test_case_ids must be an exact list when present.",
                "blocking",
            )
            for index in invalid_indices
        ]
    )
    if current_context is not None:
        violations.extend(_freshness_violations(spec, current_context))
    return _deduplicate(violations)


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
    expected_generated_from = materialize_test_spec_containers(
        context.generated_from
    )
    actual_generated_from = materialize_test_spec_containers(
        spec.generated_from
    )
    expected_references = {
        (item.artifact_kind, item.path, item.sha256)
        for item in expected_generated_from
    }
    actual_references = {
        (item.artifact_kind, item.path, item.sha256)
        for item in actual_generated_from
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
