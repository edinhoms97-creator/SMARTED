#!/usr/bin/env bash
# Isolated build: ONLY ads_vast.exibir over exact previously delivered APK.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
BASE="$PWD/.cache/vast-lab/base/SMARTEDTV-universal.apk"
WORK="$PWD/.cache/vast-lab/patch"
OUT="$PWD/.cache/vast-lab/release"
TOOLS="${ANDROID_HOME:?}/build-tools/35.0.0"
KEYSTORE="$PWD/.cache/smartedtv-signing/debug.keystore"
mkdir -p "$WORK" "$OUT"
test -f "$KEYSTORE" # Never silently generate an incompatible replacement key.
python3 tools/test_vast_single_function.py --apk "$BASE" -v
python3 tools/patch_vast_single_function.py "$BASE" "$WORK/unsigned.apk" --report "$OUT/source-preservation.json"
"$TOOLS/zipalign" -P 16 -f 4 "$WORK/unsigned.apk" "$WORK/aligned.apk"
"$TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-key-alias androiddebugkey \
  --ks-pass pass:android --key-pass pass:android \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false \
  --out "$OUT/SMARTEDTV-universal.apk" "$WORK/aligned.apk"
"$TOOLS/apksigner" verify --verbose --print-certs "$BASE" > "$OUT/base-signature.txt"
"$TOOLS/apksigner" verify --verbose --print-certs "$OUT/SMARTEDTV-universal.apk" > "$OUT/signature.txt"
diff <(grep 'Signer #1 certificate SHA-256 digest:' "$OUT/base-signature.txt") \
     <(grep 'Signer #1 certificate SHA-256 digest:' "$OUT/signature.txt")
"$TOOLS/zipalign" -P 16 -c -v 4 "$OUT/SMARTEDTV-universal.apk" > "$OUT/zipalign.txt"
"$TOOLS/aapt2" dump badging "$OUT/SMARTEDTV-universal.apk" > "$OUT/badging.txt"
grep -q "'armeabi-v7a'" "$OUT/badging.txt"
grep -q "'arm64-v8a'" "$OUT/badging.txt"
python3 tools/apk_preservation.py "$BASE" "$OUT/SMARTEDTV-universal.apk" --report "$OUT/preservation.json" --plan "$OUT/plan.json"
(cd "$OUT" && sha256sum SMARTEDTV-universal.apk > SMARTEDTV-universal.apk.sha256)
cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTED — TESTE RESTRITO VAST 1508249
Fonte: $(git rev-parse HEAD)
Base exata: release 46074593488; SHA256 2b64c443f42902cb07031db1106137a59d852ae39bb8fbd8b9379b8a6d2682bc.
Somente ads_vast.exibir mudou; todos os bytes fora da funcao e todas as demais entradas (exceto assinaturas) preservados.
Tag efetiva fixa: https://vast.yomeno.xyz/vast?spot_id=1508249. Sem fallback antigo.
Cada chamada recebe vast_attempt_id nos logs SmartAdsOpening/recibo.
Percorre alternativas declaradas Wrapper/VMAP e isola cada Linear antes de chamar o seletor nativo.
Mantem midia, duracao, ID e tracking do mesmo criativo; herda apenas o ramo selecionado.
Seletor compartilhado, player e funcoes de pixels nao alterados; sem filtros novos de codec/resolucao.
Nao foi encontrado cache no-fill/limite de sessao dentro de exibir. Nao se declara corrigido gate externo.
Nenhuma alteracao em ads_tracking, AdMob, VIP, player, monitor, Home, retomada ou navegacao.
ARM32+ARM64 preservados e certificado conferido contra o APK-base.
Laboratorio visual inclui chamadas reais e fixtures claramente identificadas. Video fixture e padrao local, nao anuncio real.
Laboratorio Chromium/testes automatizados NAO provam reproducao Kodi Android nem impressao em painel.
Validacao no celular fisico ainda pendente. Nao prometer preenchimento se o servidor retornar VAST vazio.
Mesma assinatura de teste da base; nao e prova de chave oficial. Backup antes de qualquer desinstalacao.
Dropbox oficial nao substituido; prerelease isolada, PR nao mesclado.
EOF
cat "$OUT/SMARTEDTV-universal.apk.sha256"
