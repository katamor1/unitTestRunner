from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .kinds import ArtifactKind
from .models import ContractViolation, LoadedArtifact


def validate_artifact(
    kind: ArtifactKind,
    payload: Mapping[str, Any],
) -> tuple[ContractViolation, ...]:
    return _validate(f"{kind.value}.schema.json", payload)


def validate_cli_envelope(
    payload: Mapping[str, Any],
) -> tuple[ContractViolation, ...]:
    return _validate("cli_envelope.schema.json", payload)


def load_artifact(
    path: Path | str,
    *,
    expected_kind: ArtifactKind,
) -> LoadedArtifact:
    resolved = Path(path)
    try:
        decoded = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return LoadedArtifact(
            kind=expected_kind,
            payload={},
            violations=(
                ContractViolation(
                    code="invalid_json",
                    json_path="$",
                    message=f"Cannot read {resolved}: {error}",
                ),
            ),
        )
    if not isinstance(decoded, dict):
        return LoadedArtifact(
            kind=expected_kind,
            payload={},
            violations=(
                ContractViolation(
                    code="invalid_root",
                    json_path="$",
                    message="Artifact root must be an object.",
                ),
            ),
        )
    violations = validate_artifact(expected_kind, decoded)
    return LoadedArtifact(
        kind=expected_kind,
        payload=decoded,
        violations=violations,
    )


def _validate(
    schema_name: str,
    payload: Mapping[str, Any],
) -> tuple[ContractViolation, ...]:
    validator = _validator(schema_name)
    return tuple(
        ContractViolation(
            code=_error_code(error.validator),
            json_path=_json_path(error.absolute_path),
            message=error.message,
        )
        for error in sorted(
            validator.iter_errors(dict(payload)),
            key=lambda item: (list(item.absolute_path), item.message),
        )
    )


@lru_cache(maxsize=None)
def _validator(schema_name: str) -> Draft202012Validator:
    documents = _schema_documents()
    return Draft202012Validator(
        documents[schema_name],
        registry=_schema_registry(),
    )


@lru_cache(maxsize=1)
def _schema_documents() -> dict[str, dict[str, Any]]:
    root = resources.files("unit_test_runner.schemas")
    return {
        item.name: json.loads(item.read_text(encoding="utf-8"))
        for item in root.iterdir()
        if item.name.endswith(".json")
    }


@lru_cache(maxsize=1)
def _schema_registry() -> Registry:
    registry = Registry()
    for schema in _schema_documents().values():
        registry = registry.with_resource(
            str(schema["$id"]),
            Resource.from_contents(schema),
        )
    return registry


def _error_code(validator: str) -> str:
    return {
        "additionalProperties": "unknown_property",
        "const": "invalid_value",
        "enum": "invalid_enum",
        "format": "invalid_format",
        "minLength": "invalid_value",
        "minProperties": "required_property",
        "pattern": "invalid_format",
        "required": "required_property",
        "type": "invalid_type",
    }.get(validator, "schema_error")


def _json_path(parts) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path
