#!/usr/bin/env bash
# Canonical fast verification. No APK download, emulator, network ads or UI boot.
set -euo pipefail
cd "$(dirname "$0")/.."
npm test
python3 -m unittest discover -s tools -p 'test_apk_pipeline.py' -v
python3 tools/test_minimal_clickadilla.py
python3 tools/test_delivery_probe.py
python3 tools/test_stabilized_openings.py
python3 tools/test_vast_single_function.py
bash -n tools/build_vast_single_function.sh
python3 tools/test_confirmed_tracking.py
python3 tools/test_ads_regressions.py
python3 tools/test_resolved_resume.py
python3 tools/test_vast_tracking.py
python3 tools/test_vast_transition_menus.py
node tools/test-vast-tracking.js
python3 tools/test_ad_openings.py
python3 tools/test_apk_links.py
node tools/test-apk-links.js
bash -n tools/build-universal-apk.sh
python3 -m py_compile tools/patch_original_ads.py tools/patch_minimal_clickadilla.py tools/probe_ad_delivery.py tools/restore_confirmed_tracking.py android-build/ads-patches/*.py android-build/clickadilla-minimal/*.py android-build/confirmed-tracking/*.py
git diff --check
