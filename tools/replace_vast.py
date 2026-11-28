#!/usr/bin/env python3
"""Replace ALL HilltopAds references with ClickAdilla in text files under a directory.
This is aggressive - replaces any occurrence of hilltop-containing URLs/domains."""
import os, re, sys

CLICKADILLA = "https://vast.yomeno.xyz/vast?spot_id=1508180"
BINARY_EXTS = {".so", ".dex", ".class", ".png", ".jpg", ".jpeg", ".gif", 
               ".webp", ".mp4", ".mp3", ".ogg", ".wav", ".ttf", ".otf", 
               ".woff", ".woff2", ".arsc", ".db", ".bin"}

def is_binary_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in BINARY_EXTS:
        return True
    try:
        size = os.path.getsize(filepath)
        if size > 10 * 1024 * 1024:
            return True
    except:
        return True
    return False

def replace_in_file(filepath):
    """Replace hilltop references in a file. Returns True if modified."""
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except:
        return False
    
    if b'hilltop' not in data.lower():
        return False
    
    # Try multiple encodings
    text = None
    used_encoding = None
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            text = data.decode(enc)
            used_encoding = enc
            break
        except:
            continue
    
    if text is None:
        return False
    
    original = text
    
    # 1. Replace full URLs containing hilltop (http/https)
    text = re.sub(
        r'''https?://[^"' <>\]\)\}\\\n\r\t]*hilltop[^"' <>\]\)\}\\\n\r\t]*''',
        CLICKADILLA, text, flags=re.IGNORECASE
    )
    
    # 2. Replace bare domains containing hilltopads (e.g., hilltopads.net, cdn.hilltopads.com)
    text = re.sub(
        r'''[A-Za-z0-9._-]*hilltopads\.[A-Za-z0-9._/-]+[^"' <>\]\)\}\\\n\r\t]*''',
        CLICKADILLA, text, flags=re.IGNORECASE
    )
    
    # 3. Replace bare domains with hilltop in them (e.g., hilltop.example.com/path)
    text = re.sub(
        r'''[A-Za-z0-9._-]*hilltop\.[A-Za-z]{2,}[^"' <>\]\)\}\\\n\r\t]*''',
        CLICKADILLA, text, flags=re.IGNORECASE
    )
    
    # 4. Replace VAST config patterns: key = "value" where value is a non-ClickAdilla URL
    def fix_vast_assignment(match):
        prefix = match.group(1)
        url = match.group(2)
        suffix = match.group(3)
        if 'yomeno' in url.lower() or 'clickadilla' in url.lower():
            return match.group(0)
        return prefix + CLICKADILLA + suffix
    
    # Match patterns like: VAST_TAG = "http://..." or vastTagUrl: 'http://...'
    text = re.sub(
        r'''((?:VAST_TAG|vastTagUrl|vast_tag|vastUrl|vast_url|VAST_URL)\s*[=:]\s*["'])'''
        r'''(https?://[^"']+)'''
        r'''(["'])''',
        fix_vast_assignment, text
    )
    
    # 5. Replace any URL that mentions ad serving domain patterns commonly used by HilltopAds
    # HilltopAds typically uses URLs like:
    # - https://hilltopads.net/...
    # - https://*.hilltopads.com/...
    # - https://*.hilltopads.net/...
    # - https://v2.hilltopads.com/...
    # Pattern already covered by #2 above
    
    if text != original:
        try:
            with open(filepath, 'w', encoding=used_encoding, errors='replace') as f:
                f.write(text)
            return True
        except Exception as e:
            print(f"  Error writing {filepath}: {e}")
            return False
    return False

def check_remaining(base_dir):
    """Return list of text files still containing 'hilltop'."""
    remaining = []
    binary = []
    for root, dirs, files in os.walk(base_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            if is_binary_file(fpath):
                try:
                    with open(fpath, 'rb') as f:
                        if b'hilltop' in f.read().lower():
                            binary.append(fpath)
                except:
                    pass
                continue
            try:
                with open(fpath, 'rb') as f:
                    if b'hilltop' in f.read().lower():
                        remaining.append(fpath)
            except:
                pass
    return remaining, binary

def main():
    base_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    
    # First pass: replace
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
    
    print(f"\nChecked {checked} files, modified {modified}")
    
    # Second pass: check what remains
    remaining, binary = check_remaining(base_dir)
    
    if remaining:
        print(f"\nWARNING: {len(remaining)} text files still contain 'hilltop':")
        for f in remaining[:20]:
            rel = os.path.relpath(f, base_dir)
            try:
                with open(f, 'rb') as fh:
                    content = fh.read().decode('utf-8', errors='replace')
                for i, line in enumerate(content.split('\n')):
                    if 'hilltop' in line.lower():
                        print(f"  {rel}:{i+1}: {line.strip()[:120]}")
                        break
            except:
                print(f"  {rel}: (could not read)")
    else:
        print("\nAll text files clean!")
    
    if binary:
        print(f"\nBinary files containing 'hilltop' (not modified): {len(binary)}")
        for f in binary[:5]:
            rel = os.path.relpath(f, base_dir)
            print(f"  {rel}")
    
    sys.exit(0)  # Never fail - just report

if __name__ == '__main__':
    main()
