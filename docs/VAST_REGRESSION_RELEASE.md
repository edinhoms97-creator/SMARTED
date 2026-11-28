# SMARTEDTV — correção de regressão VAST e APK de teste

## Decisão atual do usuário

**VAST também no celular nesta etapa. AdMob NÃO reativado.** A integração nativa e a classificação de dispositivos continuam no pacote, mas a seleção desta prerelease retorna VAST para validar primeiro esse fluxo. A distribuição futura AdMob/celular e VAST/TV/box fica adiada até aprovação do usuário.

O relato é de regressão: antes havia anúncio em aberturas consecutivas; agora é necessário entrar várias vezes para observar um anúncio. **Não se atribui esse comportamento a falta de inventário da Clickadilla sem evidência.** Esta entrega corrige gates locais, não acrescenta tentativas de tag até obter fill, não muda spot/provedor e não reaproveita criativos.

## APK desta entrega

- Build: **46074593488**; fonte **`27da6476440e837bdcb48637583a1926c48d6829`**.
- [SMARTEDTV-universal.apk](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-original-ads-46074593488-1/SMARTEDTV-universal.apk).
- [Build e gates](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46074593488).
- Tamanho: **263.230.975 bytes**; saída do runner: `dist/SMARTEDTV-universal.apk`.
- SHA-256: **`2b64c443f42902cb07031db1106137a59d852ae39bb8fbd8b9379b8a6d2682bc`**.
- Tag: **`https://vast.yomeno.xyz/vast?spot_id=1508180`**, sem parâmetros novos.

Este é um APK novo gerado pelo pipeline; não é um APK antigo renomeado. Ele substitui, para este teste, tanto o regressivo 46044121903 quanto os candidatos intermediários desta rodada. O 46073524498 selecionava AdMob compatível e NÃO é o indicado para a etapa atual; seu teste Android foi cancelado após a correção de escopo do usuário. O 46073977919 é intermediário e não contém o último tratamento de troca durante no-fill.

## Defeitos reproduzidos e correções

Os testes dirigidos abaixo falharam no código anterior antes da correção. Isso comprova os defeitos de lógica, **não que sejam a única causa de todos os casos do aparelho físico**.

### 1. Cerca de Stop presa em uma troca direta

No 46044121903, `_smarted_wait_for_video_boundary=True` só era liberada por uma leitura sem mídia ou depois de aceitar um claim. O observador, porém, recusava chegar ao claim enquanto a flag estava ativa. Se o Kodi trocasse A → B entre polls sem uma amostra intermediária sem mídia, B podia ficar bloqueado durante toda a reprodução.

Correção: guardar o caminho parado e cercar somente o estado antigo; caminho de conteúdo diferente libera a cerca e passa pelo claim sincronizado. Ausência de mídia observada e uma abertura aceita também reinicializam esse estado. O último frame stale do mesmo vídeo continua protegido contra duplicidade.

Regressão: `test_stop_then_switch_without_no_media_poll_is_not_permanently_fenced`.

### 2. Borda de início consumida antes de o gate estar pronto

O observador registrava vídeo/caminho e considerava a borda consumida mesmo quando `_talvez_mostrar()` retornava porque sua leitura de vídeo ainda não estava pronta. Com o caminho estabilizado, não havia outra borda para chamar o gate; o conteúdo podia seguir inteiro sem request.

Correção: o gate distingue estado `pending` de claim aceito ou bloqueio definitivo. Apenas uma leitura local de vídeo/caminho ainda indisponível é refeita nos polls. Após claim, VIP ou duplicidade não há retries de rede pela observação. Erro transitório de leitura nativa também não mata permanentemente a thread do observador.

Regressões: `test_first_video_edge_with_temporarily_missing_metadata_is_retried_locally` e `test_actual_full_module_retries_readiness_with_unmodified_native_path_getter`. A segunda executa o módulo nativo gerado completo, incluindo o getter original de caminho, com APIs nativas simuladas — ainda é teste automatizado, não Android real.

### 3. Filme novo absorvido como alias de uma tentativa anterior sem criativo

Se a consulta do conteúdo A terminasse sem anúncio enquanto o usuário já estivesse em B, o worker podia vincular o caminho de B como alias da abertura de A. Assim, uma tentativa anterior absorvia a oportunidade de B.

Correção: quando não houve criativo nem restauração, um VOD diferente é tratado como nova seleção; a geração anterior termina e B ganha sua própria elegibilidade. Mantidas as exceções para mesmo canal com refresh de token e aliases reais de restauração. Não se solicita novamente para o mesmo conteúdo após no-fill só porque houve outro callback.

Regressão: `test_new_content_selected_during_nofill_gets_its_own_attempt`.

## Escopo dos scripts e preservação

