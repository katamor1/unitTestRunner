from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dependency_policy import analyzer
from unit_test_runner.dependency_policy import signature_resolver


class DependencyPolicyScalingTests(unittest.TestCase):
    def _project(self, root: Path) -> dict[str, object]:
        include = root / "include"
        sources = root / "src"
        include.mkdir(parents=True)
        sources.mkdir(parents=True)

        callees = [f"Scale_Callee_{index:02d}" for index in range(20)]
        objects = [f"g_scale_object_{index:02d}" for index in range(5)]
        header = include / "scale_types.h"
        header_lines = [
            "/* CP932 fixture: \u4f9d\u5b58\u95a2\u4fc2\u30b9\u30b1\u30fc\u30ea\u30f3\u30b0 */",
            "typedef struct LargeStateTag { int values[256]; } LargeState;",
            "typedef int (*ScaleHandler)(LargeState *state, int value);",
            "typedef struct ScaleHandlerTableTag { ScaleHandler handlers[20]; } ScaleHandlerTable;",
            *(f"extern int {name};" for name in objects),
            *(f"int {name}(LargeState *state, int value);" for name in callees),
        ]
        header.write_bytes(("\n".join(header_lines) + "\n").encode("cp932"))

        target = sources / "target.c"
        target.write_text(
            '#include "scale_types.h"\n'
            "int Target(LargeState *state, int value)\n"
            "{\n"
            + "".join(f"    value += {name}(state, value);\n" for name in callees)
            + "    return value;\n}\n",
            encoding="utf-8",
        )
        implementations: list[Path] = []
        for index, name in enumerate(callees):
            implementation = sources / f"callee_{index:02d}.c"
            implementation.write_text(
                '#include "scale_types.h"\n'
                f"int {name}(LargeState *state, int value) {{ return state->values[0] + value; }}\n",
                encoding="utf-8",
            )
            implementations.append(implementation)
        object_source = sources / "objects.c"
        object_source.write_text(
            '#include "scale_types.h"\n'
            + "".join(f"int {name};\n" for name in objects),
            encoding="utf-8",
        )
        project_sources = [target, *implementations, object_source]
        return {
            "callees": callees,
            "header": header,
            "objects": objects,
            "project_sources": project_sources,
            "root": root,
            "target": target,
        }

    def _build_catalog(self, project: dict[str, object], callees: list[str]):
        builder = getattr(signature_resolver, "build_dependency_signature_catalog", None)
        self.assertIsNotNone(
            builder,
            "dependency-policy scaling requires build_dependency_signature_catalog(callees, *, workspace_root, target_source, reachable_headers, project_headers, project_sources)",
        )
        return builder(
            callees,
            workspace_root=project["root"],
            target_source=project["target"],
            reachable_headers=[project["header"]],
            project_headers=[project["header"]],
            project_sources=project["project_sources"],
        )

    def test_catalog_collects_typedefs_from_every_candidate_file_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            expected_candidates = 1 + len(project["project_sources"])
            masks = 0
            real_mask = signature_resolver.mask_source_text

            def count_mask(*args, **kwargs):
                nonlocal masks
                masks += 1
                return real_mask(*args, **kwargs)

            with patch.object(signature_resolver, "mask_source_text", side_effect=count_mask):
                self._build_catalog(project, project["callees"])

        self.assertEqual(expected_candidates, masks)

    def test_catalog_discovers_all_requested_callees_in_one_project_wide_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            expected_candidates = 1 + len(project["project_sources"])
            decodes = 0
            real_decode = signature_resolver.decode_bytes_auto

            def count_decode(*args, **kwargs):
                nonlocal decodes
                decodes += 1
                return real_decode(*args, **kwargs)

            with patch.object(signature_resolver, "decode_bytes_auto", side_effect=count_decode):
                catalog = self._build_catalog(project, project["callees"])
                resolver = getattr(signature_resolver, "resolve_dependency_signature_from_catalog", None)
                self.assertIsNotNone(
                    resolver,
                    "dependency-policy scaling requires resolve_dependency_signature_from_catalog(callee, *, catalog, calls)",
                )
                for callee in project["callees"]:
                    resolved = resolver(callee, catalog=catalog, calls=[])
                    self.assertEqual("exact", resolved.resolution)

        self.assertEqual(expected_candidates * 2, decodes)

    def test_catalog_scan_count_is_identical_for_one_or_twenty_requested_callees(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            real_decode = signature_resolver.decode_bytes_auto

            def catalog_decode_count(callees: list[str]) -> int:
                decodes = 0

                def count_decode(*args, **kwargs):
                    nonlocal decodes
                    decodes += 1
                    return real_decode(*args, **kwargs)

                with patch.object(signature_resolver, "decode_bytes_auto", side_effect=count_decode):
                    self._build_catalog(project, callees)
                return decodes

            one_callee_count = catalog_decode_count(project["callees"][:1])
            twenty_callee_count = catalog_decode_count(project["callees"])

        self.assertEqual(one_callee_count, twenty_callee_count)

    def test_external_object_definitions_are_parsed_once_per_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            parses = 0
            real_parser = analyzer.find_file_scope_object_definitions

            def count_parse(*args, **kwargs):
                nonlocal parses
                parses += 1
                return real_parser(*args, **kwargs)

            global_access = {
                "file_scope_declarations": [
                    {"name": name, "type_raw": "int", "storage_class": "extern", "raw": f"extern int {name};"}
                    for name in project["objects"]
                ],
                "global_accesses": [],
            }
            with patch.object(analyzer, "find_file_scope_object_definitions", side_effect=count_parse):
                analyzer.analyze_dependency_policy(
                    workspace_root=project["root"],
                    target_source=project["target"],
                    source_digest={"preprocessor": {"includes": [{"resolved_candidates": [str(project["header"])]}]}},
                    function_signature={"function": {"name": "Target"}},
                    global_access=global_access,
                    call_report={"calls": [], "stub_candidates": []},
                    project_sources=project["project_sources"],
                    project_headers=[project["header"]],
                )

        self.assertEqual(len(project["project_sources"]), parses)


if __name__ == "__main__":
    unittest.main()
