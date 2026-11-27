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
if [[ "${MINIMAL_CLICKADILLA:-false}" == "true" ]]; then
  PLAN="android-build/clickadilla-minimal-plan.json"
  python3 tools/patch_minimal_clickadilla.py "$BASE" "$WORK/unsigned.apk" \
    --work "$WORK/minimal-modules" --report "$OUT/source-preservation.json"
  python3 tools/test_minimal_clickadilla.py --original "$WORK/minimal-modules" --base "$BASE"
else
  PLAN="android-build/ads-only-plan.json"
  python3 tools/patch_original_ads.py "$BASE" "$WORK/unsigned.apk" \
    --work "$WORK/patched-modules" --report "$OUT/source-preservation.json"
  # Tests against the ORIGINAL parser/functions just patched, not the separate
  # welcome/demo implementation. Test doubles only; no UI or emulator launched.
  python3 tools/test_original_ad_patch.py "$WORK/patched-modules"
  python3 tools/test_ad_openings.py --original "$WORK/patched-modules"
  python3 tools/test_ads_regressions.py --original "$WORK/patched-modules"
  python3 tools/test_resolved_resume.py --original "$WORK/patched-modules"
  python3 tools/test_vast_tracking.py --original "$WORK/patched-modules"
  python3 tools/test_vast_transition_menus.py --original "$WORK/patched-modules"
  python3 tools/test_apk_links.py --original "$WORK/patched-modules"
fi
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
python3 tools/apk_preservation.py "$BASE" "$OUT/SMARTEDTV-universal.apk" --report "$OUT/preservation.json" --plan "$PLAN"
(cd "$OUT" && sha256sum SMARTEDTV-universal.apk > SMARTEDTV-universal.apk.sha256)
cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTED ORIGINAL — CICLO VAST CANAIS/FILMES/EPISODIOS / VALIDACAO EM APARELHO
Fonte: $(git rev-parse HEAD)
Base original: smartedtv.full 1.0.161 (APK do link Dropbox fornecido).
Skin, layout, XMLs, service.py, AndroidManifest.xml, resources.arsc e bibliotecas preservados byte a byte.
Somente anuncios (ads_vast, smart_ads, ads_regra, ads_admob inerte, ads_resume, ads_tracking) e links oficiais em vip.py/welcome default.py mudaram.
Player _tocar original; startup ate 8s, progresso a cada 500ms, stall nao pausado 3s, duracao+5s/teto 35s de tempo ativo.
MediaFile e tracking preservados da base bd62cbd; sem fallback MP4, novo filtro ou auto-PlayPause.
Pausa nativa excluida dos watchdogs; fullscreen apenas na transicao, nao a cada amostra.
Monitor instalado verifica AV ja em andamento; identidade por conteudo/sessao; vigia live nao disputa com anuncio enfileirado.
Diagnostico local Kodi: SmartAdsLifecycle, sem URLs/tokens. Registra posicao, ultimo progresso observado, deteccao e ultimo callback antes da limpeza.
Nao comprova decoder/audio/surface nem recebimento/contagem de impressoes no painel.
Mapeamento Wrapper/Inline e macros preservados; pixels usam UA real do Kodi. Tag usa headers legados da base.
Apos inicio real do anuncio e retorno confirmado: guarda UI nao bloqueante fecha apenas menus identificados de player/legendas da sessao.
Guarda limitada a 5s, sem alterar os prazos da midia; nao fecha menus de outro filme/VIP/pagamento nem desativa legendas.
Retomada direta via stream/ListItem, sem reexecutar provider/seletor; mesma identidade de abertura na URL de retorno.
Hashes do novo ciclo revisado e da selecao de midia inalterada conferidos no CI.
TESTE ANDROID PRATICO NAO EXECUTADO: sem adb/emulador/SDK/KVM no ambiente desta sessao. Testes Kodi usam doubles.
Validacao VIP, pagamento, skin e inicializacao preservados; AdMob continua desativado.
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

if [[ "${MINIMAL_CLICKADILLA:-false}" == "true" ]]; then
  cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTED ORIGINAL DROPBOX — SOMENTE CLICKADILLA + TRACKING / TESTE
Fonte: $(git rev-parse HEAD)
Base: /SMARTEDTV UNIVERSAL/SMARTEDTV.apk, smartedtv.full 1.0.161, ARM32+ARM64.
Hash Dropbox: 03c2b45efbe3256e6c11f8cc9809babe133a90b180eb007cf5908f597643e277
APK reconstruido a partir do original, nao do APK experimental anterior.
Somente tres entradas: ads_vast.py, smart_ads.py (tag/motor) e ads_tracking.py (novo).
Tag: https://vast.yomeno.xyz/vast?spot_id=1508180 — sem parametros/IDs inventados.
VAST em todos os dispositivos; selecao de AdMob nao utilizada neste teste.
Wrapper + InLine: Impression, Tracking e Error herdados do ramo selecionado; macros e UA runtime nos pixels; TLS verificado minimo 1.2.
Tracking: impression/start so apos progresso observado; complete nao e sintetizado em stall/stop; skip somente por callback nativo de stop.
IMPORTANTE: o corte antecipado de fim do player original foi preservado. Se ele retorna antes do fim real, complete nao e inventado.
Player, _tocar, MediaFile, tempos, fullscreen, MonitorPreRoll, retomada, VIP, pagamento, skin, welcome, links e inicializacao originais preservados.
Frequencia ORIGINAL preservada, inclusive intervalo de 2 minutos. Este perfil nao inclui os ajustes de uma tentativa por abertura dos APKs anteriores.
Nao inclui ads_resume.py nem os watchdogs/gates/guardas de menu novos das tentativas anteriores.
Relatorios source-preservation.json e preservation.json conferem o escopo contra o APK original.
Testes automatizados sao doubles, nao execucao Android; imagem/audio/toque e impressao no painel ainda NAO validados em aparelho.
Assinatura de teste/debug; pode nao atualizar instalacao assinada por outra chave. Fazer backup antes de remover qualquer instalacao.
O APK oficial no Dropbox nao foi substituido. Esta e uma prerelease separada para teste.
EOF
fi
