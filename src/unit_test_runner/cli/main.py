from __future__ import annotations

import logging
import sys
import traceback

from .commands import dispatch
from .errors import CLIError
from .exit_codes import EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR
from .parser import ArgumentParseError, build_parser
from .result import CLIResult
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
            sys.stdout.write(result.to_json())
        else:
            sys.stderr.write(exc.usage)
            sys.stderr.write(f"{parser.prog if exc.command == 'unknown' else parser.prog + ' ' + exc.command}: error: {exc.message}\n")
        return EXIT_INPUT_ERROR
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else EXIT_INPUT_ERROR
        return EXIT_INPUT_ERROR if code != 0 else 0

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

    logging.info("command finished: %s status=%s exit_code=%s", result.command, result.status, result.exit_code)
    if args.json:
        sys.stdout.write(result.to_json())
    else:
        if result.exit_code == 0:
            sys.stdout.write(result.render_human())
        else:
            sys.stderr.write(result.render_human())
    return result.exit_code
