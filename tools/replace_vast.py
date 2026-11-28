#!/usr/bin/env python3
"""Aggressively replace HilltopAds URLs with ClickAdilla in all text files under a directory."""
import os
import re
import sys

CLICKADILLA = "https://vast.yomeno.xyz/vast?spot_id=1508180"
BINARY_EXTS = {".so", ".dex", ".class", ".png", ".jpg", ".jpeg", ".gif", 
               ".webp", ".mp4", ".mp3", ".ogg", ".wav", ".ttf", ".otf", 
               ".woff", ".woff2", ".arsc"}

def is_binary_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in BINARY_EXTS:
        return True
    try:
        size = os.path.getsize(filepath)
        if size > 10 * 1024 * 1024:  # >10MB
            return True
    except:
        return True
    return False

def replace_in_file(filepath):
    """Replace hilltop URLs in a single file. Returns True if modified."""
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except:
        return False
    
    # Check if file contains 'hilltop' (case insensitive)
    if b'hilltop' not in data.lower():
        return False
    
    try:
        text = data.decode('utf-8')
    except:
        try:
            text = data.decode('latin-1')
        except:
            return False
    
    original = text
    
    # Pattern 1: Full URLs containing hilltop
    text = re.sub(
        r'https?://[^"\' <>\\\]\}]*hilltop[^"\' <>\\\]\}]*',
        CLICKADILLA, text, flags=re.IGNORECASE
    )
    
    # Pattern 2: Bare domains containing hilltopads
    text = re.sub(
        r'[A-Za-z0-9._-]*hilltopads\.[A-Za-z0-9._-]+[^"\' <>\\\]\}]*',
        CLICKADILLA, text, flags=re.IGNORECASE
    )
    
    # Pattern 3: Bare domains containing hilltop (but not hilltopads)
    text = re.sub(
        r'[A-Za-z0-9._-]*hilltop\.[A-Za-z]{2,}[^"\' <>\\\]\}]*',
        CLICKADILLA, text, flags=re.IGNORECASE
    )
    
    # Pattern 4: VAST_TAG or vastTagUrl assignments with non-ClickAdilla URLs
    def fix_vast_url(match):
        url = match.group(1)
        if 'yomeno' in url.lower() or 'clickadilla' in url.lower():
            return match.group(0)
        return match.group(0).replace(url, CLICKADILLA)
    
    text = re.sub(
        r'(?:VAST_TAG|vastTagUrl|vast_tag|vastUrl|vast_url)\s*[=:]\s*["\'](https?://[^"\']+)["\']',
        lambda m: fix_vast_url(m) if 'yomeno' not in m.group(1).lower() and 'clickadilla' not in m.group(1).lower() else m.group(0),
        text
    )
    
    if text != original:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)
            return True
        except:
            return False
    return False

def main():
    base_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    modified = 0
    checked = 0
    for root, dirs, files in os.walk(base_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            checked += 1
            if is_binary_file(fpath):
                continue
            if replace_in_file(fpath):
                rel = os.path.relpath(fpath, base_dir)
                print(f"Modified: {rel}")
                modified += 1
    print(f"Checked {checked} files, modified {modified}")

if __name__ == '__main__':
    main()
