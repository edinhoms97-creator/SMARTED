# Clickadilla — correção de ciclo, build para validação em aparelho

Data: 2026-11-27. Escopo: **canais, filmes e episódios**, no Kodi existente. Não é declaração de correção definitiva do decoder no aparelho.

## 1. Congelamento: evidência e limite da conclusão

Defeitos reproduzidos nos testes de lógica: o loop anterior classificava uma pausa nativa de mais de 3 segundos como `travamento`; também invocava fullscreen em cada amostra de progresso (500 ms). Agora a pausa nativa suspende os orçamentos de stall/tela-preta/duração, sem PlayPause automático. Fullscreen ocorre na transição de início real, não continuamente. Stop/erro/troca de conteúdo continuam sendo observados durante a pausa.

Nos canais, `_disparar` assíncrono retorna False mesmo tendo enfileirado o anúncio. O gate original interpretava isso como ausência de anúncio e iniciava o vigia live antes da conclusão do ciclo VAST. O novo gate não inicia esse vigia enquanto `_em_vast` está ativo; o ciclo o inicia no retorno. O caminho não-VAST conserva seu gate original como alias.

Esses são defeitos de ciclo demonstráveis, **não uma identificação do defeito de codec/audio/surface do vídeo de 25 s congelado perto de 2 s**. Não existe runtime Android ou log desse aparelho nesta sessão para determinar essa causa.

## 2. Primeiro conteúdo

O instalador original apenas registrava o observer; se AV já estivesse ativo, os callbacks anteriores não eram repetidos. O wrapper instala o mesmo observer e verifica a reprodução atual imediatamente, sem atraso arbitrário. Se não houver vídeo pronto, aguarda os callbacks nativos existentes. O gate usa somente caminho atual válido, não `ultimo_caminho` antigo, e não consulta o detector de retorno AdMob para classificar aberturas VAST.

A deduplicação passa a considerar sessão **e conteúdo**, depois da inicialização da regra de processo. Assim uma troca de conteúdo com o mesmo número de sessão não é descartada, sem gerar outra tentativa para pausa/reconexão/retorno. Isso corrige cenários reproduzidos em doubles; não prova qual cenário ocorreu no aparelho do usuário.

## 3. Referência de mapeamento

| Referência | Constatação verificável |
|---|---|
| `0fea261` | Já contém a tag Clickadilla Spot 1508180. |
| `311450b` | Retomada da base com stall 3 s e margem de duração 5 s. |
| `bbd253a` | Tentativa posterior com startup 3,5 s/fallback; não reutilizada como solução. |
| `bd62cbd9c5542fe28ed6db79e886a256b5fdf9a8` | Último APK entregue antes desta investigação; referência exata de parser/transporte/tracking/seleção de mídia mantida nesta correção. |
| `7de0370`, `095135b` | Inspeções estáticas apenas; nenhum conserto de player nesses commits. |

O histórico acessível não contém painel, exportação ou logs que vinculem uma impressão efetivamente contabilizada a um commit. O relato do usuário de impressões reais é respeitado, mas **não atribuído sem prova a bd62cbd ou outro commit**. Requisição, XML recebido, criativo selecionado, progresso do player, envio de pixels e contagem no painel não são a mesma evidência.

## 4. Parâmetros e semântica preservados

- Tag exata: `https://vast.yomeno.xyz/vast?spot_id=1508180`; nenhum novo parâmetro/zone/ID.
- TLS verificado, mínimo TLS 1.2; headers legados da requisição da tag preservados (UA Chrome Android fixo, não apresentado como UA real do dispositivo).
- Herança selecionada Wrapper + InLine de Impression/Error/Tracking, inclusive nós duplicados; seleção MediaFile preservada com pin AST independente.
- Macros existentes CACHEBUSTING/CACHEBUSTER/RANDOM/TIMESTAMP/ERRORCODE/DEVICEUA; desconhecidas não são inventadas. Pixels continuam usando UA real disponível no Kodi e envio assíncrono original.
- Start/impression após progresso observado; quartis/complete/skip/error conservam a semântica anterior, inclusive complementação de quartis faltantes no término natural. Não há pixels fictícios nem prova de contagem externa.
- Uma tentativa por abertura, no-fill/falha consome tentativa mas não vira impressão; sem intervalo de 120 s; VIP isento; AdMob desligado.
- Startup 8 s, stall não pausado 3 s, duração +5 s/teto 35 s de **tempo ativo**. Pausa intencional não é erro de decoder e só o controle nativo a desfaz.

