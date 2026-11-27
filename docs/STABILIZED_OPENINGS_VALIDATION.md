# SMARTEDTV — estabilização restrita sobre 9436b5e

## Entrega e escopo

- Referência obrigatória: **build 45996397116 / `9436b5ef63fe1e4d569328990c92ab1514ce9b0b`**, reconstruída pelo patcher e pelos patches exatos daquela revisão, antes de acrescentar o tracking já restaurado.
- Fonte do APK corretivo final: **`8e630dd205fe03f95958efad484f4245c84dcbcd`**.
- [Build/publicação 46044121903](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46044121903), concluído com sucesso.
- [SMARTEDTV-universal.apk novo](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-original-ads-46044121903-1/SMARTEDTV-universal.apk), **263.230.975 bytes**. Caminho de saída no runner: `dist/SMARTEDTV-universal.apk`; não é o APK anterior renomeado.
- SHA-256: `5187f34599911310dbf60dd2181b3ceac6d306b7d0ccc61a58fc1c4c051875c9`.
- Tag preservada literalmente: **`https://vast.yomeno.xyz/vast?spot_id=1508180`**. Sem outro spot/provedor, parâmetros de frequência, cache de criativos ou pixels simulados.

Os commits posteriores ao commit-fonte acima registram somente ferramentas de validação/relatório; não muda o payload desse artefato. Este é um **APK corretivo de teste**, não uma declaração de aprovação de reprodução em aparelho.

## 1. Causas identificadas no código

### Elegibilidade

A referência já tinha `INTERVALO = 0` e `pode_anunciar` sem o cooldown de dois minutos. Portanto, **não atribuo esta falha a um cooldown de 120 segundos**.

Os caminhos problemáticos eram:

1. `MonitorPreRoll.onPlayBackStopped` retornava se `_e_video(self)` ainda estivesse verdadeiro. O Kodi pode notificar Stop antes de a consulta do player deixar de apresentar o vídeo antigo. Assim, um encerramento real não necessariamente executava `esquecer()`/`encerrar_conteudo()`.
2. `onPlayBackEnded` ignorava o fim durante a supressão de retorno do VAST de 18 segundos. Um VOD/episódio encerrado nessa janela também podia reter a tentativa anterior.
3. A tentativa persistida era indexada pelo conteúdo, não por uma geração de abertura. Sem o encerramento, reabrir o mesmo caminho continuava marcado como tentado. A supressão temporal de retorno agravava a ambiguidade.
4. Não havia um limite explícito de navegação pela Home no monitor de abertura.
5. No Android real, mesmo após confirmar os controles originais de entrada gratuita, a coleta antiga da reprodução nativa do primeiro MP4 não encontrou diagnóstico de abertura no build anterior (run 46041661195). A coleta antiga lia somente logcat, e não o kodi.log nativo, portanto esse resultado também pode ser falha de observabilidade e não prova ausência real de callbacks. Foi acrescentada observação passiva das bordas de reprodução como fallback, sem substituir os callbacks nativos.

Esses são defeitos determinísticos do ciclo local, cobertos pelos testes. **Não provam que toda ausência de anúncio relatada tenha essa única causa**: no-fill, rede, segmentação e limites do provedor continuam possíveis. Não houve acesso ao painel para atribuir frequência/cookies do provedor, nem tentativa de contorná-los.

### Transição após anúncio

Foram encontrados custos/falhas evitáveis no fluxo de referência:

- `abrir_anuncio` aplicava a espera de foco de uma Activity externa, de até 2,5 s, também ao VAST interno do Kodi.
- `restaurar` sempre fazia seek em VOD, inclusive em zero ou quando o player já estava no ponto correto.
- A confirmação comparava o relógio em movimento do filme com um alvo fixo de seek, tolerando apenas 0,25 s. Um seek que terminou depois de o relógio avançar podia ser rejeitado, consumir a janela de confirmação de até 3 s e levar a outra rota/reabertura, apesar de já estar retomando corretamente.
- O lock de oportunidade abrangia rede, anúncio e retomada, em vez de apenas o bookkeeping de elegibilidade.

O teste de seek reproduz avanço de 0,4 s dentro da chamada nativa: a confirmação corrigida aceita o retorno sem sleeps ou nova rota. **Isso é evidência automatizada da falha/correção, não medição do atraso percebido no aparelho do usuário**. Também não atribuo o atraso observado a resolução de proxy/plugin sem medição; a ordem original dessas rotas foi mantida.

