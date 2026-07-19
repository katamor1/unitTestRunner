#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$(pwd)/src"
python -m unittest \
  tests.test_test_input_form_models \
  tests.test_test_input_form_locator \
  tests.test_test_input_form_query \
  tests.test_test_input_form_apply \
  tests.test_test_input_form_reclassification \
  -v
