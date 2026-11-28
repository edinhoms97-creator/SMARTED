# Evidência separada — gates fora de `ads_vast.exibir()`

## Escopo e conclusão

Nenhum gate externo foi alterado na missão VAST 1508249. A auditoria do APK 46079704676 contra a base exata 46074593488 preservou todas as entradas exceto `ads_vast.py`; nesse arquivo, preservou todos os bytes fora de `exibir()`.

**Não foi coletada uma sequência de aberturas físicas que atribua a regressão a um gate específico.** Os itens abaixo são condições identificáveis no código existente, não defeitos novos demonstrados no aparelho. As regressões automatizadas de ciclo passaram com doubles; isso não equivale a autorização observada pelo monitor no telefone.

## Condições existentes que precedem a função

Fontes de referência da base, inalteradas: `android-build/stabilize-9436/smart_ads.py` e `android-build/stabilize-9436/ads_openings.py`. As implementações do APK mantêm essas condições; a comparação ZIP do build confirma que os módulos não foram modificados nesta entrega.

| Local | Condição | Diagnóstico existente | Efeito |
|---|---|---|---|
| `MonitorPreRoll._talvez_mostrar()` | `_em_vast` verdadeiro | `attempt-blocked: ad-cycle-running` | Não chega à chamada VAST enquanto outro ciclo está ativo |
| Mesmo método | `_e_video()` falso | `video-not-ready` | Estado pendente, espera metadados nativos |
| Mesmo método | Caminho vazio | `path-not-ready` | Estado pendente |
| Mesmo método | `vip_ativo()` | `vip-exempt` | Isenção; não deve gerar anúncio |
| `Opening.claim()` | `in_ad` verdadeiro | Chamador registra bloqueio de ciclo | Recusa nova geração simultânea |
| `Opening.claim()` | Mesma identidade/alias/canal com `attempted` verdadeiro | `opening-already-attempted` | Evita repetir o mesmo opening por callback/seek/reconexão |
| `observe()` | Cerca de Stop ainda corresponde ao vídeo antigo | `stale-stopped-video` | Não reivindica o último frame stale como nova abertura |
| `observe()` | Sem nova borda/caminho/canal/Home nem metadados pendentes | Não faz novo claim em cada poll | Evita repetir consulta por simples passagem do tempo |

`Opening.claim()` reinicializa a geração quando `closed` ou a identidade difere; preserva identidade por canal durante refresh de token. `close()`, observação de Home e tratamento de seleção nova do worker são fronteiras externas a VAST. Removê-las indiscriminadamente criaria duplicidades e está fora da autorização atual.

## O que a evidência de VAST efetivamente confirma

- `selection-final-after.json` registra `vast_attempt_id` distinto nas chamadas 001/002/003, cada uma com GET real à tag 1508249. Vazio anterior não suprimiu a seguinte.
- No mesmo processo, 006 vazio → 007 rede → 008 timeout → 009 válido: 009 fez novo request e selecionou mídia. `exibir()` não consulta estado de vazio anterior nem armazena resposta em cache/global.
- O campo `opening` dos logs do laboratório é `null`, pois o harness chama diretamente a função e **não simula que houve um claim nativo de catálogo**.
- Os testes de ciclo incluem três gerações independentes, conteúdo diferente, reabertura e limites entre callbacks; os casos com módulo completo usam doubles Kodi. A evidência de request real não é evidência física de navegação/eligibilidade.

## Como isolar um bloqueio no aparelho, sem alterar código externo

1. Fazer uma abertura elegível e guardar as linhas `[SmartAdsOpening]` dessa janela de tempo.
2. Procurar `opening-claimed` e depois `vast-entry-called` com ID novo.
3. Se não houver entrada VAST, identificar `attempt-blocked` ou ausência de nova borda: problema anterior à função. Não interpretar ausência de request como resposta no-fill.
4. Se houver entrada e request, analisar resposta, ramos e `creative-selected`/motivo final.
5. Se houver seleção, analisar `ad-start-observed`, tracking e saída/retorno do player. Essa parte foi preservada, não presumida aprovada.

Qualquer correção externa exigiria autorização separada e reprodução específica. Não se alteraram monitor, Home, player, retomada, VIP, AdMob ou tracking para fazer o teste passar.
