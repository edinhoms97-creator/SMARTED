#!/usr/bin/env python3
"""Replace ALL HilltopAds references with ClickAdilla in text files.
Surgical replacement: only changes URLs/domain references containing 'hilltop'.
Does NOT touch skin, UI, VIP, checkout, QR code, or any other functionality."""
import os
import re
import sys

CLICKADILLA = "https://vast.yomeno.xyz/vast?spot_id=1508180"
TEXT_EXTS = {".py", ".js", ".html", ".xml", ".json", ".txt", ".cfg", ".ini", ".properties", ".htm"}

def replace_in_file(fpath):
    """Replace hilltop URLs in a single file. Returns True if modified."""
    try:
        size = os.path.getsize(fpath)
        if size > 10 * 1024 * 1024:
            return False
        with open(fpath, "rb") as f:
            data = f.read()
        if b"hilltop" not in data.lower():
            return False
        
        text = None
        used_enc = None
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                text = data.decode(enc)
                used_enc = enc
                break
            except:
                continue
        if text is None:
            return False
        
        original = text
        
        # Replace URLs containing hilltop (http:// or https://)
        text = re.sub(
            r'https?://[^\s"\'<>\\\]\)}]*hilltop[^\s"\'<>\\\]\)}]*',
            CLICKADILLA, text, flags=re.IGNORECASE
        )
        # Replace domain-only references (e.g., "hilltopads.net", "cdn.hilltopads.com/path")
        text = re.sub(
            r'[a-zA-Z0-9._-]+\.hilltopads?\.[a-zA-Z]{2,}[^\s"\'<>\\\]\)}]*',
            CLICKADILLA, text, flags=re.IGNORECASE
        )
        # Replace any quoted string containing hilltop (handles config values)
        # Pattern: "something-hilltop-something" or 'something-hilltop-something'
        # But ONLY if it looks like a URL/domain (contains dots or slashes)
        text = re.sub(
            r'["\']([^"\']*hilltop[^"\']*)["\']',
            lambda m: '"' + CLICKADILLA + '"' if re.search(r'[./]', m.group(1), re.IGNORECASE) else m.group(0),
            text, flags=re.IGNORECASE
        )
        
        if text != original:
            with open(fpath, "w", encoding=used_enc, errors="replace") as f:
                f.write(text)
            return True
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    base_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    replaced = 0
    for root, dirs, files in os.walk(base_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            if ext not in TEXT_EXTS:
                continue
            if replace_in_file(fpath):
                rel = os.path.relpath(fpath, base_dir)
                print(f"Replaced in: {rel}")
                replaced += 1
    print(f"Total files modified: {replaced}")

if __name__ == "__main__":
    main()