## 5. HilltopAds: o que foi encontrado/reutilizado

A busca no Git e nos três ZIPs fornecidos não encontrou uma versão Hilltop funcional identificável. O módulo do APK original tem comentários HilltopAds, mas nenhuma URL Hilltop no inventário:

`assets/addons/service.smarted.bootstrap/ads_vast.py`, SHA-256 `946b8b08169789c0a7f9c5f5701672484eef86b6ebcd5b564e80b3e718398c41`.

A auditoria confirmou `_tocar` nativo (RepeatOff + PlayMedia, fullscreen), callbacks e estrutura original de retomada. O `_tocar` continua intocado e a retomada direta existente continua em uso. **Não foi restaurado um arquivo Hilltop inteiro nem se afirma ter recuperado uma versão Hilltop comprovadamente funcional.**

## 6. Arquivos

Runtime: `android-build/ads-patches/smart_ads.py`, `ads_vast.py`, `ads_resume.py`. Escopo AST: `tools/patch_original_ads.py` permite explicitamente o gate `_talvez_mostrar` e preserva os aliases originais. Testes: `tools/test_ads_regressions.py`, `tools/test_ad_openings.py`, `tools/test_apk_pipeline.py`. Build/notas: `tools/build-universal-apk.sh`, `.github/workflows/build-universal-apk.yml`. Relatório: este arquivo. As duas inspeções anteriores alteraram somente `tools/inspect_resume_contract.py`.

Parser, MediaFile, tag, ads_tracking, regras VIP, skin, welcome, recursos, manifesto, inicialização, pagamento e arquitetura não receberam nova alteração nesta correção. A lista de oito entradas autorizadas do APK permanece a mesma.

## 7. Sequências de conteúdo

`npm run verify` passou localmente: pipeline 27, regressões de mídia 33, retomada 17, tracking 6, menus 10, aberturas 14 (1 teste de callbacks originais reservado ao runner), links 6 (1 reservado ao runner), além dos testes JS/Python preexistentes. O build executa novamente suites contra os módulos extraídos do APK original e efetivamente patchados; isso também é teste com doubles, não execução Android.

Novas regressões cobrem filme/canal/episódio como primeiro conteúdo com monitor instalado após AV, seguidos de canal/filme/episódio até a quarta abertura; sessão 0, AV ainda não pronto, mesma sessão com caminho diferente, deduplicação e disputa do vigia live. Outras cobrem no-fill, falha de rede, exceção, fechamento/reabertura, estado persistido, VIP e retorno de servidor alternativo. Não são resultados práticos de três conteúdos no aparelho.

## 8. Três ciclos físicos independentes

**Não executados:** adb, emulador e KVM indisponíveis. Autorização do usuário: publicar mesmo assim para testes próprios. Nenhum teste automatizado foi contado como ciclo físico.

Roteiro por ciclo: iniciar app do zero, abrir canal, filme e episódio; repetir com outros conteúdos; Home/reabrir; fechar/reabrir mesmo conteúdo; reiniciar sessão. Fazer três ciclos independentes. Confirmar uma tentativa por abertura e nenhuma ao pausar/buscar/reconectar/retornar.

## 9. Toque e pausa

Regressões comprovam: pausa nativa maior que 40 s não dispara watchdog nem auto-resume; retomada manual prossegue; stop durante pausa é observado; fullscreen é solicitado uma vez no início, não a cada amostra. **Toque físico, controle remoto, foco e superfície Android ainda não validados.** Não foi criado manipulador de toque/pausa ou novo player.