- `smart_ads.py`: gates de elegibilidade, limpeza da cerca, nova seleção durante tentativa e seleção VAST explícita da etapa de teste.
- `ads_openings.py`: estado pendente de metadados, reset por identidade/ausência de mídia, observação resiliente e logs de motivos.
- `ads_vast.py`: logs de erro HTTP/timeout e de conteúdo ininterrupto versus resultado de restauração. No transporte, apenas instrumentação: headers, TLS, URL, parâmetros, timeout, orçamento de leitura e limites de tamanho permanecem os anteriores. O teste remove somente a instrumentação e compara a AST de `baixar` com a referência.
- `ads_tracking.py`: **byte a byte preservado**. Mapping Wrapper/InLine, macros, User-Agent runtime dos pixels e eventos não foram retirados.

Comparação do APK assinado contra **9436b5e + tracking restaurado**: somente `smart_ads.py`, `ads_vast.py` e `ads_openings.py` diferem; **8.051 entradas preservadas**. Contra o original bruto: seis módulos de anúncios autorizados diferem/adicionados e **8.048 entradas preservadas**. As diferenças históricas de `ads_regra.py`, `ads_admob.py` e tracking frente ao bruto não são uma nova alteração desses módulos nesta correção.

Mesmos pacote `smartedtv.full`, ARM32+ARM64, bibliotecas, manifesto, recursos, skin, welcome, VIP/pagamento e helpers de player. Assinatura de teste em cache do pipeline preservada (`signature.txt` SHA-256 `f11381dae6807f297a9b53ef28957165d9b9317c287be53f734b01304b2af1bb`); **não é certificação de posse da chave oficial de distribuição**. Não sobrescrito o Dropbox; nenhum merge.

[Auditoria da entrega](evidence/vast-regression-release-preservation.json). Comparações anteriores: [relatório dos APKs](RELATORIO_COMPARATIVO_VAST_APKS.md).

## Diagnóstico objetivo

Logs `[SmartAdsOpening]` não incluem URLs de filme, tokens ou URLs de pixels.

| Etapa | Interpretação |
|---|---|
| `provider-selected` | Motor e motivo da seleção; nesta entrega deve indicar VAST |
| `attempt-blocked` | Motivo: `video-not-ready`, `path-not-ready`, `stale-stopped-video`, `ad-cycle-running`, `opening-already-attempted`, `vip-exempt` ou falha de leitura nativa |
| `eligibility-ready` / `opening-claimed` | Pré-condições prontas / tentativa local autorizada; ainda não é anúncio |
| `blocking-state-reset` | Cerca liberada por novo conteúdo, ausência de mídia ou abertura aceita |
| `vast-request` / `vast-response` | Início de GET (hop) / resposta e tamanho |
| `vast-result` | Resultado, inclusive no-fill ou resposta ausente/inválida |
| `vast-transport-error` / `vast-transport-timeout` | Classe de erro, status HTTP quando disponível, deadline ou limite de resposta; sem expor URL |
| `creative-selected` / `ad-start-observed` | Criativo selecionado / início com avanço observado no player |
| `impression-queued` / `tracking-event-queued` | Tracking enfileirado no ponto de evento; não é recibo do painel |
| `tracking-http-response` / `tracking-http-failure` | Resultado HTTP dos pixels; não comprova contagem Clickadilla |
| `ad-player-released` | Saída do player do anúncio e motivo, incluindo fim/erro/interrupção |
| `content-uninterrupted` | Não foi necessário restaurar e o mesmo conteúdo segue tocando |
| `content-release-result` / `content-released` | Resultado da restauração / confirmação do helper de retomada |
| `content-changed-during-attempt` | Nova seleção detectada durante tentativa anterior sem mídia de anúncio |
| `cycle-finished` | Worker finalizado, com confirmação ou não de anúncio + retomada |

Isso separa: **A)** não houve request; **B)** request sem criativo; **C)** criativo selecionado com falha de reprodução; **D)** anúncio observado com falha de retorno. Requisição não é impressão; HTTP 2xx não é contagem no dashboard.

## Testes automatizados

- `npm run verify`: passou. Localmente os seis testes dependentes do APK completo ficam explicitamente skipped.
- Build: **11 testes históricos + 33 testes de ciclo/integração sobre módulos gerados**, incluindo importação do módulo nativo completo.
- A etapa Android repete os testes sobre as fontes extraídas do **mesmo APK baixado**, antes de iniciar o AVD. Não substitui isso por módulos de outro build.

