#!/usr/bin/env bash
set -euo pipefail

echo "e2b3419e4a2b31b96299a894833f6667c1ce2299d24fdca3ab980ce5aa283c8d  /tmp/payload.tar.gz" | sha256sum -c -
export PYTHONPATH="$PWD/src"
python -m unittest \
  tests.test_test_input_form_cli \
  tests.test_test_input_form_end_to_end \
  tests.test_test_input_form_reclassification \
  tests.test_harness_skeleton_generation -v
pushd vscode/extension >/dev/null
npm test
popd >/dev/null
git diff --check
