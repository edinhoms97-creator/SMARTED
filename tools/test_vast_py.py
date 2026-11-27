#!/usr/bin/env python3
"""Unit tests for kodi-addon/script.smartedtv.welcome/vast.py.
Run: python3 tools/test_vast_py.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "kodi-addon", "script.smartedtv.welcome"))
import vast  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "smartedtv", "testdata")
passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("ok   " + name)
    else:
        failed += 1
        print("FAIL " + name)


def fixture(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


check("clock MM:SS", vast._parse_clock("01:30") == 90)
check("offset percent", vast._parse_offset("25%")["value"] == 25)
check("offset garbage", vast._parse_offset("abc") is None)

with_ad = vast.parse_vast(fixture("vast-with-ad.xml"))
check("with-ad: not nofill", with_ad["nofill"] is False)
check("with-ad: 1 ad", len(with_ad["ads"]) == 1)
ad = with_ad["ads"][0]
check("with-ad: duration 30", ad["duration"] == 30)
check("with-ad: skip 5s", ad["skip_offset"]["seconds"] == 5)
check("with-ad: best media 1280", ad["media_file"]["width"] == 1280)
for ev in ["start", "firstQuartile", "midpoint", "thirdQuartile", "complete", "error"]:
    check("with-ad: tracking " + ev, len(ad["tracking"].get(ev, [])) == 1)
check("with-ad: impression", len(ad["impressions"]) == 1)

check("nofill minimal", vast.parse_vast(fixture("vast-nofill.xml"))["reason"] == "no-ad")
check("empty", vast.parse_vast(fixture("vast-empty.xml"))["reason"] == "empty")
err = vast.parse_vast(fixture("vast-error.xml"))
check("vast-error code 303", err["reason"] == "vast-error" and err["error_code"] == "303")
check("malformed no-throw", vast.parse_vast("<VAST><Ad><oops")["reason"] == "malformed")

# play_preroll_or_fallback with a stubbed fetch (no network in tests)
orig_fetch = vast.fetch_vast
vast.fetch_vast = lambda *a, **k: fixture("vast-nofill.xml")
r = vast.play_preroll_or_fallback()
check("preroll nofill -> outcome nofill", r["outcome"] == "nofill")

vast.fetch_vast = lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
r = vast.play_preroll_or_fallback()
check("preroll network error -> outcome error", r["outcome"] == "error")

fired = []
vast.fetch_vast = lambda *a, **k: fixture("vast-with-ad.xml")
vast.fire_all = lambda urls, error_code=None: fired.extend(urls or [])
r = vast.play_preroll_or_fallback()
check("preroll ad -> outcome ad", r["outcome"] == "ad")
check("selection does not fire playback beacons", len(fired) == 0)
vast.fetch_vast = orig_fetch

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