| Cenário solicitado | Cobertura automatizada |
|---|---|
| Primeira, segunda e terceira reprodução | Gerações independentes; mesmo título reaberto, outro filme, episódio e canal |
| Fim natural do anúncio | Completion duplicado processado uma vez; tracking preservado |
| Stop | Getter stale, mudança direta sem leitura sem mídia, nova abertura |
| Home → conteúdo | Nova oportunidade; OSD/pausa não confundidos com Home |
| Falha/no-fill/timeout | Não marcam impressão; tentativa seguinte em nova abertura funciona |
| Filme trocado durante no-fill | Novo filme não vira alias bloqueado da tentativa anterior |
| Sem anúncio disponível | Não interrompe o conteúdo para uma tag vazia |
| Metadados ainda indisponíveis | Releitura de elegibilidade sem duplicar request |
| Concorrência/callbacks repetidos | Um claim; lock não fica preso durante mídia/rede |
| VIP | Isento, sem iniciar anúncio |
| Provedor nesta etapa | VAST mesmo em celular compatível com AdMob; ativação AdMob adiada por instrução explícita |

## Android real — resultado consolidado

- [Execução final 46075912044](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46075912044): Android **11/API 30**, Google APIs x86_64, KVM e `libndk_translation.so`; APK ARM instalado sem adicionar ABI x86 ao aplicativo.
- SHA-256 instalado: **2b64c443f42902cb07031db1106137a59d852ae39bb8fbd8b9379b8a6d2682bc**. Instalação e cold launch concluídos, processo ativo. Todos os módulos lidos na extração instalada têm hashes idênticos aos do APK.
- **33 testes do payload extraído passaram antes do AVD**, incluindo importação do módulo nativo completo; isso permanece teste com doubles das APIs, não prova de vídeo de anúncio.
- Log nativo confirmou `provider-selected` com `provider=vast` e motivo `validacao-vast-celular-admob-adiado`, e `state-observer-installed`.
- **Bloqueio do teste de conteúdo:** o foco alcançou “Assistir com anúncios”, mas o callback original 312 não foi confirmado e o controle 906 não foi alcançado. Input.Select retornou OK, mas isso não é prova de ativação. Não se alteraram welcome, licença, VIP ou perfil para forçar a passagem.
- Tentativa anterior do mesmo APK [46075278437](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46075278437) teve o mesmo bloqueio de entrada; não é aprovação alternativa.
- O helper final evita enviar dois OKs seguidos com base em rótulo stale, pois isso poderia fechar a confirmação pelo botão Voltar. Essa é mudança da automação, **não do APK**. Mesmo assim, nesta execução o callback não foi confirmado; a causa da limitação do welcome no emulador não foi isolada.
- O helper pretendia três aberturas nativas com MP4s públicos, sem fingir que eram três itens do catálogo. Elas **não foram executadas** após o bloqueio de entrada.

| Ciclo Android | Requests VAST | Anúncios tocados | No-fill | Completion / retorno |
|---|---|---|---|---|
| 1. Primeira amostra | não apurado | não apurado | não apurado | não executado |
| 2. Mesma amostra reaberta | não apurado | não apurado | não apurado | não executado |
| 3. Outra amostra | não apurado | não apurado | não apurado | não executado |

O sucesso do job significa execução/coleta concluída, **não anúncio aprovado**. Não houve evidência nova de resposta real da Clickadilla, impressão, completion, latência pós-anúncio ou contagem no painel nesta rodada. Não atribuo o bloqueio observado a no-fill do provedor.

A versão anterior do job de validação parou antes do AVD por checkout raso, sem acesso ao commit histórico exigido pelos testes; foi corrigida para buscar o histórico. Não foi considerada falha Android do APK nem sucesso de anúncio.

[Evidência Android compacta](evidence/vast-regression-release-android.json). O artefato `android-environment-result` da execução contém logs e screenshot (retenção de sete dias).

## O que fica para o aparelho físico

As três falhas determinísticas de elegibilidade foram reproduzidas e corrigidas. **A restauração completa do comportamento no aparelho do usuário ainda não está comprovada.** O novo APK está liberado para esse teste; não se pede ao usuário que aceite como normal precisar reabrir o filme várias vezes.

Critério de aceitação: abrir um filme uma vez, observar autorização/request; depois outro e um terceiro, cada um com sua própria oportunidade, sem duplicação. Em caso de anúncio real, confirmar início, conclusão única, tracking e retomada. Testar também Stop/Home e uma nova abertura após falha. Se o aparelho continuar exigindo múltiplas entradas, os novos motivos de `attempt-blocked` e estágios de request permitem localizar a etapa sem culpar o provedor por suposição.

Logs estão no `kodi.log` do perfil Android. Para análise, preferir as linhas `[SmartAdsOpening]`, que não incluem URLs/tokens; o restante do log pode conter links de conteúdo ou dados de add-ons. Ainda não há confirmação independente do painel Clickadilla. AdMob só será reativado por uma etapa posterior aprovada pelo usuário.
