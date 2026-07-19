#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="$PWD/src"
python -m compileall -q src tests
python -m unittest \
  tests.test_cli_entry_point_contract \
  tests.test_test_input_form_cli \
  tests.test_test_input_form_query \
  tests.test_test_input_form_apply \
  tests.test_test_input_form_reclassification \
  tests.test_test_input_form_end_to_end -v
pushd vscode/extension >/dev/null
npm test
popd >/dev/null
git diff --check
