from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .kinds import ArtifactKind


CURRENT_CONTRACT_VERSION = "1.0.0"


@dataclass(frozen=True)
class ContractDefinition:
    kind: ArtifactKind
    current_version: str
    schema_resource: str
    compatible_source_versions: tuple[str, ...]
    semantic_validator: str


_CONTRACTS = tuple(
    ContractDefinition(
        kind=kind,
        current_version=CURRENT_CONTRACT_VERSION,
        schema_resource=f"{kind.value}.schema.json",
        compatible_source_versions=("0.1",),
        semantic_validator="test_spec" if kind is ArtifactKind.TEST_SPEC else "common",
    )
    for kind in ArtifactKind
)

_BY_KIND = {contract.kind: contract for contract in _CONTRACTS}
_BY_KIND_AND_VERSION = {
    (contract.kind, contract.current_version): contract for contract in _CONTRACTS
}


def iter_contracts() -> Iterator[ContractDefinition]:
    return iter(_CONTRACTS)


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
