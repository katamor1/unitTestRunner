import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dependency_policy.signature_resolver import resolve_dependency_signature


class DependencySignatureResolverTests(unittest.TestCase):
    def test_prefers_reachable_header_and_matches_definition_with_calling_convention(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            header = root / "include" / "device.h"
            source = root / "src" / "device.c"
            target = root / "src" / "control.c"
            header.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(
                "typedef struct DeviceContextTag DeviceContext;\n"
                "long __stdcall Device_Read(DeviceContext *context, unsigned short channel);\n",
                encoding="utf-8",
            )
            source.write_text(
                '#include "device.h"\nlong __stdcall Device_Read(DeviceContext *context, unsigned short channel)\n{\n    return channel;\n}\n',
                encoding="utf-8",
            )
            target.write_text('#include "device.h"\nint Target(void) { return (int)Device_Read(0, 1); }\n', encoding="utf-8")

            signature = resolve_dependency_signature(
                "Device_Read",
                workspace_root=root,
                target_source=target,
                reachable_headers=[header],
                project_sources=[source],
                calls=[
                    {
                        "arguments": [
                            {"raw": "0", "argument_kind": "literal", "passing_mode_hint": "by_value"},
                            {"raw": "1", "argument_kind": "literal", "passing_mode_hint": "by_value"},
                        ],
                        "return_usage": {"usage_kind": "assigned"},
                    }
                ],
            )

        self.assertEqual("exact", signature.resolution)
        self.assertEqual("long", signature.return_type_raw)
        self.assertEqual("__stdcall", signature.calling_convention)
        self.assertEqual(["DeviceContext *", "unsigned short"], [item.type_raw for item in signature.parameters])
        self.assertEqual(Path("include/device.h"), signature.declaration_source)
        self.assertEqual(Path("src/device.c"), signature.definition_source)

    def test_conflicting_reachable_declarations_require_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "a.h"
            second = root / "b.h"
            target = root / "target.c"
            first.write_text("int Helper(int value);\n", encoding="utf-8")
            second.write_text("long Helper(long value);\n", encoding="utf-8")
            target.write_text("int Target(void) { return Helper(1); }\n", encoding="utf-8")

            signature = resolve_dependency_signature(
                "Helper",
                workspace_root=root,
                target_source=target,
                reachable_headers=[first, second],
                project_sources=[],
                calls=[],
            )

        self.assertEqual("review_required", signature.resolution)
        self.assertTrue(signature.conflicts)
        self.assertIn("a.h", " ".join(signature.conflicts))
        self.assertIn("b.h", " ".join(signature.conflicts))

    def test_variadic_declaration_is_review_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            header = root / "log.h"
            target = root / "target.c"
            header.write_text("int Log_Write(const char *format, ...);\n", encoding="utf-8")
            target.write_text("int Target(void) { return Log_Write(\"x\"); }\n", encoding="utf-8")

            signature = resolve_dependency_signature(
                "Log_Write",
                workspace_root=root,
                target_source=target,
                reachable_headers=[header],
                project_sources=[],
                calls=[],
            )

        self.assertEqual("review_required", signature.resolution)
        self.assertTrue(any(item.is_variadic for item in signature.parameters))
        self.assertTrue(any("variadic" in item.lower() for item in signature.conflicts))

    def test_uses_project_header_candidate_when_call_reachable_headers_do_not_declare_symbol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_header = root / "include" / "helper.h"
            target = root / "src" / "target.c"
            project_header.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            project_header.write_text("unsigned long Helper(unsigned short value);\n", encoding="utf-8")
            target.write_text("int Target(void) { return (int)Helper(1); }\n", encoding="utf-8")

            signature = resolve_dependency_signature(
                "Helper",
                workspace_root=root,
                target_source=target,
                reachable_headers=[],
                project_headers=[project_header],
                project_sources=[],
                calls=[],
            )

        self.assertEqual("exact", signature.resolution)
        self.assertEqual("unsigned long", signature.return_type_raw)
        self.assertEqual(Path("include/helper.h"), signature.declaration_source)

    def test_simple_call_without_declaration_is_compatible_inferred(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.c"
            target.write_text("int Target(int value) { return Boundary(value); }\n", encoding="utf-8")

            signature = resolve_dependency_signature(
                "Boundary",
                workspace_root=root,
                target_source=target,
                reachable_headers=[],
                project_sources=[],
                calls=[
                    {
                        "arguments": [{"raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}],
                        "return_usage": {"usage_kind": "returned"},
                    }
                ],
            )

        self.assertEqual("compatible_inferred", signature.resolution)
        self.assertEqual("int", signature.return_type_raw)
        self.assertEqual("int", signature.parameters[0].type_raw)


    def test_extern_macro_storage_prefix_does_not_conflict_with_definition(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            header = root / "helper.h"
            source = root / "helper.c"
            target = root / "target.c"
            header.write_text("#define EXTERN extern\nEXTERN int Helper(int value);\n", encoding="utf-8")
            source.write_text('#include "helper.h"\nint Helper(int value) { return value; }\n', encoding="utf-8")
            target.write_text('#include "helper.h"\nint Target(int value) { return Helper(value); }\n', encoding="utf-8")

            signature = resolve_dependency_signature(
                "Helper",
                workspace_root=root,
                target_source=target,
                reachable_headers=[header],
                project_sources=[source],
                calls=[],
            )

        self.assertEqual("exact", signature.resolution)
        self.assertEqual("int", signature.return_type_raw)
        self.assertEqual("int Helper(int value)", signature.prototype)


    def test_resolves_scalar_typedefs_for_signature_compatibility(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            header = root / "helper.h"
            source = root / "helper.c"
            target = root / "target.c"
            header.write_text("typedef unsigned long U32;\nU32 Helper(U32 value);\n", encoding="utf-8")
            source.write_text('#include "helper.h"\nU32 Helper(U32 value) { return value; }\n', encoding="utf-8")
            target.write_text('#include "helper.h"\nint Target(void) { return (int)Helper(1); }\n', encoding="utf-8")

            signature = resolve_dependency_signature(
                "Helper",
                workspace_root=root,
                target_source=target,
                reachable_headers=[header],
                project_sources=[source],
                calls=[],
            )

        self.assertEqual("exact", signature.resolution)
        self.assertEqual("unsigned long", signature.return_type_canonical)
        self.assertEqual("scalar", signature.return_type_category)
        self.assertEqual("unsigned long", signature.parameters[0].canonical_type)
        self.assertEqual("scalar", signature.parameters[0].type_category)

    def test_aggregate_typedef_return_requires_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            header = root / "helper.h"
            source = root / "helper.c"
            target = root / "target.c"
            header.write_text("typedef struct ResultTag { int value; } Result;\nResult Helper(void);\n", encoding="utf-8")
            source.write_text('#include "helper.h"\nResult Helper(void) { Result value; value.value = 1; return value; }\n', encoding="utf-8")
            target.write_text('#include "helper.h"\nint Target(void) { return Helper().value; }\n', encoding="utf-8")

            signature = resolve_dependency_signature(
                "Helper",
                workspace_root=root,
                target_source=target,
                reachable_headers=[header],
                project_sources=[source],
                calls=[],
            )

        self.assertEqual("review_required", signature.resolution)
        self.assertEqual("aggregate", signature.return_type_category)
        self.assertTrue(any("aggregate return" in item.lower() for item in signature.conflicts))

    def test_pointer_typedef_is_classified_as_pointer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            header = root / "helper.h"
            source = root / "helper.c"
            target = root / "target.c"
            header.write_text("typedef struct ContextTag Context;\ntypedef Context * ContextPtr;\nContextPtr Helper(ContextPtr value);\n", encoding="utf-8")
            source.write_text('#include "helper.h"\nContextPtr Helper(ContextPtr value) { return value; }\n', encoding="utf-8")
            target.write_text('#include "helper.h"\nContextPtr Target(ContextPtr value) { return Helper(value); }\n', encoding="utf-8")

            signature = resolve_dependency_signature(
                "Helper",
                workspace_root=root,
                target_source=target,
                reachable_headers=[header],
                project_sources=[source],
                calls=[],
            )

        self.assertEqual("exact", signature.resolution)
        self.assertEqual("pointer", signature.return_type_category)
        self.assertEqual("pointer", signature.parameters[0].type_category)
        self.assertIn("*", signature.return_type_canonical or "")


if __name__ == "__main__":
    unittest.main()
