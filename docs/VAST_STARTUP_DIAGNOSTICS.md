# VAST: startup 3,5 s, fallback MP4 e diagnóstico no aparelho

> **Histórico, não é a implementação atual:** startup 3,5 s, fallback MP4 e diagnóstico persistente foram retirados a pedido do usuário. Estado atual: [VAST_BASE_TRANSITION.md](VAST_BASE_TRANSITION.md).

## O que foi comprovado sobre 311450b

Inspeção estática/redigida do original: [run 46012855736](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46012855736), sem executar código do APK/provider.

- `_tocar` apenas envia `PlayerControl(RepeatOff)` e `PlayMedia` ao Kodi e recupera fullscreen. Não conecta o MP4 em Python nem espera sua reprodução. Esta função **continua original**, sem outro player/overlay/atividade.
- O `reproduzir` em `311450b` aguardava até 8 s por `isPlayingVideo()` e um caminho diferente do conteúdo. Essa condição não confirma quadro/progresso. Depois que o caminho era aceito, o relógio congelado podia gerar aborto pelo watchdog de 3 s. São causas de espera/aborto verificáveis no código, não prova do erro específico de decoder do aparelho.
- A escolha de MediaFile retornava somente um MP4; as alternativas do mesmo criativo eram descartadas. Também permitia até 1080p/5000 kbps.
- A inicialização da regra já removia tentativa/cooldown de outro processo. Não foi encontrado um bloqueio permanente intencional depois de falha/no-fill. Sem log do aparelho não se pode concluir se a ausência após reinício foi no-fill, rede/TLS, VIP, callbacks ausentes, reinício apenas da Activity com o processo vivo ou falha do monitor. **Limite por IP não foi comprovado.**

Os checks GitHub consultados de `311450b` estavam aprovados; não havia check separado chamado `verify` no HEAD documental seguinte. Foi acrescentado um comando reproduzível `npm run verify` e o workflow manual agora usa esse mesmo comando. Um erro de check externo diferente ainda exige seu URL/log para diagnóstico específico.

## Comportamento desta revisão

1. O player continua sendo o original do APK.
2. Startup limitado a **3,5 s a partir do despacho**, incluindo conexão/decoder: é necessário o caminho do anúncio, vídeo ativo, relógio **acima de 0,1 s e avançando**, sem indicação de áudio sem quadro. `isPlayingVideo`/AVStarted/headers isolados não bastam.
3. Sem progresso real no prazo: `stop()`, Error 405 expandido e registro `startup-timeout`. Sem impressão/start falsos. O core Kodi processa stop/play de forma assíncrona; o tempo efetivo de liberação de uma superfície de hardware ainda depende do aparelho.
4. Depois de iniciado: watchdog de **3 s sem avanço**, margem de **5 s sobre a duração**, teto global de 35 s incluindo XML/wrappers/tentativas. Sem auto-PlayPause ou novos hooks de clique.
5. Seleção progressiva MP4/AVC baseline/main, até **1280×720 e 3000 kbps** quando declarados; preferência por 720p moderado/480p. HEVC/AV1/VPx, perfis incompatíveis, mídia pesada e delivery streaming são recusados. Metadados ausentes não equivalem a codec comprovado; continuam protegidos pelo watchdog.
6. Até três URLs distintas do **mesmo InLine/Linear selecionado**, na ordem segura. Se o primeiro arquivo falhar **antes do início real**, tenta o próximo, sem refazer a consulta nem reabrir o conteúdo entre eles. Depois de impressão/início real não tenta outro criativo/arquivo, evitando duplicar impressão. Toda a sequência compartilha o teto da sessão.
7. Cada falha de mídia tenta seu Error; todos os Impression dos Wrappers/Inline selecionados continuam herdados. Macros CACHEBUSTER/CACHEBUSTING e UA real continuam ativos. Pixel emitido não prova recebimento pelo provedor.
8. Sucesso ou fim das tentativas: restaura diretamente o snapshot original (stream, ListItem/metadados, timestamp VOD; live sem seek), sem chamar plugin/seleção de servidor. O snapshot nunca é substituído pelo relógio da primeira peça que falhou. Alternativas de conteúdo ainda se limitam às já resolvidas; não há resolver genérico de hoster.
9. No-fill/rede/timeout da tag não substituem nem param o conteúdo.

