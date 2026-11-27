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
if [[ "${STABILIZE_OPENINGS:-false}" == "true" ]]; then
  PLAN="$WORK/stabilized-modules/plan.json"
  python3 tools/stabilize_confirmed_ads.py "$BASE" "$WORK/unsigned.apk" \
    --work "$WORK/stabilized-modules" --report "$OUT/source-preservation.json"
  python3 "$WORK/stabilized-modules/reference_tests.py" "$WORK/stabilized-modules"
  python3 tools/test_stabilized_openings.py --original "$WORK/stabilized-modules"
elif [[ "${CONFIRMED_REFERENCE:-false}" == "true" ]]; then
  PLAN="$WORK/confirmed-modules/plan.json"
  python3 tools/restore_confirmed_tracking.py "$BASE" "$WORK/unsigned.apk" \
    --work "$WORK/confirmed-modules" --report "$OUT/source-preservation.json"
  python3 "$WORK/confirmed-modules/reference_tests.py" "$WORK/confirmed-modules"
  python3 tools/test_confirmed_tracking.py --original "$WORK/confirmed-modules" --base "$BASE"
elif [[ "${MINIMAL_CLICKADILLA:-false}" == "true" ]]; then
  PLAN="android-build/clickadilla-minimal-plan.json"
  python3 tools/patch_minimal_clickadilla.py "$BASE" "$WORK/unsigned.apk" \
    --work "$WORK/minimal-modules" --report "$OUT/source-preservation.json" --source "${VAST_SOURCE:-clickadilla}"
  python3 tools/test_minimal_clickadilla.py --original "$WORK/minimal-modules" --base "$BASE" --source "${VAST_SOURCE:-clickadilla}"
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
if [[ "${STABILIZE_OPENINGS:-false}" == "true" ]]; then
  mkdir -p "$WORK/signature-reference"
  gh release download smarted-original-ads-46028834505-1 --pattern signature.txt --dir "$WORK/signature-reference" --clobber
  diff <(grep 'Signer #1 certificate SHA-256 digest:' "$WORK/signature-reference/signature.txt") \
       <(grep 'Signer #1 certificate SHA-256 digest:' "$OUT/signature.txt")
fi
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

if [[ "${MINIMAL_CLICKADILLA:-false}" == "true" && "${STABILIZE_OPENINGS:-false}" != "true" ]]; then
  cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTED ORIGINAL DROPBOX — FONTE VAST RESTAURADA / DIAGNOSTICO DE ENTREGA / TESTE
Fonte: $(git rev-parse HEAD)
Base: /SMARTEDTV UNIVERSAL/SMARTEDTV.apk, smartedtv.full 1.0.161, ARM32+ARM64.
Hash Dropbox: 03c2b45efbe3256e6c11f8cc9809babe133a90b180eb007cf5908f597643e277
APK reconstruido a partir do original, nao do APK experimental anterior.
Somente tres entradas: ads_vast.py, smart_ads.py (tag/motor) e ads_tracking.py (novo).
Fonte selecionada: ${VAST_SOURCE:-clickadilla}.
Original: https://bid.onclckstr.com/vast?spot_id=6155985 (extraida do APK, sem trocar apenas o dominio).
Clickadilla, somente se selecionada explicitamente: https://vast.yomeno.xyz/vast?spot_id=1508180.
Sem fallback automatico entre spots/redes; sem parametros/IDs inventados.
VAST em todos os dispositivos; selecao de AdMob nao utilizada neste teste.
Wrapper + InLine: Impression, Tracking e Error herdados do ramo selecionado; macros e UA runtime nos pixels; TLS verificado minimo 1.2.
Tracking: impression/start so apos progresso observado; complete nao e sintetizado em stall/stop; skip somente por callback nativo de stop.
Retirado o corte antecipado de 1,5s do fim. Aguarda fim observado pelo player ou tempo integral, sem sintetizar complete em falha.
Player Kodi, _tocar, MediaFile, watchdogs originais (45s maximo, stall 6s, sem quadro 2,5s), fullscreen, MonitorPreRoll, retomada, VIP, pagamento, skin, welcome, links e inicializacao preservados.
Diagnostico local SmartAdsDelivery identifica requisicao/resposta/sem-criativo/no-fill e resultado, sem URLs de stream/tokens.
Ambas as fontes responderam VAST vazio nas consultas de comparacao; esta restauracao nao garante fill nem conta impressoes sem video.
Frequencia ORIGINAL preservada, inclusive intervalo de 2 minutos. Este perfil nao inclui os ajustes de uma tentativa por abertura dos APKs anteriores.
Nao inclui ads_resume.py nem os watchdogs/gates/guardas de menu novos das tentativas anteriores.
Relatorios source-preservation.json e preservation.json conferem o escopo contra o APK original.
Testes automatizados sao doubles, nao execucao Android; imagem/audio/toque e impressao no painel ainda NAO validados em aparelho.
Assinatura de teste/debug; pode nao atualizar instalacao assinada por outra chave. Fazer backup antes de remover qualquer instalacao.
O APK oficial no Dropbox nao foi substituido. Esta e uma prerelease separada para teste.
EOF
fi

