import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.c_analyzer.object_definition_finder import find_file_scope_object_definitions


class ObjectDefinitionFinderTests(unittest.TestCase):
    def test_finds_only_file_scope_object_definitions(self):
        definitions = find_file_scope_object_definitions(
            """
#define FALSE_DEFINITION int macro_object;
extern int declaration_only;
extern int external_definition = 3;
typedef int Value;
int tentative;
int initialized = 1;
static int internal_linkage;
int values[3];
Value aggregate_like = {0};
int first, second = 2;
/* int commented_out; */
void Update(int value)
{
    int local_value;
    tentative = value;
    if (value) { int nested_local; }
}
"""
        )
        by_name = {item.name: item for item in definitions}

        self.assertEqual(
            {
                "external_definition",
                "tentative",
                "initialized",
                "internal_linkage",
                "values",
                "aggregate_like",
                "first",
                "second",
            },
            set(by_name),
        )
        self.assertEqual("extern", by_name["external_definition"].storage_class)
        self.assertEqual("static", by_name["internal_linkage"].storage_class)
        self.assertTrue(by_name["tentative"].is_tentative)
        self.assertTrue(by_name["values"].is_tentative)
        self.assertFalse(by_name["initialized"].is_tentative)
        self.assertEqual("int", by_name["tentative"].type_text)

    def test_does_not_treat_assignments_as_definitions(self):
        definitions = find_file_scope_object_definitions(
            """
extern int g_error_code;
int Target(int value)
{
    g_error_code = value;
    return g_error_code;
}
"""
        )

        self.assertNotIn("g_error_code", {item.name for item in definitions})


if __name__ == "__main__":
    unittest.main()
