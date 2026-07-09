# Uploaded quick workspace validation

A generated `_quick` workspace for `Shared3` exposed that `utr_runner.c` was emitting literal newlines inside C string literals for runner markers such as `UTR RUN`, `UTR OK`, and `UTR SUMMARY`.

The generated build failed with compiler diagnostics equivalent to `C2001: newline in constant/string literal` in `generated/harness/utr_runner.c`.

Follow-up fix: runner output strings must be emitted as escaped C newlines, e.g. `printf("UTR RUN %s\\n", ...)`, so the generated C source contains `\n` instead of an actual line break inside the string literal.
