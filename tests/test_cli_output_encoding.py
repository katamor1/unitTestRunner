import io
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.cli.main import _write_stream
from unit_test_runner.cli.result import CLIResult


class CliOutputEncodingTests(unittest.TestCase):
    def test_json_output_is_ascii_safe_for_cp932_consoles(self):
        result = CLIResult(
            status="error",
            exit_code=1,
            command="build-probe",
            message="compiler output contained replacement character",
            data={"log_excerpt": "invalid byte was decoded as \ufffd"},
        )

        text = result.to_json()

        text.encode("cp932")
        self.assertIn("\\ufffd", text)
        self.assertEqual("invalid byte was decoded as \ufffd", json.loads(text)["data"]["log_excerpt"])

    def test_stream_writer_falls_back_when_console_encoding_rejects_text(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="cp932", errors="strict")

        _write_stream(stream, "invalid byte was decoded as \ufffd\n")
        stream.flush()

        self.assertIn(b"\\ufffd", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
