#!/usr/bin/env bash
# Canonical fast verification. No APK download, emulator, network ads or UI boot.
set -euo pipefail
cd "$(dirname "$0")/.."
npm test
python3 -m unittest discover -s tools -p 'test_apk_pipeline.py' -v
python3 tools/test_ads_regressions.py
python3 tools/test_resolved_resume.py
python3 tools/test_vast_tracking.py
python3 tools/test_vast_startup_diagnostics.py
node tools/test-vast-tracking.js
python3 tools/test_ad_openings.py
python3 tools/test_apk_links.py
node tools/test-apk-links.js
bash -n tools/build-universal-apk.sh
python3 -m py_compile tools/patch_original_ads.py android-build/ads-patches/*.py
git diff --check
