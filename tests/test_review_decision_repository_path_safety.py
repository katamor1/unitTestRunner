from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from unit_test_runner.dossier import review_decision_repository as repository_module


class ReviewDecisionRepositoryPathSafetyTests(unittest.TestCase):
    def test_safety_check_does_not_resolve_the_volatile_lock_leaf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = root / "reports"
            reports.mkdir()
            ledger = reports / "review_decisions.json"
            lock = reports / ".review_decisions.json.lock"
            simulated_external = root.parent / "simulated-transient-target" / lock.name
            original_resolve = Path.resolve

            def resolve(path: Path, strict: bool = False) -> Path:
                if path == lock:
                    return simulated_external
                return original_resolve(path, strict=strict)

            with mock.patch.object(Path, "resolve", new=resolve):
                repository_module._assert_safe_repository_paths(root, ledger, lock)

    def test_safety_check_still_rejects_a_symlinked_lock_leaf(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            tempfile.TemporaryDirectory() as outside,
        ):
            root = Path(temporary)
            reports = root / "reports"
            reports.mkdir()
            ledger = reports / "review_decisions.json"
            lock = reports / ".review_decisions.json.lock"
            try:
                lock.symlink_to(Path(outside) / "lock")
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink creation is unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "symlink|reparse"):
                repository_module._assert_safe_repository_paths(root, ledger, lock)


if __name__ == "__main__":
    unittest.main()
