# Watchdog Kodi/Android e botões do APK oficial

## Escopo

A base continua sendo exatamente `smartedtv.full` 1.0.161 do Dropbox fornecido. Nenhuma skin, XML de layout, manifesto, biblioteca, serviço de inicialização ou tela welcome alternativa é inserida. Além dos quatro arquivos de anúncios já revisados, apenas ações de link do APK e constantes `APK`/`DROPBOX_URL` de `service.smarted.bootstrap/vip.py`, além do helper de URL e duas constantes na welcome original, podem mudar. O patcher compara a AST restante; validação de licença, cloud e pagamento permanecem intactos.

## Inspeção e problemas tratados

A inspeção somente leitura dos módulos originais confirmou:

- `escolher_anuncio` delega a escolha a `_media_escolhido`. A seleção antiga preferia a proximidade da resolução da tela, sem limitar bitrate ou rejeitar codecs explicitamente incompatíveis.
- `_tocar` entrega `PlayMedia` ao Kodi em tela cheia, sem recompilar ou substituir o player Android. O relógio usa `time.monotonic()`.
- A espera original de início tinha seu próprio orçamento. O limite de reprodução era reiniciado depois dela e não constituía teto absoluto da sessão.
- O callback de erro da versão anterior só aceitava erro quando `isPlayingVideo` já era falso. Um decoder que falhasse mantendo esse sinal ativo dependeria do detector de progresso, que ainda permitia até oito segundos sem avanço.
- O monitor original agenda a sessão em thread e suprime seus próprios callbacks durante anúncio/retomada. Essa separação, a regra de uma oportunidade por abertura e a isenção VIP permanecem.

Isso identifica lacunas de proteção no código; não prova qual codec/dispositivo causou o congelamento relatado, pois não temos log do aparelho.

## Segurança de reprodução implementada

- Amostragem do tempo real do player a cada **500 ms**; **3 segundos sem avanço** abortam a peça.
- Erro `onPlayBackError` da sessão ativa também aborta quando Kodi ainda informa reprodução. Callback anterior à posse do anúncio não é tratado como erro da nova peça.
- Tela preta/áudio sem quadro usa o mesmo limite de três segundos, quando o helper original consegue identificar esse estado.
- Limite de reprodução **mínimo entre duração + 5 segundos, 35 segundos e orçamento restante da sessão**. O início do decoder entra nesse cálculo; a busca XML/wrappers também consome o teto de 35 segundos. Uma duração válida informada pelo player pode reduzir, nunca estender, o limite.
- A peça é parada antes do fallback. Falha não dispara `complete`; erro VAST 405 é enviado às URLs disponíveis. A retomada original é acionada e o seek do VOD é confirmado (tolerância de 250 ms). Canal ao vivo usa as rotas originais de reconexão.
- Uma nova seleção do usuário durante a reprodução não é parada nem substituída pela retomada anterior.

Os limites são verificações de uma thread Python cooperativa. Kodi/Android nativo, sistema operacional e abertura do conteúdo principal têm suas próprias latências: os testes não permitem garantir execução em tempo real nem recuperação de um processo nativo completamente bloqueado. A retomada dispõe de orçamento próprio e só é declarada confirmada após verificação do player.

## MediaFile

Seleciona MP4 progressivo HTTP(S), com preferência por AVC/H.264 baseline/main quando declarado, resolução próxima de 720p e bitrate moderado. Limites: 1920×1080 e 5000 kbps. Rejeita codecs explicitamente HEVC/AV1/VP8/VP9, perfil AVC high/10-bit e áudio explicitamente incompatível. WebM/HLS não são usados como alternativa para o pre-roll nesta etapa: se não houver MP4 candidato, o conteúdo segue.

VAST frequentemente omite codec/profile de áudio/vídeo. Metadados desconhecidos de MP4 são fallback, não uma garantia de H.264/AAC; não fazemos download/probe do bitstream inteiro antes de tocar. O watchdog protege também esses casos.

## Botões sem troca de tela

As rotas originais foram identificadas: welcome 121 → `vip.abrir_dropbox`; download → `vip.open_apk_download`; atualização → `vip.procurar_atualizacao`; compartilhamento longo → `vip.compartilhar`. O addon de ajustes usa os mesmos handlers.

- Compartilhar: envia/exibe o link oficial, sem redirecionar para pastas por variante.
- A verificação de pasta configurada da welcome usa agora o arquivo universal público, não uma pasta por variante; seu helper/fallback de URL também é fixado ao mesmo arquivo.
- Baixar/Atualizar: abrem o mesmo URL direto `SMARTEDTV.apk` com `dl=1`, em Mobile, TV Box e projetor; não consultam outro manifesto nem redirecionam para uma release diferente.
- O navegador/gerenciador de downloads e o instalador Android continuam responsáveis por download, permissões e confirmação do usuário. Abrir o intent não é prova de instalação.
- Web, QR do APK e preview standalone usam o mesmo link. A referência Kodi separada também delega aos handlers, mas **não substitui a welcome do APK original**.

O link fornecido foi confirmado no Dropbox como `/SMARTEDTV UNIVERSAL/SMARTEDTV.apk`, 263.222.483 bytes, revisão original `016612000089f9e00000003401bbf21`. Ele **não é substituído automaticamente** pelo APK de teste publicado no GitHub. Os botões baixam o arquivo que o proprietário mantiver nesse link.

## Testes sem emulador

- `python3 tools/test_ads_regressions.py`: inclui peça de 21 s que avança até 5 s, congela, é parada aos ~8 s de sessão e devolve o filme em 42.125 s; erro com `isPlayingVideo=True`; tela preta com relógio avançando; prazo absoluto; latência do XML e cold start.
- `python3 tools/test_apk_links.py` e `node tools/test-apk-links.js`: destinos dos handlers, três variantes, fallback de compartilhamento e controles nativos de referência.
- No build, esses testes Python rodam novamente com `--original` sobre as funções reais extraídas e corrigidas do APK. O parser original também é testado com MP4 concorrentes.
- Demais testes JS/Python, proteção do escopo, hash da base, assinatura e alinhamento permanecem obrigatórios.

Esses são testes determinísticos com doubles de mídia/rede. Reiniciar o app no aparelho e repetir abertura de canais/filmes/episódios continua obrigatório antes de declarar aprovação de hardware.

## Build publicado e evidência

- Fonte do APK: `91a21e69a66cd8a72b84c65715e0a8b215d4e9a1`.
- [Build manual 46000575890](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46000575890), concluído com sucesso em 2026-11-27, 12:40:15–12:42:02 UTC.
- [SMARTEDTV-universal.apk](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-original-ads-46000575890-1/SMARTEDTV-universal.apk), ARM32/ARM64, 263.222.581 bytes, assinatura de teste.
- [Preservação](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-original-ads-46000575890-1/preservation.json): 8.046 entradas originais preservadas; exatamente os seis arquivos revisados de anúncios/links alterados.
- A etapa de empacotamento executou os testes de parser, oportunidades, watchdog e ações reais da welcome sobre os módulos originais corrigidos. Os casos dependentes do original são intencionalmente pulados na execução local sem APK, mas não no build.
- Aprovação de reprodução/cold start em hardware continua pendente. Fazer backup antes de remover uma instalação assinada com outra chave.
