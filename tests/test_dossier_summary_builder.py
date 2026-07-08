import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier.summary_builder import build_summaries


class DossierSummaryBuilderTests(unittest.TestCase):
    def test_counts_current_global_access_schema_read_write_entries(self):
        summaries = build_summaries(
            {
                "global_access": {
                    "global_accesses": [
                        {"name": "g_count", "access_kind": "read_write"},
                        {"name": "g_count", "access_kind": "read"},
                    ]
                }
            }
        )

        dependency = summaries["dependency_summary"]
        self.assertEqual(2, dependency["global_read_count"])
        self.assertEqual(1, dependency["global_write_count"])

    def test_counts_legacy_global_access_schema(self):
        summaries = build_summaries(
            {
                "global_access": {
                    "reads": [{"name": "g_count"}],
                    "writes": [{"name": "g_count"}],
                }
            }
        )

        dependency = summaries["dependency_summary"]
        self.assertEqual(1, dependency["global_read_count"])
        self.assertEqual(1, dependency["global_write_count"])


if __name__ == "__main__":
    unittest.main()
