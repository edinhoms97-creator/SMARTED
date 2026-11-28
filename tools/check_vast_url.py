#!/usr/bin/env python3
"""Verify that the VAST URL in key files is ClickAdilla and no HilltopAds URLs remain."""
import os, sys, zipfile

KEY_FILES = [
    "assets/addons/script.smartedtv.welcome/vast.py",
    "assets/smartedtv/js/config.js",
    "assets/smartedtv/js/vast.js",
]
CLICKADILLA = "vast.yomeno.xyz"

def check_apk(apk_path):
    errors = []
    with zipfile.ZipFile(apk_path) as zf:
        for key_file in KEY_FILES:
            try:
                data = zf.read(key_file).decode("utf-8", errors="replace")
                if "hilltop" in data.lower():
                    errors.append(f"{key_file}: still contains 'hilltop'")
                if CLICKADILLA not in data:
                    errors.append(f"{key_file}: ClickAdilla URL not found")
            except KeyError:
                errors.append(f"{key_file}: file not found in APK")
            except Exception as e:
                errors.append(f"{key_file}: error - {e}")
    return errors

if __name__ == "__main__":
    apk_path = sys.argv[1]
    errors = check_apk(apk_path)
    if errors:
        print("FAILED:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print(f"SUCCESS: All key VAST files have ClickAdilla, no HilltopAds")
    for kf in KEY_FILES:
        print(f"  OK: {kf}")
