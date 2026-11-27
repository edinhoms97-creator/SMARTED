# Base confirmada pelo usuário: 9436b5e — somente tracking

## Referência escolhida, sem inferência de sucesso pelo CI

O usuário confirmou nesta conversa a opção **“Um anúncio por abertura”**, identificada como:

- Build `45996397116`, release `smarted-original-ads-45996397116-1`.
- Fonte `9436b5ef63fe1e4d569328990c92ab1514ce9b0b`.

Essa confirmação do usuário, e não um check de build, define a referência desta restauração. A referência não é o APK original bruto do Dropbox, nem `b86570a`, `bd62cbd`, nem os perfis mínimos posteriores.

## URL preservada

`https://vast.yomeno.xyz/vast?spot_id=1508180`

Sem trocar domínio, spot, parâmetros, macros da requisição da tag, headers, TLS ou timeout da consulta. O transporte `baixar` permanece exatamente o da referência. O endpoint `bid.onclckstr.com`/spot 6155985 não é selecionado neste APK.

## Reconstrução e diferenças permitidas

`tools/restore_confirmed_tracking.py` lê o commit fixo pelo Git e usa **o patcher e os quatro arquivos de patch daquela revisão**, sobre o mesmo APK original validado por hash. Não usa os arquivos atuais dos perfis experimentais para reconstruir player, regras ou retomada.

Sobre esse payload reconstruído, somente:

1. `ads_vast.py`: transporte dos pixels com macros/UA runtime; herança de Impression/Tracking/Error da cadeia Wrapper + InLine selecionada; expansão do Error code. Os pontos de disparo de start/quartis/complete/skip da referência são mantidos.
2. `ads_tracking.py`: helper de macros e UA dos pixels, sem player/monitor/UI/retomada.

`smart_ads.py`, `ads_regra.py` e `ads_admob.py` são idênticos byte a byte à referência. Todos os outros arquivos do APK também, exceto assinaturas. A versão `reproduzir` tem comparação AST integral com a referência, permitindo diferença **apenas dentro da função local `error`**, que formata os pixels de erro. Não foram alterados callbacks, controles, sleeps, watchdogs, limites, mídia, restauração, menu, pausa, VIP, pagamento, links, skin ou inicialização.

A regra confirmada volta junto com a referência: uma tentativa por abertura de canal/filme/episódio, sem intervalo de dois minutos, VIP isento e AdMob inerte. Isso é restauração da referência, não nova implementação.

Não entram o watchdog de 3 s, a retomada `ads_resume.py`, a guarda de menus, as novas verificações de primeira abertura, o diagnóstico `SmartAdsDelivery`, a troca para o domínio original ou a alteração do corte final dos builds posteriores.

## Verificação de escopo

- O gate usual compara o APK final com o original Dropbox, usando o plano histórico acrescido somente do helper de tracking.
- Um segundo gate compara **todas as entradas do APK final com o payload da referência 9436b5e**. Somente `ads_vast.py` e `ads_tracking.py` podem diferir, exceto assinaturas. O resultado acompanha a release em `reference-preservation.json`.
- `source-preservation.json` registra a referência, hashes dos módulos históricos e verificações de identidade do controle de player e da consulta da tag.
- Os 11 testes do motor da revisão histórica são executados novamente sobre os módulos gerados. Seis regressões adicionais verificam macros/UA dos pixels, preservação da consulta da tag, Wrapper selecionado/duplicatas, no-fill, Error e comparação dos módulos com a referência.
- `npm run verify` também passou localmente; o runner repete a verificação. Tudo isso é teste com doubles/comparação de fontes, não confirmação nova de reprodução física ou contabilização de pixels.

Nenhuma nova consulta real a anúncios é necessária ou executada para esse build. O original do Dropbox não é sobrescrito; nenhum PR é mesclado. APK universal ARM32+ARM64, assinatura de teste/debug do pipeline existente. Fazer backup antes de remover qualquer instalação.
