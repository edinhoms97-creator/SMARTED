#!/usr/bin/env python3
"""Replace HilltopAds URLs with ClickAdilla in text files under a directory.
Does NOT modify any other content - surgical URL replacement only."""
import os
import re
import sys

CLICKADILLA = "https://vast.yomeno.xyz/vast?spot_id=1508180"
TEXT_EXTS = {".py", ".js", ".html", ".xml", ".json", ".txt", ".cfg", ".ini"}

def main():
    base_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    replaced = 0
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
                if b"hilltop" not in data.lower():
                    continue
                text = None
                used_enc = None
                for enc in ("utf-8", "latin-1"):
                    try:
                        text = data.decode(enc)
                        used_enc = enc
                        break
                    except:
                        continue
                if text is None:
                    continue
                original = text
                text = re.sub(
                    r'''https?://[^"' <>\]\}\\]*hilltop[^"' <>\]\}\\]*''',
                    CLICKADILLA, text, flags=re.IGNORECASE
                )
                text = re.sub(
                    r'''[A-Za-z0-9._-]*hilltopads\.[A-Za-z0-9._/-]+[^"' <>\]\}\\]*''',
                    CLICKADILLA, text, flags=re.IGNORECASE
                )
                if text != original:
                    with open(fpath, "w", encoding=used_enc, errors="replace") as f:
                        f.write(text)
                    rel = os.path.relpath(fpath, base_dir)
                    print(f"Replaced in: {rel}")
                    replaced += 1
            except Exception as e:
                print(f"Error processing {fpath}: {e}")
    print(f"Total files modified: {replaced}")

if __name__ == "__main__":
    main()