## 2. Correções aplicadas

- `ads_openings.py`: ledger de gerações em memória, com claim sincronizado antes do dispatch. Uma geração aceita uma tentativa, independentemente de fill.
- Stop real fecha a geração mesmo com consulta de vídeo antiga; Ended de VOD/episódio fecha-a inclusive dentro da antiga janela de supressão. Ended de canal contínuo mantém a exceção de reconexão live.
- Uma nova abertura aceita limpa a elegibilidade persistida anterior. Conteúdos diferentes, reabertura do mesmo filme e navegação Home/retorno podem criar nova geração; callbacks repetidos, pausa/seek, novo Started de reconexão e retorno do anúncio permanecem na mesma.
- URLs alternativas obtidas pela retomada nativa são aliases da abertura existente. Metadados tardios de canal são vinculados sem criar tentativa extra; troca posterior de canal pode criar outra geração.
- Observador passivo de vídeo/caminho/canal/Home usa `xbmc.Monitor.waitForAbort` a cada 0,25 s, não comandos de player nem um novo serviço Android. Encaminha bordas ao mesmo claim sincronizado, cobrindo callbacks de AV ausentes no bootstrap. Não considera OSD/pausa/buffering/perda de foco como Home. Stop com getter stale é cercado até uma nova borda real. EOF live seguido automaticamente de Home e refresh de token do mesmo canal não são novas aberturas; cinco polls consecutivos da reconexão são cobertos por regressão.
- Worker VAST e pixels continuam fora do callback de AV. O lock de elegibilidade não acompanha a duração da mídia/rede.
- VAST interno não espera recuperar foco externo. Seek redundante é evitado; confirmação de seek positivo mantém a tolerância original, mas considera o tempo monotônico transcorrido em reprodução.
- Seleção de outro conteúdo enquanto a tag/anúncio está em andamento não deve restaurar o filme anterior; o resultado de mudança de conteúdo pode abrir uma nova oportunidade.
- No-fill/falha/timeout não geram impressão nem retries do mesmo claim. O conteúdo não é interrompido para consultar uma tag vazia.

### Limite semântico dos callbacks

Os testes de reconexão cobrem callbacks Started/AV/Play repetidos sem encerramento do usuário e Ended live. Um Stop de Kodi é tratado como encerramento explícito. Não se afirma que todo add-on de terceiros sinalize suas reconexões da mesma forma, nem que testes com doubles substituam navegação real no catálogo. Essa compatibilidade ainda precisa da validação prática descrita abaixo.

## 3. Tracking e diagnóstico

Foram preservados o mapping selecionado Wrapper/InLine de Impression/Tracking/Error, a expansão de macros e o UA runtime dos pixels. `ads_tracking.py` permanece byte a byte igual ao tracking restaurado. Transporte da tag, headers/TLS, seletor MediaFile, `_tocar`, controles nativos, callbacks do observador do anúncio e watchdogs da referência não foram trocados por implementações posteriores.

`[SmartAdsOpening]` registra, sem URLs/tokens:

| Etapa | O que demonstra — e o que não demonstra |
|---|---|
| `opening-claimed` | Uma oportunidade local aceita, não fill nem impressão |
| `vast-request` / `vast-response` | Tentativa da tag ou wrapper; recebimento/tamanho de XML, não início da mídia |
| `creative-selected` | Seleção do criativo; não prova que o player iniciou |
| `ad-start-observed` | Progresso do player observado no anúncio, não apenas dispatch |
| `impression-queued` / `tracking-event-queued` | Eventos enfileirados no ponto original de disparo |
| `tracking-http-response` / `tracking-http-failure` | Resultado HTTP do pixel em background, identificado por lote/abertura; **não prova contagem no painel** |
| `ad-player-released` | Saída do ciclo do anúncio e seu motivo |
| `resume-begin` / `resume-route` / `content-released` | Caminho da retomada e confirmação pelo código |
| `cycle-finished` | Resultado final de anúncio + retomada, não mera criação da thread |

Os timestamps monotônicos permitem separar liberação do anúncio, retomada e HTTP do tracking sem fazer `join` dos pixels. Wrapper hops são requisições adicionais da mesma oportunidade, não novas aberturas.

`complete` continua dependente do fim observado; um stop/erro/stall não é convertido em completion. O teste com dois callbacks Ended confirma somente uma impressão, um start e um complete no ciclo. **Nesta execução ainda não se comprovou recebimento/contagem no painel Clickadilla.** O relato anterior do usuário de eventos no painel não foi reinterpretado como confirmação independente deste build.