A proteção anterior por hash da AST fixava exatamente a janela antiga de 8 s e, portanto, foi substituída por testes comportamentais explícitos para o novo prazo autorizado de 3,5 s. Não se desativou o verify nem se ignoram falhas.

## Como verificar no aparelho

Arquivo principal: **`special://temp/smarted_vast.log`**. Rotação anterior: **`special://temp/smarted_vast.log.1`**.

No gerenciador de arquivos do Kodi/SMARTED, abra a pasta `special://temp/` e copie esses arquivos após reproduzir o problema. O caminho físico varia com a distribuição; não se presume uma pasta Android externa específica. Nenhuma skin/XML/tela de configuração foi alterada e não há toast automático. O diagnóstico escolhido é o arquivo persistente.

O arquivo é JSONL com UTC, sessão aleatória local por processo e fases:

- `boot`: `VAST MONITOR READY` / `VAST MONITOR OFF`.
- `gate`: `VAST SKIP` + motivo `vip`, `same-session`, `same-opening`, `busy`, `no-video`, `no-path` ou `return`.
- `request`: `VAST REQUEST`, confirma que houve uma nova tentativa.
- `tag`: HTTP real quando disponível e categoria de falha de transporte.
- `media`: resultado de cada arquivo, índice, dimensões/bitrate declarados e tempo.
- `result`: resultado final e `retomada_confirmada` quando houve retomada.

Resultados principais:

| Status | Interpretação |
|---|---|
| `VAST OK (15.1s)` | exemplo de término/skip após início real; conferir `motivo` |
| `VAST NO-FILL (HTTP 200 vazio)` | resposta HTTP 200 com corpo vazio, não erro do decoder |
| `VAST NO-FILL (HTTP 200 sem anuncio)` | XML sem anúncio utilizável/sem MediaFile declarado |
| `VAST TIMEOUT` | timeout da consulta VAST |
| `VAST NETWORK FAIL` | rede/TLS/HTTP; `http_status` diferencia 403/5xx quando disponível |
| `VAST MEDIA FAIL` + `startup-timeout` | MP4 sem progresso real em 3,5 s |
| `VAST MEDIA FAIL` + `sem-midia-compativel` | MediaFiles existem, mas nenhum passa o filtro |
| `VAST CONTENT NOT READY` | não havia snapshot resolvido seguro; conteúdo não foi interrompido |

Uma sessão nova após reinício com `boot` mas sem `request` deve ser lida junto dos `gate`. A mesma sessão local indica que o processo Python continuou vivo. Ausência de novas linhas pode indicar que o monitor não foi chamado ou que a gravação local falhou; nesse último caso há aviso genérico no log Kodi.

Somente campos permitidos são gravados. Sem URLs de filme/anúncio/pixel, tokens, IP, IDs de conta, credenciais ou payload XML. Limite: 128 KiB + uma rotação. Falha de gravação nunca bloqueia a reprodução. O arquivo não é enviado automaticamente a nenhum serviço.

## Validação

`npm run verify`: testes JS/Python, startup, fallback, diagnóstico/rotação/redação, reinício com estado anterior, retomada, regras de abertura, botões, gates de preservação e sintaxe. O build repete os testes de startup/diagnóstico contra os **módulos do original corrigido** e verifica assinatura, alinhamento e todas as entradas do APK.

Novo módulo isolado `ads_diagnostics.py`: nono caminho autorizado do plano. Manifesto, recursos/skin, serviço de startup e libs não são modificados. AdMob permanece inerte/desativado.

Sem aparelho físico neste ambiente: testes determinísticos não certificam decodificação/superfície de hardware, disponibilização de anúncios nem contabilização de pixels reais.
