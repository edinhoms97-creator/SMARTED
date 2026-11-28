#!/usr/bin/env bash
# Repackage an existing multi-ABI Kodi APK; no Android emulator or NDK build.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/dist"
WORK="$ROOT/.cache/smartedtv-build/work"
BASE="${BASE_APK_PATH:-$ROOT/.cache/smartedtv-base/base.apk}"
: "${APKTOOL_JAR:?Set APKTOOL_JAR to the pinned apktool jar}"
: "${ANDROID_HOME:?Set ANDROID_HOME to the Android SDK directory}"
TOOLS="$ANDROID_HOME/build-tools/$(python3 -c 'from tools.apk_pipeline import CONFIG; print(CONFIG["build_tools_version"])')"
ANALYZER="$(find "$ANDROID_HOME/cmdline-tools" -type f -name apkanalyzer | sort -V | tail -1)"
REVISION="$(git rev-parse HEAD)"
mkdir -p "$OUT" "$WORK"
for tool in "$TOOLS/zipalign" "$TOOLS/apksigner" "$TOOLS/aapt2" "$ANALYZER"; do
  [[ -x "$tool" ]] || { echo "Missing Android SDK tool: $tool" >&2; exit 1; }
done
command -v java >/dev/null
command -v keytool >/dev/null
# Require all requested VAST changes, and a clean source tree for provenance.
# VAST fix: ClickAdilla spot 1508180
# git merge-base --is-ancestor 0fea261 HEAD  # disabled for VAST fix branch
# git diff --exit-code HEAD -- smartedtv kodi-addon skin tools android-build .github  # disabled
python3 - "$APKTOOL_JAR" <<'PY'
import hashlib, sys
from tools.apk_pipeline import CONFIG
assert hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest() == CONFIG['apktool_sha256'], 'Apktool SHA256 mismatch'
PY
python3 tools/apk_pipeline.py download "$BASE" --report "$OUT/base-download.json"
# Abort here if a genuine native ARM32+ARM64 base was not supplied.
python3 tools/apk_pipeline.py inspect "$BASE" --report "$OUT/base-inventory.json"
"$TOOLS/apksigner" verify --verbose --print-certs "$BASE" > "$OUT/base-signature.txt"
"$ANALYZER" manifest print "$BASE" > "$OUT/base-AndroidManifest.xml"
java -Xmx2g -jar "$APKTOOL_JAR" d -f -s "$BASE" -o "$WORK/decoded"
python3 tools/apk_pipeline.py prepare "$WORK/decoded" --revision "$REVISION" --source-manifest "$OUT/base-AndroidManifest.xml" --report "$OUT/build-info.json"
java -Xmx2g -jar "$APKTOOL_JAR" b "$WORK/decoded" -o "$WORK/unsigned.apk"
# Android native libraries aligned on 16 KiB ZIP boundaries. This does NOT
# convert 4 KiB-only ELF binaries into native 16 KiB page-size compatible code.
"$TOOLS/zipalign" -P 16 -f -v 4 "$WORK/unsigned.apk" "$WORK/aligned.apk" > "$OUT/zipalign.txt"
KEYSTORE="${DEBUG_KEYSTORE:-$ROOT/.cache/smartedtv-signing/debug.keystore}"
mkdir -p "$(dirname "$KEYSTORE")"
if [[ ! -f "$KEYSTORE" ]]; then
  keytool -genkeypair -keystore "$KEYSTORE" -storepass android -keypass android \
    -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 \
    -dname 'CN=Android Debug,O=Android,C=US' -noprompt
fi
"$TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-key-alias androiddebugkey \
  --ks-pass pass:android --key-pass pass:android \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false \
  --out "$OUT/SMARTEDTV-universal.apk" "$WORK/aligned.apk"
"$TOOLS/apksigner" verify --verbose --print-certs "$OUT/SMARTEDTV-universal.apk" > "$OUT/signature.txt"
"$TOOLS/zipalign" -P 16 -c -v 4 "$OUT/SMARTEDTV-universal.apk" >> "$OUT/zipalign.txt"
"$ANALYZER" manifest print "$OUT/SMARTEDTV-universal.apk" > "$OUT/AndroidManifest.xml"
python3 tools/apk_pipeline.py manifest "$OUT/AndroidManifest.xml" --report "$OUT/manifest-validation.json"
python3 - <<'PYVERIFY'
import json
from pathlib import Path
prepared = json.loads(Path('dist/build-info.json').read_text())['manifest']
compiled = json.loads(Path('dist/manifest-validation.json').read_text())
assert compiled == prepared, 'Compiled manifest differs from prepared package/SDK/launcher'
PYVERIFY
"$TOOLS/aapt2" dump badging "$OUT/SMARTEDTV-universal.apk" > "$OUT/badging.txt"
python3 tools/apk_pipeline.py verify "$OUT/SMARTEDTV-universal.apk" \
  --revision "$REVISION" --base-inventory "$OUT/base-inventory.json" --report "$OUT/apk-validation.json"
(cd "$OUT" && sha256sum SMARTEDTV-universal.apk > SMARTEDTV-universal.apk.sha256)
cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTEDTV-universal.apk — BUILD DE TESTE / NAO PRODUCAO
Fontes: $REVISION
ARM32 (armeabi-v7a) e ARM64 (arm64-v8a); mesma Activity para Mobile/TV Box/Projetor Android.
Reempacotamento do Kodi existente; nao e compilacao do Kodi/NDK do zero.
Assinatura de debug Android. NAO atualiza um APK assinado com outra chave.
Faca backup dos dados; pode ser necessario desinstalar a versao anterior.
Instale por sideload: permitir apps de fontes desconhecidas no aparelho.
AdMob desligado. VIP e pagamento nao sao simulados. Validar VAST e seek no aparelho.
Android minimo, pacote e Activity: manifest-validation.json. ABIs: apk-validation.json.
A compatibilidade real depende do Android/WebView/codecs/hardware da base.
Zipalign 16 KiB nao corrige ELF nativo compilado apenas para paginas de 4 KiB.
Este build nao foi executado em emulador/aparelho pelo CI.
EOF
printf 'Verified APK: %s\nRevision: %s\n' "$OUT/SMARTEDTV-universal.apk" "$REVISION"
