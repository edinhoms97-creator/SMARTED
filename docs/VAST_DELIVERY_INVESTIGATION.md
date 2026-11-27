# Investigação de não entrega — fonte original e Clickadilla

Data: 2026-11-27. Escopo: canais, filmes e episódios no Kodi existente.

## Resultado objetivo: houve resposta de servidor, não houve criativo

A investigação **não confirmou reprodução até o final**. Nas consultas comparativas, ambas as fontes devolveram HTTP 200 com XML VAST de sete bytes, zero `Ad`, zero `Wrapper`, zero `InLine` e zero `MediaFile`. Isso é resposta sem anúncio (no-fill), não vídeo travado ou tracking quebrado.

[Comparação executada no run 46025145456](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46025145456), fonte `5c33c4c63c9f515f44ff07f382764a09a3a4de2a`.

| Tentativa de consulta | Origem | Resultado |
|---|---|---|
| 1 | Ferramenta de leitura da tag Clickadilla | Ferramenta retornou falha HTTP 500; não é evidência suficiente de HTTP 500 do servidor de anúncios. Nenhuma reprodução confirmada. |
| 2 | Tag original, extraída diretamente do APK fixado | HTTP 200, VAST vazio de sete bytes, nenhum criativo ou mídia. |
| 3 | Tag Clickadilla 1508180 | HTTP 200, VAST vazio de sete bytes, nenhum criativo ou mídia. |

Não houve repetição automática de consultas, fallback para outra rede, chamada de pixels ou impressão fabricada. O código de diagnóstico estava preparado para decodificar a mídia inteira por CPU quando houvesse uma mídia selecionada; **não chegou a essa fase porque não veio mídia**. Android/Kodi, imagem visível/áudio audível, toque e decoder de aparelho não foram testados. Testes locais com fixtures são regressões de lógica, não novas tentativas reais de entrega e não contam como confirmações físicas.

Esses resultados descrevem o IP/ambiente do runner naquele momento. Não provam que as tags nunca entregam, nem identificam por si sós qual regra de inventário/conta/segmentação resultou em no-fill no aparelho do usuário.

## Não era só uma troca de domínio

A [inspeção estática do run 46025437951](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46025437951), sem novas consultas a anúncios, identificou:

- Original: `https://bid.onclckstr.com/vast?spot_id=6155985`.
- Clickadilla introduzida: `https://vast.yomeno.xyz/vast?spot_id=1508180`.
- O caminho é o mesmo; **o spot é diferente**, além do domínio.
- SHA-256 da tag original: `e46fccf1d5e81e0d250d097afd10e03b904da7c991d34b647d09df93be3ebcd0`.
- SHA-256 da tag Clickadilla: `4efc4083d491aefa7aa72dcd85fced865b174b77492677f1184dd33c77de3be4`.

Não é correto montar `bid.onclckstr.com` com o spot 1508180 e chamar isso de restauração. O perfil de comparação restaura a **URL original exata**, lida do APK, inclusive o spot 6155985. Não afirmamos que a marca da rede pode ser deduzida apenas do domínio ou de comentários antigos no arquivo.

**Limite da conclusão:** a fonte original também retornou vazia no runner. Restaurá-la é uma reversão controlada para testar a configuração anterior no aparelho, não uma prova de que o domínio era a causa ou de que a entrega foi resolvida.

## Outras causas e limitações verificadas

### 1. Bloqueio pela frequência, antes de consultar a tag

O perfil anterior voltou às regras originais, inclusive intervalo de 120 segundos, VIP isento, mesma sessão/conteúdo/tentativa já consumida e estado persistido. Esses gates podem impedir uma nova consulta mesmo com a tag correta. Eles foram preservados nesta reversão para não misturar outra reescrita de ciclo. Nos testes em aparelho, usar conteúdo realmente novo, não VIP, e observar o log do gate; não interpretar ausência de requisição como no-fill.

### 2. Agendamento não é exibição

No `MonitorPreRoll` original, `_disparar` no Android inicia uma thread e devolve True imediatamente. `mostrar_preroll` usa esse True para registrar o anúncio, antes de o resultado da mídia estar disponível. O worker pode falhar/no-fill e cancelar; a ordem entre cancelamento e registro pode deixar um registro incorreto. A regressão com a função `_disparar` original e worker interceptado demonstra que o retorno True ocorre até quando esse worker devolveu False.

