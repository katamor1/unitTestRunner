from __future__ import annotations

from pathlib import Path

from unit_test_runner.dossier.dossier_models import TraceabilityLink
from unit_test_runner.dossier.traceability import write_traceability_csv


def write_dossier_traceability_csv(path: Path, links: list[TraceabilityLink]) -> None:
    write_traceability_csv(path, links)
