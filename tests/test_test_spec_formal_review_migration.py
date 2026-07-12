from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.contracts import ArtifactKind, ContractMode, load_artifact, migrate_payload

from tests.spec_support import copied_payload


def canonical_like_v01() -> dict:
    payload = copied_payload()
    return {
        "schema_version": "0.1",
        "producer": copy.deepcopy(payload["producer"]),
        "extensions": {"vendor": {"trace": "keep-me"}},
        **copy.deepcopy(payload["data"]),
    }


class TestSpecFormalReviewMigrationTests(unittest.TestCase):
    def test_v01_top_level_authority_is_rejected_before_projection(self):
        legacy = canonical_like_v01()
        legacy["approved"] = True

        with self.assertRaisesRegex(ValueError, "approved"):
            migrate_payload(
                ArtifactKind.TEST_SPEC,
                legacy,
                target_version="1.1.0",
            )

    def test_v01_unknown_top_level_and_case_fields_are_rejected(self):
        for location in ("top", "case"):
            with self.subTest(location=location):
                legacy = canonical_like_v01()
                if location == "top":
                    legacy["unrepresentable"] = {"value": 1}
                else:
                    legacy["test_cases"][0]["legacy_secret"] = "discarded"
                with self.assertRaisesRegex(ValueError, "unrepresentable|legacy_secret"):
                    migrate_payload(
                        ArtifactKind.TEST_SPEC,
                        legacy,
                        target_version="1.1.0",
                    )

    def test_v01_nested_authority_is_rejected_before_projection(self):
        legacy = canonical_like_v01()
        legacy["test_cases"][0]["expected_observations"][0]["approval"] = {
            "reviewer": "someone"
        }

        with self.assertRaisesRegex(ValueError, "approval"):
            migrate_payload(
                ArtifactKind.TEST_SPEC,
                legacy,
                target_version="1.1.0",
            )

    def test_v01_preserves_supplied_producer_and_extensions(self):
        legacy = canonical_like_v01()

        migrated = migrate_payload(
            ArtifactKind.TEST_SPEC,
            legacy,
            target_version="1.1.0",
        )

        self.assertEqual(legacy["producer"], migrated["producer"])
        self.assertEqual(
            {"trace": "keep-me"},
            migrated["extensions"]["vendor"],
        )
        self.assertEqual("0.1", migrated["extensions"]["migration"]["source_version"])

    def test_v10_migration_metadata_collision_is_typed_and_non_destructive(self):
        previous = copied_payload()
        previous["schema_version"] = "1.0.0"
        previous["extensions"] = {"migration": {"vendor": "owned"}}
        before_mapping = copy.deepcopy(previous)

        with self.assertRaisesRegex(ValueError, "extensions.migration"):
            migrate_payload(
                ArtifactKind.TEST_SPEC,
                previous,
                target_version="1.1.0",
            )
        self.assertEqual(before_mapping, previous)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_spec.json"
            path.write_text(json.dumps(previous, indent=2), encoding="utf-8")
            before_bytes = path.read_bytes()
            loaded = load_artifact(
                path,
                expected_kind=ArtifactKind.TEST_SPEC,
                mode=ContractMode.COMPATIBLE,
            )
            self.assertEqual(before_bytes, path.read_bytes())
        self.assertIn("migration_error", {item.code for item in loaded.violations})


if __name__ == "__main__":
    unittest.main()
