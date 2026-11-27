#!/usr/bin/env bash
# Exact original SMARTEDTV; reviewed ad/APK-link ZIP patch. NO skin/startup/resource rebuild.
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
python3 tools/test_ad_openings.py --original "$WORK/patched-modules"
python3 tools/test_ads_regressions.py --original "$WORK/patched-modules"
python3 tools/test_resolved_resume.py --original "$WORK/patched-modules"
python3 tools/test_vast_tracking.py --original "$WORK/patched-modules"
python3 tools/test_apk_links.py --original "$WORK/patched-modules"
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
# EVERY entry other than the 8 reviewed ad/link files/signatures must be identical.
python3 tools/apk_preservation.py "$BASE" "$OUT/SMARTEDTV-universal.apk" --report "$OUT/preservation.json"
(cd "$OUT" && sha256sum SMARTEDTV-universal.apk > SMARTEDTV-universal.apk.sha256)
cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTED ORIGINAL — WATCHDOG VAST + LINKS DO APK / BUILD DE TESTE
Fonte: $(git rev-parse HEAD)
Base original: smartedtv.full 1.0.161 (APK do link Dropbox fornecido).
Skin, layout, XMLs, service.py, AndroidManifest.xml, resources.arsc e bibliotecas preservados byte a byte.
Somente anuncios (ads_vast, smart_ads, ads_regra, ads_admob inerte, ads_resume, ads_tracking) e links oficiais em vip.py/welcome default.py mudaram.
Classes/metodos de interface originais preservados; somente helper de URL e constantes da welcome corrigidos.
Validacao VIP, pagamento, skin e inicializacao preservados.
Watchdog: progresso a cada 500ms; 3s sem avanco aborta; limite absoluto min(duracao+5s,35s), incluindo inicio do decoder.
MP4 progressivo conservador (ate 1080p/5000kbps), preferencia 720p AVC baseline/main quando declarado.
Baixar/Atualizar abrem SMARTEDTV.apk oficial no Dropbox (dl=1); compartilhar envia/exibe esse mesmo link.
Download/instalacao dependem das permissoes e confirmacoes do Android.
Regra: uma tentativa por abertura de canal/filme/episodio, sem intervalo de 2 minutos.
Pause, seek, reconexao e retorno do anuncio nao repetem a tentativa. No-fill libera o conteudo.
Nenhuma skin, welcome ou servico de inicializacao novo foi instalado.
Retomada usa stream/ListItem resolvidos, sem plugin:// ou seletor; fallback somente entre alternativas resolvidas salvas.
Impressions e eventos dos Wrappers selecionados sao herdados; macros CACHEBUSTING/CACHEBUSTER/RANDOM e User-Agent real do Kodi.
VAST Clickadilla #1508180 em todos os dispositivos; AdMob desativado.
Assinatura de debug: NAO atualiza app assinado com a chave original.
Antes de remover qualquer instalacao, fazer backup dos dados.
Teste em aparelho ainda obrigatorio: nao declarar inicializacao/reproducao aprovadas apenas pelo CI.
Relatorio preservation.json demonstra exatamente os arquivos modificados.
EOF
