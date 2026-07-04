from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(verbose: bool, quiet: bool, log_file: str | None, json_mode: bool) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    if log_file:
        target = Path(log_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(target, encoding="utf-8")
    elif verbose and not json_mode:
        handler = logging.StreamHandler(sys.stderr)
    else:
        handler = logging.NullHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)
    root.addHandler(handler)
