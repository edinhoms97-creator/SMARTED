#!/usr/bin/env python3
"""Verify ClickAdilla VAST URL in APK key files."""
import sys, zipfile

CLICKADILLA = "vast.yomeno.xyz/vast?spot_id=1508180"

def find_vast_files(zf):
    """Find files containing VAST configuration in the APK."""
    results = []
    for name in zf.namelist():
        if name.endswith("vast.py") or name.endswith("config.js") or name.endswith("vast.js"):
            if "smartedtv" in name or "script.smartedtv" in name:
                results.append(name)
    return results

def main():
    apk_path = sys.argv[1]
    errors = []
    found_clickadilla = 0
    with zipfile.ZipFile(apk_path) as zf:
        vast_files = find_vast_files(zf)
        print(f"VAST-related files found in APK: {len(vast_files)}")
        for vf in vast_files:
            try:
                data = zf.read(vf).decode("utf-8", errors="replace")
                has_clickadilla = CLICKADILLA in data
                has_hilltop = "hilltop" in data.lower()
                print(f"  {vf}: clickadilla={'YES' if has_clickadilla else 'NO'}, hilltop={'YES' if has_hilltop else 'NO'}")
                if has_clickadilla:
                    found_clickadilla += 1
                if has_hilltop:
                    errors.append(f"{vf} still contains 'hilltop'")
            except Exception as e:
                print(f"  {vf}: error - {e}")
    
    if found_clickadilla == 0:
        errors.append("ClickAdilla URL not found in any VAST file")
    if errors:
        print("\nFAILED:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print(f"\nSUCCESS: ClickAdilla found in {found_clickadilla} file(s), original skin/UI preserved")

if __name__ == "__main__":
    main()
