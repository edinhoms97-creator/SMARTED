#!/usr/bin/env bash
# Exact current release -> three authorized functions. Never restore historical APK wholesale.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
BASE="$PWD/.cache/history-startup/current/SMARTEDTV-universal.apk"
WORK="$PWD/.cache/history-recovery/patch"
OUT="$PWD/.cache/history-recovery/release"
TOOLS="${ANDROID_HOME:?}/build-tools/35.0.0"
KEYSTORE="$PWD/.cache/smartedtv-signing/debug.keystore"
mkdir -p "$WORK" "$OUT"
test -f "$KEYSTORE"
python3 tools/test_history_recovery.py --apk "$BASE" --out "$OUT/startup-before-after.json" -v
python3 tools/test_vast_single_function.py --apk "$BASE" -v
python3 tools/patch_history_recovery.py "$BASE" "$WORK/unsigned.apk" --report "$OUT/source-preservation.json"
"$TOOLS/zipalign" -P 16 -f 4 "$WORK/unsigned.apk" "$WORK/aligned.apk"
"$TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android \
 --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false \
 --out "$OUT/SMARTEDTV-universal.apk" "$WORK/aligned.apk"
"$TOOLS/apksigner" verify --verbose --print-certs "$BASE" > "$OUT/base-signature.txt"
"$TOOLS/apksigner" verify --verbose --print-certs "$OUT/SMARTEDTV-universal.apk" > "$OUT/signature.txt"
diff <(grep 'Signer #1 certificate SHA-256 digest:' "$OUT/base-signature.txt") <(grep 'Signer #1 certificate SHA-256 digest:' "$OUT/signature.txt")
"$TOOLS/zipalign" -P 16 -c -v 4 "$OUT/SMARTEDTV-universal.apk" > "$OUT/zipalign.txt"
"$TOOLS/aapt2" dump badging "$OUT/SMARTEDTV-universal.apk" > "$OUT/badging.txt"
grep -q "'armeabi-v7a'" "$OUT/badging.txt"; grep -q "'arm64-v8a'" "$OUT/badging.txt"
python3 - "$BASE" "$OUT/SMARTEDTV-universal.apk" "$OUT/preservation.json" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,'tools')
from patch_history_recovery import preservation
r=preservation(sys.argv[1],sys.argv[2]);Path(sys.argv[3]).write_text(json.dumps(r,indent=2)+'\n')
print('::notice title=Recovery signed APK preservation::'+json.dumps(r))
PY
(cd "$OUT" && sha256sum SMARTEDTV-universal.apk > SMARTEDTV-universal.apk.sha256)
cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTED — RECUPERACAO VAST E FLUXO INICIAL / TESTE FISICO
Fonte: $(git rev-parse HEAD)
Base exata atual 46079704676: SHA256 919e97db0929ab90f189c9503722f4a5139feda573a28c96d79973a8e70e6087.
Historico comparado: build 45992589750 (skin original preservada, INTERVALO=120).
SOMENTE ads_vast.exibir e welcome.abrir_tela_entrada/vigiar_inicializacao modificados; demais bytes/funcoes protegidos.
VAST: recupera orcamento historico de ate 8s por HTTP hop, teto compartilhado de 24s para profundidade nativa 2.
Sem sleep, retry artificial de raiz, cooldown, cache vazio ou limite por sessao.
INTERVALO=0 e elegibilidade atual preservados; nunca restaurar regra historica de 120s.
Tag efetiva: https://vast.yomeno.xyz/vast?spot_id=1508249, sem fallback antigo.
Recuperacao de alternativas Wrapper/VMAP/URLs relativas e pareamento MediaFile/duracao/ID preservados.
Tela inicial: retira apenas dois atalhos que iam para Home antes do dialogo (ativacao concluida/reentrada).
Vigia inicial: nao antecipa Home por demora no desenho; dispatcher existente mantem fallback de erro.
Validacao VIP, layout/controles, Home, navegacao, AdMob, tracking, player e retomada NAO alterados.
O perfil 3s/duracao+5s aparece em outro commit, NAO no player do APK-base atual. Player atual preservado byte a byte.
ARM32+ARM64 e assinatura de teste preservados; nao prova posse da chave oficial. Backup antes de desinstalar.
Testes controlados, browser e Android emulado nao equivalem a anuncio no aparelho fisico nem painel aprovado.
Nao se promete fill se a tag devolver VAST vazio. Roteiro e evidencias na release.
Dropbox oficial nao substituido. Nenhum merge.
EOF
cat "$OUT/SMARTEDTV-universal.apk.sha256"
