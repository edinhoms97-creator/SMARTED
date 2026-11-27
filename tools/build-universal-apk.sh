#!/usr/bin/env bash
# Exact original SMARTEDTV; ads-only ZIP patch. NO skin/startup/resource rebuild.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
: "${ANDROID_HOME:?Set ANDROID_HOME}"
TOOLS="$ANDROID_HOME/build-tools/35.0.0"
BASE="$PWD/.cache/smartedtv-base/base.apk"
WORK="$PWD/.cache/smartedtv-ads-only"
OUT="$PWD/dist"
mkdir -p "$WORK" "$OUT"
for tool in apksigner zipalign aapt2; do test -x "$TOOLS/$tool"; done
git diff --exit-code HEAD -- tools android-build .github
python3 tools/apk_pipeline.py download "$BASE" --report "$OUT/base-identity.json"
"$TOOLS/apksigner" verify --verbose --print-certs "$BASE" > "$OUT/base-signature.txt"
"$TOOLS/aapt2" dump badging "$BASE" > "$OUT/base-badging.txt"
python3 tools/patch_original_ads.py "$BASE" "$WORK/unsigned.apk" \
  --work "$WORK/patched-modules" --report "$OUT/source-preservation.json"
# Tests against the ORIGINAL parser/functions just patched, not the separate
# welcome/demo implementation. Test doubles only; no UI or emulator launched.
python3 tools/test_original_ad_patch.py "$WORK/patched-modules"
"$TOOLS/zipalign" -P 16 -f 4 "$WORK/unsigned.apk" "$WORK/aligned.apk"
KEYSTORE="$PWD/.cache/smartedtv-signing/debug.keystore"
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
"$TOOLS/zipalign" -P 16 -c -v 4 "$OUT/SMARTEDTV-universal.apk" > "$OUT/zipalign.txt"
"$TOOLS/aapt2" dump badging "$OUT/SMARTEDTV-universal.apk" > "$OUT/badging.txt"
# This comparison is stronger than comparing selected manifest attributes:
# EVERY entry other than the 3 reviewed ad files/signatures must be identical.
python3 tools/apk_preservation.py "$BASE" "$OUT/SMARTEDTV-universal.apk" --report "$OUT/preservation.json"
(cd "$OUT" && sha256sum SMARTEDTV-universal.apk > SMARTEDTV-universal.apk.sha256)
cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTED ORIGINAL — SOMENTE ANUNCIOS / BUILD DE TESTE
Fonte: $(git rev-parse HEAD)
Base original: smartedtv.full 1.0.161 (APK do link Dropbox fornecido).
Skin, bootstrap, tela inicial, AndroidManifest.xml, resources.arsc e bibliotecas preservados byte a byte.
Apenas ads_vast.py, a selecao de provedor em smart_ads.py e ads_admob.py inerte mudaram.
Nenhuma skin, welcome ou servico de inicializacao novo foi instalado.
VAST Clickadilla #1508180 em todos os dispositivos; AdMob desativado.
Assinatura de debug: NAO atualiza app assinado com a chave original.
Antes de remover qualquer instalacao, fazer backup dos dados.
Teste em aparelho ainda obrigatorio: nao declarar inicializacao/reproducao aprovadas apenas pelo CI.
Relatorio preservation.json demonstra exatamente os arquivos modificados.
EOF
