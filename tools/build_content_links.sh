#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD/.cache/content-links"
BASE="$ROOT/base/SMARTEDTV-universal.apk"
OUT="$ROOT/release"
TOOLS="${ANDROID_HOME:?}/build-tools/35.0.0"
KEY="$PWD/.cache/smartedtv-signing/debug.keystore"
mkdir -p "$OUT" "$ROOT/work"
test -f "$KEY"
python3 tools/patch_content_links.py "$BASE" "$ROOT/work/unsigned.apk" --report "$OUT/source-preservation.json"
"$TOOLS/zipalign" -P 16 -f 4 "$ROOT/work/unsigned.apk" "$ROOT/work/aligned.apk"
"$TOOLS/apksigner" sign --ks "$KEY" --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false --out "$OUT/SMARTEDTV-universal.apk" "$ROOT/work/aligned.apk"
"$TOOLS/apksigner" verify --verbose --print-certs "$BASE" > "$OUT/base-signature.txt"
"$TOOLS/apksigner" verify --verbose --print-certs "$OUT/SMARTEDTV-universal.apk" > "$OUT/signature.txt"
diff <(grep 'Signer #1 certificate SHA-256 digest:' "$OUT/base-signature.txt") <(grep 'Signer #1 certificate SHA-256 digest:' "$OUT/signature.txt")
"$TOOLS/zipalign" -P 16 -c -v 4 "$OUT/SMARTEDTV-universal.apk" > "$OUT/zipalign.txt"
"$TOOLS/aapt2" dump badging "$OUT/SMARTEDTV-universal.apk" > "$OUT/badging.txt"
grep -q "'armeabi-v7a'" "$OUT/badging.txt";grep -q "'arm64-v8a'" "$OUT/badging.txt"
python3 - "$BASE" "$OUT/SMARTEDTV-universal.apk" "$OUT/preservation.json" <<'PY'
import json,sys,hashlib
from pathlib import Path
sys.path.insert(0,'tools')
from patch_content_links import compare
r=compare(sys.argv[1],sys.argv[2]);r['apk_sha256']=hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
Path(sys.argv[3]).write_text(json.dumps(r,indent=2)+'\n')
print('::notice title=Content signed APK audit::'+json.dumps(r))
PY
(cd "$OUT" && sha256sum SMARTEDTV-universal.apk > SMARTEDTV-universal.apk.sha256)
