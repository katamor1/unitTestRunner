from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .kinds import ArtifactKind
from .validator import validate_payload


class ConsumerContractError(ValueError):
    """Raised when an artifact cannot be exposed as consumer data."""


def normalize_consumer_data(
    payload: Mapping[str, Any],
    *,
    expected_kind: ArtifactKind,
    allow_legacy_v01: bool = False,
) -> dict[str, Any]:
    source_version = payload.get("schema_version")
    declared_kind = payload.get("artifact_kind")
    current_envelope_shape = any(
        key in payload for key in ("producer", "subject", "data", "extensions")
    )
    if (
        allow_legacy_v01
        and source_version == "0.1"
        and not current_envelope_shape
    ):
        if declared_kind not in (None, expected_kind.value):
            raise ConsumerContractError(
                f"Expected {expected_kind.value}; received {declared_kind!r}."
            )
        return copy.deepcopy(dict(payload))

    violations = validate_payload(expected_kind, payload)
    if violations:
        details = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}"
            for item in violations
        )
        raise ConsumerContractError(
            f"Invalid {expected_kind.value} consumer artifact: {details}"
        )
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ConsumerContractError(
            f"Invalid {expected_kind.value} consumer artifact: data must be an object."
        )
    return copy.deepcopy(dict(data))


def load_consumer_data(
    path: Path | str,
    *,
    expected_kind: ArtifactKind,
    allow_legacy_v01: bool = False,
) -> dict[str, Any]:
    try:
        decoded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConsumerContractError(f"Could not load consumer artifact: {error}") from error
    if not isinstance(decoded, Mapping):
        raise ConsumerContractError("Consumer artifact root must be an object.")
    return normalize_consumer_data(
        decoded,
        expected_kind=expected_kind,
        allow_legacy_v01=allow_legacy_v01,
    )
