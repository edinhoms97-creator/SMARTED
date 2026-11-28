#!/usr/bin/env python3
"""Check for any remaining 'hilltop' references in text files. Returns exit code 1 if found."""
import os
import sys

TEXT_EXTS = {".py", ".js", ".html", ".xml", ".json", ".txt", ".cfg", ".ini"}

def check(base_dir):
    found = []
    for root, dirs, files in os.walk(base_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            if ext not in TEXT_EXTS:
                continue
            try:
                size = os.path.getsize(fpath)
                if size > 10 * 1024 * 1024:
                    continue
                with open(fpath, "rb") as f:
                    data = f.read()
                if b"hilltop" in data.lower():
                    rel = os.path.relpath(fpath, base_dir)
                    found.append(rel)
            except:
                pass
    return found

if __name__ == "__main__":
    base_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    found = check(base_dir)
    if found:
        print(f"FOUND 'hilltop' in {len(found)} files:")
        for f in found:
            print(f"  {f}")
        sys.exit(1)
    else:
        print("No 'hilltop' references found in text files - CLEAN")
        sys.exit(0)
