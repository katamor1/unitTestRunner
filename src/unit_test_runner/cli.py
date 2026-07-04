from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .build_probe import build_probe
from .c_analyzer import list_functions
from .dossier import analyze_function_workflow, generate_test_draft_from_dossier
from .vc6 import discover_workspace, map_source_to_projects


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unit-test-runner")
    subcommands = parser.add_subparsers(dest="command", required=True)

    discover = subcommands.add_parser("discover-projects")
    discover.add_argument("--workspace", required=True)
    discover.add_argument("--dsw", required=True)
    discover.add_argument("--out", required=True)

    map_source = subcommands.add_parser("map-source")
    map_source.add_argument("--workspace", required=True)
    map_source.add_argument("--dsw", required=True)
    map_source.add_argument("--source", required=True)
    map_source.add_argument("--project")

    list_funcs = subcommands.add_parser("list-functions")
    list_funcs.add_argument("--source", required=True)

    analyze = subcommands.add_parser("analyze-function")
    analyze.add_argument("--workspace", required=True)
    analyze.add_argument("--dsw", required=True)
    analyze.add_argument("--source", required=True)
    analyze.add_argument("--function", required=True)
    analyze.add_argument("--configuration", required=True)
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--project")

    probe = subcommands.add_parser("build-probe")
    probe.add_argument("--dossier", required=True)
    probe.add_argument("--vc6-bin")
    probe.add_argument("--dry-run", action="store_true")

    draft = subcommands.add_parser("generate-test-draft")
    draft.add_argument("--dossier", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "discover-projects":
            result = discover_workspace(Path(args.workspace), Path(args.dsw))
            _write_json(Path(args.out), result)
            return 0
        if args.command == "map-source":
            matches = map_source_to_projects(Path(args.workspace), Path(args.dsw), args.source, args.project)
            _print_json({"matches": matches})
            return 0
        if args.command == "list-functions":
            _print_json({"functions": list_functions(Path(args.source))})
            return 0
        if args.command == "analyze-function":
            dossier = analyze_function_workflow(
                args.workspace,
                args.dsw,
                args.source,
                args.function,
                args.configuration,
                args.out,
                args.project,
            )
            _print_json({"dossier": str(Path(args.out) / "reports" / "function_dossier.json"), "target": dossier["target"]})
            return 0
        if args.command == "build-probe":
            _print_json(build_probe(args.dossier, args.vc6_bin, args.dry_run))
            return 0
        if args.command == "generate-test-draft":
            path = generate_test_draft_from_dossier(args.dossier)
            _print_json({"test_case_draft": str(path)})
            return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 10
