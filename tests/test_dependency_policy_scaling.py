from __future__ import annotations

import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dependency_policy import analyzer
from unit_test_runner.dependency_policy import signature_resolver
from unit_test_runner.c_analyzer import function_locator


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
            "/* scan-id: target */\n"
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
                f"/* scan-id: callee-{index:02d} */\n"
                '#include "scale_types.h"\n'
                f"int {name}(LargeState *state, int value) {{ return state->values[0] + value; }}\n",
                encoding="utf-8",
            )
            implementations.append(implementation)
        object_source = sources / "objects.c"
        object_source.write_text(
            "/* scan-id: objects */\n"
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

    def _candidate_paths(self, project: dict[str, object]) -> list[Path]:
        return [project["header"], *project["project_sources"]]

    def _decode_path_counter(self, project: dict[str, object]):
        candidate_by_bytes = {path.read_bytes(): path.resolve() for path in self._candidate_paths(project)}
        decoded_paths: Counter[Path] = Counter()
        real_decode = signature_resolver.decode_bytes_auto

        def count_decode(data: bytes, *args, **kwargs):
            path = candidate_by_bytes.get(data)
            if path is not None:
                decoded_paths[path] += 1
            return real_decode(data, *args, **kwargs)

        return decoded_paths, count_decode

    def _analyze_external_objects(self, project: dict[str, object], objects: list[str]):
        return analyzer.analyze_dependency_policy(
            workspace_root=project["root"],
            target_source=project["target"],
            source_digest={"preprocessor": {"includes": [{"resolved_candidates": [str(project["header"])]}]}},
            function_signature={"function": {"name": "Target"}},
            global_access={
                "file_scope_declarations": [
                    {"name": name, "type_raw": "int", "storage_class": "extern", "raw": f"extern int {name};"}
                    for name in objects
                ],
                "global_accesses": [],
            },
            call_report={"calls": [], "stub_candidates": []},
            project_sources=project["project_sources"],
            project_headers=[project["header"]],
        )

    @staticmethod
    def _object_snapshot(report):
        return [
            (
                item.symbol,
                item.type_raw,
                item.configured_mode,
                item.resolved_mode,
                item.review_status,
                item.declaration_header,
                item.definition_source,
                item.definition_candidates,
                [(evidence.kind, evidence.detail, evidence.source, evidence.weight) for evidence in item.evidence],
                item.warnings,
            )
            for item in report.external_objects
        ]

    def test_catalog_collects_typedefs_from_every_candidate_file_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            expected_paths = Counter({path.resolve(): 1 for path in self._candidate_paths(project)})
            masked_paths: Counter[Path] = Counter()
            real_mask = signature_resolver.mask_source_text

            def count_mask(text, path, *args, **kwargs):
                masked_paths[Path(path).resolve()] += 1
                return real_mask(text, path, *args, **kwargs)

            with patch.object(signature_resolver, "mask_source_text", side_effect=count_mask):
                self._build_catalog(project, project["callees"])

        self.assertEqual(expected_paths, masked_paths)

    def test_catalog_discovers_all_requested_callees_in_one_project_wide_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            expected_paths = Counter({path.resolve(): 2 for path in self._candidate_paths(project)})
            decoded_paths, count_decode = self._decode_path_counter(project)

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

        self.assertEqual(expected_paths, decoded_paths)

    def test_catalog_scan_count_is_identical_for_one_or_twenty_requested_callees(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            expected_paths = Counter({path.resolve(): 2 for path in self._candidate_paths(project)})

            def catalog_decode_paths(callees: list[str]) -> Counter[Path]:
                decoded_paths, count_decode = self._decode_path_counter(project)
                with patch.object(signature_resolver, "decode_bytes_auto", side_effect=count_decode):
                    self._build_catalog(project, callees)
                return decoded_paths

            one_callee_paths = catalog_decode_paths(project["callees"][:1])
            twenty_callee_paths = catalog_decode_paths(project["callees"])

        self.assertEqual(expected_paths, one_callee_paths)
        self.assertEqual(expected_paths, twenty_callee_paths)
        self.assertEqual(one_callee_paths, twenty_callee_paths)

    def test_catalog_results_equal_public_wrapper_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            catalog = self._build_catalog(project, project["callees"])
            resolver = getattr(signature_resolver, "resolve_dependency_signature_from_catalog", None)
            self.assertIsNotNone(
                resolver,
                "dependency-policy scaling requires resolve_dependency_signature_from_catalog(callee, *, catalog, calls)",
            )

            indexed = [
                resolver(callee, catalog=catalog, calls=[]).to_dict()
                for callee in project["callees"]
            ]
            wrapped = [
                signature_resolver.resolve_dependency_signature(
                    callee,
                    workspace_root=project["root"],
                    target_source=project["target"],
                    reachable_headers=[project["header"]],
                    project_headers=[project["header"]],
                    project_sources=project["project_sources"],
                    calls=[],
                ).to_dict()
                for callee in project["callees"]
            ]

        self.assertEqual(wrapped, indexed)

    def test_analysis_builds_one_source_digest_for_callees_sharing_an_implementation_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            include = root / "include"
            sources = root / "src"
            include.mkdir(parents=True)
            sources.mkdir(parents=True)
            header = include / "shared.h"
            header.write_text(
                "extern int g_shared;\n"
                "int Shared_First(int value);\n"
                "int Shared_Second(int value);\n",
                encoding="utf-8",
            )
            target = sources / "target.c"
            target.write_text(
                '#include "shared.h"\n'
                "int Target(int value)\n"
                "{\n"
                "    return Shared_First(value) + Shared_Second(value) + g_shared;\n"
                "}\n",
                encoding="utf-8",
            )
            implementation = sources / "shared.c"
            implementation.write_text(
                '#include "shared.h"\n'
                "int g_shared;\n"
                "int Shared_First(int value) { return value + g_shared; }\n"
                "int Shared_Second(int value) { return value - g_shared; }\n",
                encoding="utf-8",
            )
            calls = [
                {
                    "call_id": f"call-{index}",
                    "name": name,
                    "target_kind": "external_function",
                    "arguments": [{"raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}],
                    "return_usage": {"usage_kind": "expression"},
                }
                for index, name in enumerate(("Shared_First", "Shared_Second"), start=1)
            ]

            real_builder = analyzer.build_source_digest
            with patch.object(analyzer, "build_source_digest", wraps=real_builder) as build_digest:
                report = analyzer.analyze_dependency_policy(
                    workspace_root=root,
                    target_source=target,
                    source_digest={"preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}},
                    function_signature={"function": {"name": "Target"}},
                    global_access={
                        "file_scope_declarations": [],
                        "global_accesses": [{"name": "g_shared"}],
                    },
                    call_report={"calls": calls, "stub_candidates": []},
                    project_sources=[target, implementation],
                    project_headers=[header],
                )

        self.assertEqual("resolved", report.status)
        self.assertEqual(["real", "real"], [item.resolved_mode for item in report.dependencies])
        self.assertEqual(1, build_digest.call_count)

    def test_shared_implementation_function_scans_are_independent_of_callee_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            include = root / "include"
            sources = root / "src"
            include.mkdir(parents=True)
            sources.mkdir(parents=True)
            callees = [f"Shared_Scan_{index:02d}" for index in range(8)]
            header = include / "shared_scan.h"
            header.write_text(
                "extern int g_shared_scan;\n"
                + "".join(f"int {callee}(int value);\n" for callee in callees),
                encoding="utf-8",
            )
            target = sources / "target.c"
            target.write_text(
                '#include "shared_scan.h"\n'
                "int Target(int value)\n"
                "{\n"
                + "".join(f"    value += {callee}(value);\n" for callee in callees)
                + "    return value + g_shared_scan;\n"
                "}\n",
                encoding="utf-8",
            )
            implementation = sources / "shared_scan.c"
            implementation.write_text(
                '#include "shared_scan.h"\n'
                "int g_shared_scan;\n"
                + "".join(
                    f"int {callee}(int value) {{ return value + g_shared_scan; }}\n"
                    for callee in callees
                ),
                encoding="utf-8",
            )

            def scan_counts(requested: list[str]) -> tuple[int, int]:
                calls = [
                    {
                        "call_id": f"call-{index}",
                        "name": name,
                        "target_kind": "external_function",
                        "arguments": [
                            {
                                "raw": "value",
                                "argument_kind": "parameter",
                                "passing_mode_hint": "by_value",
                            }
                        ],
                        "return_usage": {"usage_kind": "expression"},
                    }
                    for index, name in enumerate(requested, start=1)
                ]
                real_annotate = function_locator.annotate_brace_depth
                real_body = analyzer._function_body
                with (
                    patch.object(function_locator, "annotate_brace_depth", wraps=real_annotate) as location_scan,
                    patch.object(analyzer, "_function_body", wraps=real_body) as body_scan,
                ):
                    report = analyzer.analyze_dependency_policy(
                        workspace_root=root,
                        target_source=target,
                        source_digest={
                            "preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}
                        },
                        function_signature={"function": {"name": "Target"}},
                        global_access={
                            "file_scope_declarations": [],
                            "global_accesses": [{"name": "g_shared_scan"}],
                        },
                        call_report={"calls": calls, "stub_candidates": []},
                        project_sources=[target, implementation],
                        project_headers=[header],
                    )
                self.assertEqual("resolved", report.status)
                self.assertEqual(["real"] * len(requested), [item.resolved_mode for item in report.dependencies])
                return location_scan.call_count, body_scan.call_count

            one_callee = scan_counts(callees[:1])
            many_callees = scan_counts(callees)

        self.assertEqual(one_callee, many_callees)
        self.assertEqual((1, 0), one_callee)

    def test_shared_global_lookup_keeps_first_complete_body_for_duplicate_definitions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            header = root / "duplicate.h"
            target = root / "target.c"
            implementation = root / "duplicate.c"
            header.write_text(
                "extern int g_duplicate;\nint Duplicate_Helper(int value);\n",
                encoding="utf-8",
            )
            target.write_text(
                '#include "duplicate.h"\n'
                "int Target(int value) { return Duplicate_Helper(value) + g_duplicate; }\n",
                encoding="utf-8",
            )
            implementation.write_text(
                '#include "duplicate.h"\n'
                "int g_duplicate;\n"
                "int Duplicate_Helper(int value) { return value + g_duplicate; }\n"
                "int Duplicate_Helper(int value) { return value; }\n",
                encoding="utf-8",
            )

            report = analyzer.analyze_dependency_policy(
                workspace_root=root,
                target_source=target,
                source_digest={
                    "preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}
                },
                function_signature={"function": {"name": "Target"}},
                global_access={
                    "file_scope_declarations": [],
                    "global_accesses": [{"name": "g_duplicate"}],
                },
                call_report={
                    "calls": [
                        {
                            "call_id": "call-1",
                            "name": "Duplicate_Helper",
                            "target_kind": "external_function",
                            "arguments": [
                                {
                                    "raw": "value",
                                    "argument_kind": "parameter",
                                    "passing_mode_hint": "by_value",
                                }
                            ],
                            "return_usage": {"usage_kind": "expression"},
                        }
                    ],
                    "stub_candidates": [],
                },
                project_sources=[target, implementation],
                project_headers=[header],
            )

        dependency = report.dependencies[0]
        self.assertEqual("real", dependency.resolved_mode)
        self.assertEqual(["g_duplicate"], dependency.shared_globals)

    def test_external_object_definitions_are_parsed_once_per_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))
            expected_paths = Counter({path.resolve(): 1 for path in project["project_sources"]})
            source_by_marker = {
                f"/* scan-id: {path.stem.replace('_', '-')} */": path.resolve()
                for path in project["project_sources"]
            }
            real_parser = analyzer.find_file_scope_object_definitions

            def parser_counter():
                parsed_paths: Counter[Path] = Counter()

                def count_parse(text, *args, **kwargs):
                    path = next((candidate for marker, candidate in source_by_marker.items() if marker in text), None)
                    if path is not None:
                        parsed_paths[path] += 1
                    return real_parser(text, *args, **kwargs)

                return parsed_paths, count_parse

            single_paths, count_single_parse = parser_counter()
            with patch.object(analyzer, "find_file_scope_object_definitions", side_effect=count_single_parse):
                single_report = self._analyze_external_objects(project, project["objects"][:1])

            many_paths, count_many_parse = parser_counter()
            with patch.object(analyzer, "find_file_scope_object_definitions", side_effect=count_many_parse):
                many_report = self._analyze_external_objects(project, project["objects"])

        self.assertEqual(expected_paths, single_paths)
        self.assertEqual(expected_paths, many_paths)
        def expected_entry(symbol: str):
            return (
                symbol,
                "int",
                "auto",
                "real",
                "resolved",
                Path("include/scale_types.h"),
                Path("src/objects.c"),
                [Path("src/objects.c")],
                [("unique_definition", "Unique definition found at src/objects.c.", "project_sources", 2)],
                [],
            )

        self.assertEqual("resolved", single_report.status)
        self.assertEqual("resolved", many_report.status)
        self.assertEqual([expected_entry(project["objects"][0])], self._object_snapshot(single_report))
        self.assertEqual([expected_entry(name) for name in project["objects"]], self._object_snapshot(many_report))
        self.assertEqual(self._object_snapshot(single_report), self._object_snapshot(many_report)[:1])
        self.assertEqual(project["objects"], [item.symbol for item in many_report.external_objects])


if __name__ == "__main__":
    unittest.main()
