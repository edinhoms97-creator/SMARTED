#!/usr/bin/env python3
"""Build smartedtv/standalone/smartedtv-preview.html from the source files.

Inlines css/styles.css, js/*.js and assets/* (as data URIs) into a single
offline HTML file. Run from the repository root:

    python3 tools/build-standalone.py
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "smartedtv"
OUT = SRC / "standalone" / "smartedtv-preview.html"


def data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> int:
    html = (SRC / "index.html").read_text(encoding="utf-8")

    css = (SRC / "css" / "styles.css").read_text(encoding="utf-8")
    html = html.replace(
        '<link rel="stylesheet" href="css/styles.css">',
        "<style>\n" + css + "\n</style>",
    )

    for js in ("config.js", "vast.js", "admob.js", "services.js", "app.js"):
        code = (SRC / "js" / js).read_text(encoding="utf-8")
        html = html.replace(
            f'<script src="js/{js}"></script>',
            "<script>\n" + code + "\n</script>",
        )

    # Inline every local asset referenced by <img src> / <link href>.
    def inline(match: "re.Match[str]") -> str:
        attr, rel = match.group(1), match.group(2)
        asset = SRC / rel
        if not asset.exists():
            print(f"warning: asset not found: {rel}", file=sys.stderr)
            return match.group(0)
        return f'{attr}="{data_uri(asset)}"'

    html = re.sub(r'(src|href)="(assets/[^"]+)"', inline, html)

    leftover = re.findall(r'(?:src|href)="(?!data:|https?:|#)[^"]+"', html)
    if leftover:
        print(f"warning: non-inlined references remain: {leftover}", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