if [[ "${CONFIRMED_REFERENCE:-false}" == "true" && "${STABILIZE_OPENINGS:-false}" != "true" ]]; then
  python3 - "$WORK/confirmed-modules/reference-9436b5e.apk" "$OUT/SMARTEDTV-universal.apk" "$OUT/reference-preservation.json" <<'PYREF'
import json, sys
from pathlib import Path
sys.path.insert(0, 'tools')
from apk_preservation import compare
from restore_confirmed_tracking import AD, HELPER, REFERENCE
report = compare(sys.argv[1], sys.argv[2], {AD, HELPER})
report['reference_commit'] = REFERENCE
Path(sys.argv[3]).write_text(json.dumps(report, indent=2) + '\n')
print('::notice title=Final APK versus confirmed reference::' + json.dumps(report))
PYREF
  cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTED — BASE CONFIRMADA 9436b5e RESTAURADA / SOMENTE TRACKING
Fonte deste APK: $(git rev-parse HEAD)
Referencia confirmada pelo usuario: build 45996397116, commit 9436b5ef63fe1e4d569328990c92ab1514ce9b0b.
Todos os modulos da referencia foram reconstruidos com o patcher exato daquela revisao.
Tag mantida SEM ALTERACAO: https://vast.yomeno.xyz/vast?spot_id=1508180
Diferencas permitidas em relacao a referencia: tracking em ads_vast.py e helper novo ads_tracking.py.
Tracking: heranca selecionada Wrapper/InLine de Impression/Tracking/Error, macros e UA real nos pixels.
Requisicoes da tag, headers, TLS, MediaFile, player, callbacks, tempos, retomada e frequencia iguais a referencia.
Controle AST de reproduzir identico, exceto expansao de macros no emissor Error.
Smart_ads.py, ads_regra.py e ads_admob.py identicos byte a byte a referencia.
Sem bid.onclckstr.com/spot 6155985, watchdog 3s, retomada nova, menus ou diagnostico de entrega dos builds posteriores.
Regra da referencia: uma tentativa por abertura de canal/filme/episodio, sem intervalo de dois minutos; VIP isento; AdMob inerte.
Skin, welcome, links, pagamento, manifesto, recursos, bibliotecas e inicializacao iguais a referencia.
reference-preservation.json compara TODAS as entradas com a referencia, alem da comparacao com o APK base original.
Este build nao fez novas consultas reais de anuncios. Testes de tracking/player sao doubles, nao validacao fisica de imagem/audio ou painel.
Universal ARM32+ARM64. Assinatura de teste/debug; fazer backup antes de remover qualquer instalacao.
APK oficial do Dropbox nao foi substituido. Nenhum PR foi mesclado.
EOF
fi

if [[ "${STABILIZE_OPENINGS:-false}" == "true" ]]; then
  python3 - "$WORK/stabilized-modules/reference-9436b5e-tracking.apk" "$OUT/SMARTEDTV-universal.apk" <<'PYREPORT'
