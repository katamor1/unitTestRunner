#!/usr/bin/env bash
set -euo pipefail
pushd vscode/extension >/dev/null
npm run compile
node --test dist/test/testSpecReviewRoute.test.js dist/test/adapter.test.js
popd >/dev/null
git diff --check
