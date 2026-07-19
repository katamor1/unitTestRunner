from __future__ import annotations


class CLIError(Exception):
    def __init__(
        self,
        message: str,
        exit_code: int,
        command: str = "unknown",
        code: str = "error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.command = command
        self.code = code
