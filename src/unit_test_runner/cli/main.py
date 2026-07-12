from __future__ import annotations

import logging
import os
import sys
import traceback
from typing import TextIO

from .commands import dispatch
from .errors import CLIError
from .exit_codes import EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR
from .outcomes import DomainOutcome
from .parser import ArgumentParseError, build_parser
from .result import CLIResult
from unit_test_runner.contracts import RunOutcome
from unit_test_runner.utils.logging import setup_logging


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(raw_argv)
    except ArgumentParseError as exc:
        result = CLIResult(
            status="error",
            exit_code=EXIT_INPUT_ERROR,
            command=exc.command,
            message=exc.message,
            errors=[exc.message],
        )
        if "--json" in raw_argv:
            _write_stream(sys.stdout, result.to_json())
        else:
            _write_stream(sys.stderr, exc.usage)
            _write_stream(sys.stderr, f"{parser.prog if exc.command == 'unknown' else parser.prog + ' ' + exc.command}: error: {exc.message}\n")
        return EXIT_INPUT_ERROR
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else EXIT_INPUT_ERROR
        return EXIT_INPUT_ERROR if code != 0 else 0

    _apply_build_probe_environment(args)
    setup_logging(verbose=args.verbose, quiet=args.quiet, log_file=args.log_file, json_mode=args.json)
    logging.info("command started: %s", args.command)
    try:
        result = dispatch(args)
    except CLIError as exc:
        result = CLIResult(
            status="error",
            exit_code=exc.exit_code,
            command=exc.command,
            message=exc.message,
            errors=[exc.message],
        )
        logging.error(exc.message)
    except Exception as exc:  # pragma: no cover - kept as CLI safety net
        logging.error("internal error: %s", exc)
        logging.debug(traceback.format_exc())
        result = CLIResult(
            status="internal_error",
            exit_code=EXIT_INTERNAL_ERROR,
            command=getattr(args, "command", "unknown"),
            message="An unexpected internal error occurred.",
            errors=[str(exc)],
        )

    json_output = None
    if args.json:
        result, json_output = _validated_json_result(result)
    logging.info("command finished: %s status=%s exit_code=%s", result.command, result.status, result.exit_code)
    if args.json:
        _write_stream(sys.stdout, json_output or "")
    else:
        if result.exit_code == 0:
            _write_stream(sys.stdout, result.render_human())
        else:
            _write_stream(sys.stderr, result.render_human())
    return result.exit_code


def _validated_json_result(result: CLIResult) -> tuple[CLIResult, str]:
    try:
        return result, result.to_json()
    except ValueError as exc:
        logging.error("CLI result contract validation failed: %s", exc)
        fallback = CLIResult(
            status="internal_error",
            exit_code=EXIT_INTERNAL_ERROR,
            command=result.command,
            message="The command result violated the CLI contract.",
            errors=[{"code": "contract_error", "message": str(exc)}],
            outcome=DomainOutcome("command", RunOutcome.ERROR, None),
        )
        return fallback, fallback.to_json()


def _apply_build_probe_environment(args) -> None:
    if getattr(args, "command", None) != "build-probe":
        return
    toolchain = getattr(args, "toolchain", None)
    if toolchain:
        os.environ["UNIT_TEST_RUNNER_BUILD_TOOLCHAIN"] = toolchain
    cc = getattr(args, "cc", None)
    if cc:
        os.environ["UNIT_TEST_RUNNER_CC"] = cc


def _write_stream(stream: TextIO, text: str) -> None:
    try:
        stream.write(text)
        return
    except UnicodeEncodeError:
        buffer = getattr(stream, "buffer", None)
        encoding = stream.encoding or "utf-8"
        if buffer is None:
            stream.write(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))
            return
        buffer.write(text.encode(encoding, errors="backslashreplace"))
        buffer.flush()