## 4. Verificação automatizada e preservação

- `npm run verify`: passou localmente e no build. O comando local é offline; os testes que exigem o APK completo são explicitamente skipped fora do runner.
- Build final: **11 testes históricos + 25 testes do ciclo/integração**, executados contra os módulos gerados do APK, sem confundir esses testes com ciclos Android.
- Coberturas: primeira abertura/reabertura mesmo filme/outro filme; Stop com vídeo ainda ativo; Ended dentro dos antigos 18 s; callbacks simultâneos; pausa/seek/reconexão; stop/end do anúncio; no-fill/rede; aliases da retomada; filme/episódio/canal; Home vs OSD; metadados tardios de canal; VIP; lock livre durante mídia; espera de foco apenas externa; completion duplicado; HTTP de pixel com double; retomada em zero sem seek/sleep; relógio avançando durante seek.
- Auditoria AST limita funções/métodos que podem mudar. Os demais helpers, constantes e classes são comparados antes de gerar o APK.
- Comparação final do **APK assinado** com 9436b5e + tracking restaurado: somente `smart_ads.py`, `ads_vast.py` e o novo `ads_openings.py` diferem; **8.051 entradas preservadas**.
- Comparação com o APK original fixado do Dropbox: seis módulos de anúncios diferem; **8.048 entradas preservadas**. As diferenças de `ads_admob.py`/`ads_regra.py` pertencem à referência reconstruída, não a uma troca nova desses módulos.
- Pacote `smartedtv.full` e universal **ARM32 + ARM64** preservados, incluindo bibliotecas nativas, manifesto, recursos, skin, welcome, VIP/pagamento e inicialização.
- Certificado de teste comparado com `signature.txt` do build 46028834505. Os relatórios de assinatura têm o mesmo SHA-256 (`f11381dae6807f297a9b53ef28957165d9b9317c287be53f734b01304b2af1bb`). Isso preserva a chave de teste anterior; **não equivale a possuir a chave oficial de distribuição**.
- APK oficial do Dropbox não foi sobrescrito; nenhum PR foi mesclado.