import json, sys
from pathlib import Path
sys.path.insert(0, 'tools')
from apk_preservation import compare
from stabilize_confirmed_ads import PREFIX
report = compare(sys.argv[1], sys.argv[2], {PREFIX + name for name in ('ads_vast.py', 'smart_ads.py', 'ads_openings.py')})
Path('dist/reference-preservation.json').write_text(json.dumps(report, indent=2) + '\n')
print('::notice title=Signed APK versus confirmed reference with restored tracking::' + json.dumps(report))
PYREPORT
  cat > "$OUT/INSTALLATION.txt" <<EOF
SMARTEDTV — 9436b5e + TRACKING RESTAURADO + ESTABILIZACAO POR ABERTURA (TESTE)
Fonte: $(git rev-parse HEAD)
Referencia obrigatoria: build 45996397116 / 9436b5e, reconstruida antes da camada restrita.
Tag exata: https://vast.yomeno.xyz/vast?spot_id=1508180 — sem parametros novos ou outro provedor.
Uma oportunidade por abertura real, incluindo reabertura, fim VOD/episodio e Home; sem cooldown.
Ledger em memoria deduplica callbacks/retorno nativo; flags persistidas antigas so sao limpas numa nova abertura aceita.
Stop fecha a geracao mesmo se isPlayingVideo ainda apresentar estado antigo. Reconexao live por Ended nao a fecha.
Observador passivo de bordas de video/Home usa waitForAbort; cobre callback AV ausente/cedo no cold-start.
Sem comandos play/seek/pause/menu nesse observador; Player.HasMedia preserva pausa/buffering e a excecao de reconexao live.
Flag de Stop cerca somente o ultimo caminho; troca direta A->B sem amostra sem midia libera a nova abertura.
Metadados ainda indisponiveis sao relidos localmente, sem repetir request da tag apos um claim.
Selecao nativa de compatibilidade/saude restaurada: AdMob compativel prioritario, VAST se incompativel.
provider-selected, attempt-blocked e blocking-state-reset explicam os gates antes da tag.
Sem lock de elegibilidade durante rede/anuncio/retomada; trabalho de VAST e pixels permanece fora do callback.
VAST nativo nao espera recuperar foco Android como um anuncio externo. Retomada evita seek redundante, sobretudo em zero.
Confirmacao de seek considera o avanco monotonicamente transcorrido; o relogio do filme nao precisa ficar congelado no alvo.
Ordem de rotas/proxy/plugin, MediaFile, tag/headers/TLS, callbacks do player e watchdogs sao os da referencia.
Mapping Wrapper/InLine, macros, UA real e eventos existentes preservados; complete apenas no fim observado.
Logs [SmartAdsOpening]: opening-claimed, vast-request/response, creative-selected, ad-start-observed,
impression-queued, tracking-event-queued, tracking-http-response/failure, ad-player-released,
resume-begin/route/content-released e cycle-finished. Sem URLs/tokens. HTTP 2xx nao comprova contagem no painel.
No-fill/falha consome tentativa, nao impressao. Nao ha criativo em cache ou impressao simulada.
Testes automatizados de ciclo sao doubles; nao equivalem a ciclos Android nem prova de imagem/audio/tracking do provedor.
Android: consultar docs/STABILIZED_OPENINGS_VALIDATION.md e o run de validacao; instalacao nao prova reproducao.
Preservacao integral das demais entradas do APK verificada em preservation.json/reference-preservation.json.
Mesmo pacote smartedtv.full, ARM32+ARM64 e chave de teste em cache dos builds anteriores.
A chave original de distribuicao nao esta disponivel; pode nao atualizar instalacao oficial. Fazer backup antes de remover.
VIP, outros modulos, skin/welcome/pagamento/inicializacao/bibliotecas nao alterados por esta camada.
Nenhum PR mesclado; APK oficial Dropbox nao substituido.
EOF
fi
