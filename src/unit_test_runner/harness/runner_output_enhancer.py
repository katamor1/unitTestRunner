from __future__ import annotations

from pathlib import Path

from .c90_writer import sanitize_identifier, write_c_file
from .harness_models import TestSkeleton


def enhance_runner_output(output_root: Path | str, function_name: str, tests: list[TestSkeleton]) -> Path:
    output_root = Path(output_root).resolve()
    runner = output_root / "generated" / "harness" / "utr_runner.c"
    case_header = f"test_{sanitize_identifier(function_name)}_cases.h"
    table_entries = [f'    {{"{test.test_case_id}", {test.generated_function_name}}}' for test in tests]
    entries = ",\n".join(table_entries) if table_entries else '    {"no_tests", 0}'
    test_count = len(tests)
    source = f'''/* generated runner skeleton: review required */
#include <stdio.h>
#include "utr_assert.h"
#include "utr_runner.h"
#include "{case_header}"

typedef struct Utr_TestEntryTag {{
    const char *name;
    void (*func)(void);
}} Utr_TestEntry;

static Utr_TestEntry utr_tests[] = {{
{entries}
}};

static int utr_test_count = {test_count};

void Utr_RunAllTests(void)
{{
    int index;
    int before;
    int after;
    int passed;
    int failed;
    int skipped;
    int inconclusive;

    passed = 0;
    failed = 0;
    skipped = 0;
    inconclusive = 0;
    Utr_ResetFailureCount();
    for (index = 0; index < utr_test_count; index++) {{
        if (utr_tests[index].func != 0) {{
            before = Utr_GetFailureCount();
            printf("UTR RUN %s\n", utr_tests[index].name);
            fflush(stdout);
            utr_tests[index].func();
            after = Utr_GetFailureCount();
            if (after == before) {{
                passed++;
                printf("UTR OK %s\n", utr_tests[index].name);
            }} else {{
                failed++;
                printf("UTR FAILED %s\n", utr_tests[index].name);
            }}
            fflush(stdout);
        }} else {{
            skipped++;
            printf("UTR SKIPPED %s\n", utr_tests[index].name);
            fflush(stdout);
        }}
    }}
    printf("UTR SUMMARY total=%d passed=%d failed=%d skipped=%d inconclusive=%d\n", passed + failed + skipped + inconclusive, passed, failed, skipped, inconclusive);
    fflush(stdout);
}}

int main(void)
{{
    Utr_RunAllTests();
    return Utr_GetFailureCount() == 0 ? 0 : 1;
}}
'''
    write_c_file(runner, source, overwrite=True)
    return runner