Relatórios anexados à [release final](https://github.com/edinhoms97-creator/SMARTED/releases/tag/smarted-original-ads-46044121903-1): `source-preservation.json`, `preservation.json`, `reference-preservation.json`, `signature.txt`, `badging.txt` e checksum.

## 5. Validação Android real

**Resultado final: BLOQUEADO. Build/preservação aprovados; reprodução de anúncio e três ciclos Android NÃO aprovados.**

Ambiente local: sem SDK/JDK/ADB/emulador e sem `/dev/kvm`. No runner GitHub: JDK 17, SDK, ADB e AVD Android **11 / API 30**, `google_apis/x86_64`, KVM e `libndk_translation.so`. O APK ARM é instalado sem inserir ABI x86 no app. Acesso a arquivos é concedido por appops; APK, licença, VIP e perfil não são modificados para passar o teste.

No run anterior [46041661195](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46041661195), o hash do APK foi conferido; os controles originais 312 (Assistir com anúncios) e 906 (Continuar com anúncios) foram confirmados pelos rótulos de foco via JSON-RPC já habilitado no Kodi. O primeiro MP4 público reproduziu nativamente, mas a coleta por logcat não encontrou abertura em 85 s. Como os diagnósticos Python do Kodi ficam no arquivo kodi.log, isso NÃO comprova ausência de callback/requisição; a coleta final foi corrigida para ler o log nativo com ADB debug root no emulador. Os dois ciclos restantes não foram executados; contagens não apuradas, e não zero/no-fill. Esse resultado motivou tanto o fallback passivo quanto a revisão da coleta; não foi possível isolá-los como causa única no teste antigo.

O teste usa MP4s públicos no player nativo, não navegação por três itens reais do catálogo. Portanto, mesmo eventuais três oportunidades confirmadas com essas amostras não certificam todas as rotas de filmes/séries/canais do catálogo. O pós-teste compara hashes de módulos instalados com o próprio APK, sem alterar código ou configurações do app. O helper consulta arquivo/relógio/velocidade do player separadamente do dispatch de intent nos ciclos que chegam ao fim; o primeiro ciclo bloqueou antes dessa consulta final.

### APK final — tentativa real e diagnóstico somente leitura

- [Android run 46044719121](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46044719121): instalado e iniciado com SHA-256 **5187f34599911310dbf60dd2181b3ceac6d306b7d0ccc61a58fc1c4c051875c9**, exatamente o APK desta entrega.
- Entrada gratuita original confirmada: foco `Ativar → Assistir com anúncios → Voltar → Continuar com anúncios` e callbacks nativos dos controles **312 e 906** encontrados no kodi.log. Não basta o retorno zero de Input.Select/adb.
- Os cinco módulos extraídos em `/data/user/0/smartedtv.full/cache/apk/assets/addons/service.smarted.bootstrap` têm hashes idênticos aos do APK. Não existe cópia desses módulos em `.kodi/addons/service.smarted.bootstrap` sobrepondo-os.
- Etapas efetivamente encontradas no log nativo: `state-observer-installed` em 176817 ms e `native-playback-observed` em 224702 ms. A diferença é o tempo desde a instalação do observador no bootstrap, **não uma medida de latência do anúncio**.
- O primeiro MP4 abriu e chegou ao EOF no player nativo. Porém **não foi encontrado `opening-claimed`, request/response, início de anúncio ou cycle-finished** na janela de 85 s. O fallback observou vídeo mas não demonstrou uma oportunidade concluída; não resolveu comprovadamente o bloqueio neste ambiente.
- [Inspeção somente leitura 46045618702](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46045618702): `motor_anuncio` do APK seleciona VAST com o mapping da referência (`validacao-clickadilla-1508180-admob-desativado`); `_e_video` apenas consulta `isPlayingVideo()`. Não foi identificado desvio para AdMob nem filtro de MP4 local nesses gates. A condição exata que impediu o claim permanece não isolada; não atribuo isso ao provedor/no-fill.
- O erro de `service.xbmc.versioncheck` em `uname -rs`/SIGSEGV sob tradução ARM pertence a outro add-on; não é prova de exceção no worker VAST. Há também SystemExit em callback de importlib no bootstrap; não foi estabelecido nexo causal com o gate de abertura. Nenhum desses módulos foi alterado.
- O run intermediário 46044021466, anterior ao último ajuste live, instalou o observador e confirmou hashes, mas não alcançou o controle 906; nenhum ciclo de conteúdo foi executado. Não é aprovação alternativa.

Evidência compacta versionada: [Android](evidence/stabilized-openings-android.json) e [preservação](evidence/stabilized-openings-preservation.json). Logs, screenshot e relatório completo estão no artefato `android-environment-result` do run (retenção de 7 dias).

| Ciclo Android solicitado | Requisições VAST | Ads realmente tocados | No-fill | Complete / filme liberado |
|---|---:|---:|---:|---|
| 1. Big Buck Bunny (amostra, não item do catálogo) | não apurado | não apurado | não apurado | bloqueado: vídeo observado, claim não encontrado |
| 2. Reabrir a mesma amostra | não apurado | não apurado | não apurado | não executado após bloqueio do ciclo 1 |
| 3. Echo Here We Are (outra amostra) | não apurado | não apurado | não apurado | não executado após bloqueio do ciclo 1 |

Não preencher campos não executados com zero observado, nem usar testes unitários como substituto desta tabela. Instalação/boot Android não provam anúncio ou tracking real. Sem anúncio efetivamente completado não há medição honesta do atraso pós-anúncio. Sem acesso ao painel não há comprovação de contagem Clickadilla.

## 6. Conclusão e pendências de aceitação

As regressões determinísticas de flags/gerações e transição foram corrigidas e passaram nos testes automatizados; tracking e escopo binário foram preservados. **Isso não constitui validação funcional completa do APK.** O fallback passivo permanece candidato, com borda de vídeo comprovada e claim não comprovado no Android.

Para aprovação faltam: isolar o gate entre vídeo observado e claim, repetir três aberturas reais do catálogo (incluindo mesmo título), obter resposta com criativo real e comprovar início/impressão/completion únicos, retorno do filme e latência pós-anúncio. Rede/no-fill devem continuar fail-open; não se deve forçar fill nem trocar tag/spot. O painel Clickadilla exige verificação independente pelo titular; HTTP 2xx ou evento enfileirado não são recibo do dashboard.

O artefato é uma **prerelease de teste**, não atualização oficial aprovada. Nenhum merge, sobrescrita do Dropbox, mudança de skin/welcome/licença/VIP/pagamento ou troca de chave oficial foi realizado.
