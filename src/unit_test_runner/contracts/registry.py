from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .kinds import ArtifactKind


CURRENT_CONTRACT_VERSION = "1.0.0"
CURRENT_TEST_SPEC_VERSION = "1.1.0"
CURRENT_TASK6_CONTRACT_VERSION = "1.1.0"


@dataclass(frozen=True)
class ContractDefinition:
    kind: ArtifactKind
    current_version: str
    schema_resource: str
    compatible_source_versions: tuple[str, ...]
    semantic_validator: str


_TASK6_KINDS = (
    ArtifactKind.REVIEW_DECISIONS,
    ArtifactKind.FUNCTION_DOSSIER,
    ArtifactKind.DOSSIER_MANIFEST,
)

_DEFAULT_CONTRACTS = tuple(
    ContractDefinition(
        kind=kind,
        current_version=CURRENT_CONTRACT_VERSION,
        schema_resource=f"{kind.value}.schema.json",
        compatible_source_versions=("0.1",),
        semantic_validator=kind.value,
    )
    for kind in ArtifactKind
    if kind is not ArtifactKind.TEST_SPEC and kind not in _TASK6_KINDS
)

_TEST_SPEC_V1 = ContractDefinition(
    kind=ArtifactKind.TEST_SPEC,
    current_version="1.0.0",
    schema_resource="test_spec_v1_0.schema.json",
    compatible_source_versions=("0.1",),
    semantic_validator=ArtifactKind.TEST_SPEC.value,
)

_TEST_SPEC_CURRENT = ContractDefinition(
    kind=ArtifactKind.TEST_SPEC,
    current_version=CURRENT_TEST_SPEC_VERSION,
    schema_resource="test_spec.schema.json",
    compatible_source_versions=("1.0.0", "0.1"),
    semantic_validator=ArtifactKind.TEST_SPEC.value,
)

_TASK6_V1_CONTRACTS = tuple(
    ContractDefinition(
        kind=kind,
        current_version="1.0.0",
        schema_resource=f"{kind.value}_v1_0.schema.json",
        compatible_source_versions=("0.1",),
        semantic_validator=kind.value,
    )
    for kind in _TASK6_KINDS
)

_TASK6_CURRENT_CONTRACTS = tuple(
    ContractDefinition(
        kind=kind,
        current_version=CURRENT_TASK6_CONTRACT_VERSION,
        schema_resource=f"{kind.value}.schema.json",
        compatible_source_versions=("1.0.0", "0.1"),
        semantic_validator=kind.value,
    )
    for kind in _TASK6_KINDS
)

_CONTRACTS = _DEFAULT_CONTRACTS + _TASK6_CURRENT_CONTRACTS + (_TEST_SPEC_CURRENT,)
_CONTRACT_VERSIONS = _CONTRACTS + _TASK6_V1_CONTRACTS + (_TEST_SPEC_V1,)

_BY_KIND = {contract.kind: contract for contract in _CONTRACTS}
_BY_KIND_AND_VERSION = {
    (contract.kind, contract.current_version): contract
    for contract in _CONTRACT_VERSIONS
}


def iter_contracts() -> Iterator[ContractDefinition]:
    return iter(_CONTRACTS)


def iter_contract_versions() -> Iterator[ContractDefinition]:
    return iter(_CONTRACT_VERSIONS)


def get_contract(
    kind: ArtifactKind,
    version: str | None = None,
) -> ContractDefinition:
    if version is None:
        return _BY_KIND[kind]
    try:
        return _BY_KIND_AND_VERSION[(kind, version)]
    except KeyError as error:
        raise ValueError(
            f"Unsupported contract version for {kind.value}: {version}"
        ) from error