## 10. Imagem, áudio e diagnóstico

Reprodução completa com imagem e áudio no aparelho: **pendente**. Avanço de relógio em doubles ou callback AVStarted não comprova quadros decodificados nem áudio audível.

O Kodi log recebe `[SmartAdsLifecycle]` e o logger existente recebe `[SmartAdsDiag]`. Diagnóstico limitado a 64 eventos, sem URLs, tokens ou nomes de conteúdo. `freeze_position` é a posição observada; `freeze_wall_ms` marca o último progresso observado (ou início da condição sem quadro); `freeze_detected_wall_ms` marca a detecção pelo watchdog; `last_native_event` é o último callback antes da limpeza. Precisão limitada à amostragem de 500 ms, **não o instante exato de falha do decoder**. Paused/resumed/seek/AV/error/end/stop e a razão terminal são registrados. Esse log é local: não há upload ou endpoint novo.

Para reproduzir, anotar tipo de conteúdo, horário e gesto, e fornecer o trecho SmartAdsLifecycle/SmartAdsDiag correspondente. Verificar separadamente no painel a contagem real de impressões. Não compartilhar URLs de stream, tokens ou dados pessoais do log completo.

## 11. Retomada

Mantida captura stream resolvido/ListItem/metadados/alternativas da mesma sessão; VOD retorna à posição salva, live reinicia sem seek; sem rerodar plugin, provider ou seletor. No-fill não para conteúdo. Falha do anúncio limpa apenas sua reprodução, sem parar uma seleção mais nova. Menus identificados de player/legendas continuam com guarda limitada de transição, sem alterações permanentes de legenda/configuração. Confirmação em aparelho: pendente.

## 12. APK e identidade

Geração manual por `build-universal-apk.yml`, nesta mesma branch, com `publish_release=true`. **Build e publicação concluídos com sucesso** no [run 46020859891](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46020859891).

- Fonte compilada: `9c1cb994d71135778fdddf9ecf7723696eebe6c5` (o registro deste resultado é alteração documental posterior, não outro APK).
- [Baixar SMARTEDTV-universal.apk](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-original-ads-46020859891-1/SMARTEDTV-universal.apk).
- [Prerelease e relatórios](https://github.com/edinhoms97-creator/SMARTED/releases/tag/smarted-original-ads-46020859891-1), universal ARM32+ARM64.
- Tamanho: 263.230.973 bytes. SHA-256 informado pelo digest do asset GitHub: `09047f0cfe466d6e69385e3d98ad39d919e31fc3365de33250e39d077ea9ce77`.
- Não é o APK anterior renomeado: digest anterior `e555d5bb8f1c6a0fa193a5e5cebc3ba9cb467b6f2e1f1ac0d6f96709320768a4` (run 46017664753). O tamanho coincidir não significa conteúdo idêntico.
- Gate de preservação aprovado: oito entradas autorizadas alteradas, **8.046 preservadas**; skin/manifesto/recursos/inicialização inalterados.
- Suites locais e gates de empacotamento contra módulos originais patchados aprovados. Assinatura/alinhamento/identidade verificados pelo pipeline, não por instalação Android.

A prerelease e suas notas identificam a fonte exata; `preservation.json`, `signature.txt`, `badging.txt` e `.sha256` acompanham o APK. A rede desta sessão bloqueou o download direto dos assets/logs hospedados nos domínios auxiliares GitHub; o estado dos dois jobs, as anotações de preservação, notas da release e digest dos assets foram conferidos pela API GitHub. O pipeline conferiu o SHA-256 antes da publicação. O Dropbox oficial não foi alterado e nenhum PR foi mesclado.

Base: pacote `smartedtv.full`, versão `1.0.161`, código `2103147`, target 34. Assinatura de teste/debug conforme pipeline existente, não a chave original. Pode não atualizar uma instalação assinada com outra chave; fazer backup antes de qualquer remoção. **Build para validação em aparelho; não rotular como final fisicamente validado.**
