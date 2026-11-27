# Anúncios SMARTEDTV — implementação e validação

## Estado desta entrega

- Tag principal: `https://vast.yomeno.xyz/vast?spot_id=1508180` (Clickadilla #1508180).
- Web: `smartedtv/js/vast.js`, conectado a `ads.startSession()`.
- Kodi: `vast.py` (transporte/parser) + `vast_player.py` (player/tracking/retomada), conectados à confirmação da janela welcome em uma thread de trabalho.
- AdMob separado: `smartedtv/js/admob.js`, **`admob.enabled: false`**; IDs fornecidos em `config.js`. Sem SDK/bridge Android neste repositório. Ver [ADMOB.md](ADMOB.md).
- Atualização de build: **APK de teste reempacotado e publicado**, com fontes web/addon desta entrega e runtime nativo da base preservado. Sem compilação Kodi/NDK do zero. Download e validações em [BUILD_APK.md](BUILD_APK.md). A tag real e o hardware ainda precisam de validação.

## Transporte por plataforma

**Kodi/Python:** `ssl.create_default_context()` com verificação de certificado/hostname e mínimo TLS 1.2; User-Agent Chrome Android, Accept XML, Accept-Language pt-BR, timeout de socket de 8 segundos. Não há `verify=False` ou contexto TLS inseguro. Beacons usam o mesmo contexto e são enviados fora do caminho de reprodução.

**Browser/WebView:** `fetch()` usa a segurança TLS e o User-Agent reais da plataforma. JavaScript **não pode impor mínimo TLS 1.2 nem forçar o UA Chrome Android**. O shell Android/WebView precisa ser atualizado/configurado para cumprir isso em aparelhos antigos. A tag também precisa permitir CORS; CORS bloqueado é tratado como falha de rede e cai no fallback, não como anúncio exibido. O timeout web de 8 segundos cobre headers e corpo mesmo sem `AbortController`.

## Ciclo de reprodução

1. Captura posição e estado de pausa do VOD antes da requisição; pausa o conteúdo enquanto resolve o anúncio.
2. XML vazio, `<VAST/>`, ausência de `<Ad>`, XML inválido, rede ou timeout liberam o conteúdo sem overlay persistente. Erros não impedem a retomada.
3. Uma URL `<Error>` dentro de um anúncio válido é tracking de falha, **não no-fill**.
4. Reproduz o primeiro anúncio linear Inline disponível e prefere MP4. Não implementa ad pods nem resolução recursiva de Wrappers nesta versão; respostas sem mídia direta caem no fallback.
5. Impression/start são emitidos após o começo efetivo da mídia (`playing` / `onAVStarted`), não na busca da tag. Quartis e complete são deduplicados. Interrupção não gera complete; falha de mídia gera error 405. URLs de tracking são beacons best-effort, sem garantia de recebimento pelo provedor.
6. Web: skipoffset em segundos ou porcentagem; botão desabilitado até o limite, com checagem também no handler. D-PAD fica no overlay e o foco volta ao controle anterior.
7. Watchdog de 12 segundos cobre falha de início e ausência de progresso no meio da mídia; remove o anúncio e restaura o conteúdo.
8. Retomada web: mantém o mesmo elemento de vídeo, restaura `currentTime`, aguarda `seeked` quando necessário e confere diferença ≤ 50 ms. Fallback de confirmação: 1,5 s. `resumeConfirmed: false` informa seek não confirmado; não é mascarado como sucesso. A posição é conferida antes de dar play. Um VOD originalmente pausado permanece pausado.
9. Retomada Kodi: preserva URL + ListItem + posição, reabre a fonte e solicita seek, conferindo posição por até 3 s (tolerância 250 ms, devido à API/amostragem Kodi). Não declara precisão absoluta de frame. Streams ao vivo/não-seekable podem retornar `resumeConfirmed: false`.

## Integração ao player principal

A página welcome é uma interface de entrada, **não contém catálogo/canal ou URL de VOD principal**. Ao usá-la sozinha, o fallback volta à welcome; não inventamos um canal.

No player web existente:

```js
const result = await SmartedtvServices.get("ads").startSession({
  resumeTarget: { video: elementoVideoDoVOD },
  onEvent: (evento, url) => console.debug(evento, url)
});
// O módulo já restaura este vídeo. Não inicie outra fonte antes de concluir.
// Se não houver resumeTarget, o chamador deve iniciar seu canal após a Promise.
// Avaliar result.resumeConfirmed / result.resumedAt para diagnosticar seek.
```

No addon principal Kodi, chamar `vast_player.run_session(on_fallback=iniciar_canal_selecionado)` em worker. O callback atende o caso sem conteúdo em reprodução. A welcome isolada apenas fecha ao final; o addon principal ainda precisa fornecer o destino quando não há canal/VOD ativo.

## Testes automatizados

Na raiz, Node 22 e Python 3:

```sh
npm ci
npm test
npm run build:standalone
```

- `tools/test-vast.js`: 28 verificações do parser/helpers.
- `tools/test-vast-player.js`: 10 testes de ciclo com DOM/mídia/relógio simulados, incluindo timeout sem AbortController, corpo travado, pulo antecipado, seek confirmado/não confirmado, tracking, stall e flag AdMob.
- `tools/test_vast_py.py`: 23 verificações do parser e fallback Python.
- `tools/test_vast_kodi.py`: 6 testes com API Kodi simulada, incluindo conclusão, interrupção, no-fill, stall, seek falho e TLS verificado.

O diagnóstico XML no stderr do primeiro teste é intencional (fixture de XML malformado). Estes testes não certificam reprodução/codecs em aparelho real.

## Validação manual pendente

Servir o repositório e abrir `/smartedtv/demo-vast.html`:

```sh
python3 -m http.server 8000 --bind 0.0.0.0
```

- Tag real (padrão): observar carregamento, CORS, mídia, quartis e complete no Network e no log.
- `/smartedtv/demo-vast.html?tag=testdata/vast-nofill.xml`: retorno imediato ao VOD sem overlay.
- Trocar para `vast-empty.xml` ou `vast-error.xml`: mesmo fallback limpo.
- DevTools offline: validar falha de rede e retorno ao VOD.
- Com anúncio real: iniciar VOD, ir a 00:42 e disparar anúncio; conferir alvo/posição e `resumeConfirmed`, inclusive após pular e após falha da mídia.
- Repetir no Kodi Omega/Android TV e no Chrome/WebView mobile; testar D-PAD, autoplay e vídeo pausado. Um bloqueio de autoplay pode exigir gesto do usuário.

`vast-with-ad.xml` é um fixture sintético do parser: as URLs `example.com` **não são um criativo reproduzível**. Para reprodução, usar a tag real ou um criativo de teste autorizado.

A rede deste sandbox não permite acessar o host da tag, e não há runtime Kodi instalado. Portanto **a tag real, os beacons recebidos pela Clickadilla e a retomada em hardware não foram validados aqui**. A aprovação do VAST e a ativação posterior do AdMob dependem desses testes.