Isso é um risco de bookkeeping/corrida identificado no código, **não prova de que esse caminho causou o caso do aparelho**. Não reintroduzimos as substituições amplas de monitor das tentativas anteriores.

### 3. Primeiro conteúdo e callbacks

O instalador original só instala o observer, sem recuperar um AV que tenha iniciado antes dele. O perfil mínimo preserva esse comportamento. Caso o primeiro conteúdo não produza log de requisição, verificar instalação do monitor/callbacks, sem confundir com falha do servidor. Também é uma possibilidade estrutural, não um diagnóstico físico confirmado.

### 4. Corte de 1,5 segundo antes do fim

A inspeção encontrou `FOLGA_FIM = 1.5`; o loop original saía quando `posicao >= duracao - FOLGA_FIM`. Isso podia abreviar a reprodução e impedir um evento complete verdadeiro. **Nesta versão apenas esse critério muda para duração integral observada**, ou término nativo. Não foram criados atrasos artificiais, outro player ou novas regras de pausa/fullscreen.

A regressão sobre a função de reprodução efetivamente gerada usa o valor original 1,5 e exige alcançar o fim antes de retornar e emitir complete uma vez. É teste de lógica; não é confirmação de que um criativo real completou no aparelho.

### 5. Inventário/conta/rede: hipóteses ainda abertas

Como o servidor respondeu XML vazio antes de existir MediaFile, devem ser conferidos no painel: tag completa/spot correto, estado ativo/aprovado, formato e regras de entrega para app/in-stream, segmentação de país/dispositivo/origem e eventual restrição de tráfego de datacenter. No aparelho, DNS privado, bloqueador, VPN e conectividade podem mudar o resultado em relação ao runner. Essas são hipóteses de investigação, não fatos confirmados sobre a conta.

O UA da consulta da tag permanece o legado Android TV do original; pixels usam o UA runtime. Não inventamos IP, geolocalização, IDs, parâmetros ou outro spot para obter fill. É preciso comparar a tag completa fornecida pelo painel, não apenas o domínio.

## Alterações do APK de comparação

- Fonte selecionável explicitamente (`original` ou `clickadilla`), sem fallback automático. Nesta entrega: **original**.
- Somente as mesmas três entradas autorizadas: `ads_vast.py`, `smart_ads.py` e `ads_tracking.py`.
- Restauro da tag completa original, correção restrita do encerramento antecipado e diagnóstico `[SmartAdsDelivery]` das fases request/response/result/creative-selected/player-result.
- VAST vazio é identificado como `no-fill`, não como anúncio exibido. O diagnóstico não inclui URLs de stream, tokens ou nomes de conteúdo. Impressão e complete não são inventados para compensar falta de mídia.
- Player nativo, MediaFile, captura/restauração, monitor, watchdogs originais (45 s máximo, stall 6 s e sem quadro 2,5 s), frequência, VIP, pagamento, skin, recursos, manifesto, welcome e links preservados. Exceção explícita: remoção do corte antecipado de 1,5 s.
- Sem `ads_resume.py`, novos watchdogs/guardas de menu/gates de primeira abertura dos builds experimentais anteriores.

## Como interpretar o teste em aparelho

1. `[SmartAdsDelivery] request`: o app chegou à consulta; se não houver, conferir VIP/frequência/sessão/monitor no log original.
2. `response` com `ads: 0` seguido de `no-fill`: não chegou anúncio; não é possível reparar isso disparando impression ou complete.
3. `creative-selected`: só comprova seleção de mídia, não exibição.
4. `player-result` e complete: evidência do código/runtime; confirmar visualmente imagem e áudio até o fim e o retorno do conteúdo. A contagem de impressões no painel é uma checagem separada.

Não foi excedido o limite de três consultas/tentativas descritas acima. O empacotamento e os testes de regressão não voltam a consultar as tags. Se continuar vazio no aparelho, o próximo dado útil é o trecho `[SmartAdsDelivery]` e a configuração não sensível da zona no painel — nunca senha, token ou log completo com streams privados.

## Identidade da entrega

A fonte compilada e os relatórios serão identificados nas notas da prerelease e nos arquivos `source-preservation.json`/`preservation.json`. O Dropbox oficial não é sobrescrito; nenhum PR é mesclado. Assinatura de teste/debug, com a mesma cautela de backup antes de qualquer remoção. **Entrega para validação em aparelho, sem promessa de fill nem de três reproduções completas que não ocorreram.**
