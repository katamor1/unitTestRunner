#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$PWD/src"
python -m unittest tests.test_test_input_form_models tests.test_test_input_form_locator -v
python -m compileall -q src/unit_test_runner/test_input_form tests/test_test_input_form_locator.py
git diff --check
