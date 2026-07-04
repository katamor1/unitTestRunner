from __future__ import annotations

import argparse

from unit_test_runner import __version__


class ArgumentParseError(Exception):
    def __init__(self, message: str, usage: str, command: str) -> None:
        super().__init__(message)
        self.message = message
        self.usage = usage
        self.command = command


class Step02ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        parts = self.prog.split()
        command = parts[-1] if len(parts) > 1 else "unknown"
        raise ArgumentParseError(message, self.format_usage(), command)


def build_parser() -> argparse.ArgumentParser:
    parser = Step02ArgumentParser(prog="unit-test-runner")
    parser.add_argument("--version", action="version", version=f"unit-test-runner {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    parser.add_argument("--quiet", action="store_true", help="Reduce non-essential output.")
    parser.add_argument("--log-file", help="Write logs to this file.")
    parser.add_argument("--json", action="store_true", help="Write machine-readable JSON to stdout.")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output.")
    subcommands = parser.add_subparsers(dest="command", required=True, parser_class=Step02ArgumentParser)

    subcommands.add_parser("doctor", help="Check the local execution environment.")

    discover = subcommands.add_parser("discover-projects", help="Discover VC6 projects from a workspace.")
    discover.add_argument("--workspace", required=True)
    discover.add_argument("--dsw")
    discover.add_argument("--out")
    discover.add_argument("--with-dsp-details", action="store_true")

    map_source = subcommands.add_parser("map-source", help="Map a C source file to VC6 project candidates.")
    map_source.add_argument("--workspace")
    map_source.add_argument("--dsw", required=True)
    map_source.add_argument("--source", required=True)
    map_source.add_argument("--configuration")
    map_source.add_argument("--project")
    map_source.add_argument("--out")

    list_funcs = subcommands.add_parser("list-functions", help="List function definitions in a C source file.")
    list_funcs.add_argument("--source", required=True)

    analyze = subcommands.add_parser("analyze-function", help="Generate a function-level dossier.")
    analyze.add_argument("--workspace")
    analyze.add_argument("--dsw", required=True)
    analyze.add_argument("--source", required=True)
    analyze.add_argument("--function", required=True)
    analyze.add_argument("--configuration", default="Win32 Debug")
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--project")
    analyze.add_argument("--emit-json", action="store_true")
    analyze.add_argument("--emit-md", action="store_true")
    analyze.add_argument("--emit-csv", action="store_true")

    probe = subcommands.add_parser("build-probe", help="Run or prepare a build probe from a dossier.")
    probe.add_argument("--dossier", required=True)
    probe.add_argument("--vc6-bin")
    probe.add_argument("--vcvars")
    probe.add_argument("--out")
    probe.add_argument("--dry-run", action="store_true")

    draft = subcommands.add_parser("generate-test-draft", help="Generate a test draft from a dossier or analysis reports.")
    draft.add_argument("--dossier")
    draft.add_argument("--function-signature")
    draft.add_argument("--global-access")
    draft.add_argument("--call-report")
    draft.add_argument("--coverage-design")
    draft.add_argument("--boundary-candidates")
    draft.add_argument("--out")
    draft.add_argument("--format", choices=("csv", "md", "json", "all"), default="csv")

    return parser
