# SMARTEDTV — relatório dos scripts VAST: versão anterior × APK atual

## 1. Resumo e motivo deste relatório

Você informou que testou **mais de três filmes no APK atual e nenhum exibiu anúncio**. Esse é um relato de falha no aparelho, não um resultado aprovado. Não tenho os logs desse aparelho para determinar se houve solicitação de tag, no-fill ou bloqueio anterior ao request.

**A alteração recente não foi somente de logs/tracking: ela mudou o controle que decide quando uma reprodução pode tentar um anúncio.** A comparação dos APKs publicados confirma:

- **Candidato anterior 46035861727 → atual 46044121903:** somente `smart_ads.py` e `ads_openings.py` mudaram; 8.052 entradas não relacionadas a assinatura são idênticas.
- **Versão anterior de “somente tracking restaurado”, 46028834505 → atual:** `smart_ads.py` e `ads_vast.py` mudaram, e `ads_openings.py` foi acrescentado; 8.051 entradas são idênticas.
- **Intermediário 46043711441 → atual:** só `ads_openings.py`, dentro de `observe()`, mudou; 8.053 entradas são idênticas.

Portanto, se por “uma versão antes” você quer dizer o candidato 46035861727, **o parser/transporte/player do módulo `ads_vast.py` e o helper `ads_tracking.py` são byte a byte iguais ao atual**. Se você se refere à versão 46028834505, anterior à estabilização, também houve alterações no fluxo de retomada/diagnóstico de `ads_vast.py`, detalhadas abaixo.

Este relatório não troca código do app, não restaura versões, não gera APK e não consulta anúncios.

## 2. Quais APKs foram comparados

Todos foram baixados das releases existentes no runner e tiveram o SHA-256 integral conferido antes da inspeção. As fontes Python foram lidas do ZIP, sem importá-las/executá-las.

| Identificação | Build / release (sufixo `-1`) | Commit-fonte | Tamanho |
|---|---|---|---:|
| Tracking restaurado, antes da estabilização | `46028834505` | `a1e21c054f3d165a8adcc4b9f5ce819c484e2891` | 263.226.778 bytes |
| Candidato anterior à última rodada | `46035861727` | `d81aa548f4e07d8ad24b8d165984e8af32e97fe6` | 263.226.879 bytes |
| Intermediário da última rodada | `46043711441` | `c33065f9da30f694bf9befb72d041bcd6806aedc` | 263.230.975 bytes |
| **Atual enviado na resposta anterior** | **`46044121903`** | **`8e630dd205fe03f95958efad484f4245c84dcbcd`** | **263.230.975 bytes** |

SHA-256 dos APKs:

```text
46028834505  f45cad169285cf511ac51d86660176972aa6d821d59791dab40d31235135b3a3
46035861727  1e8ca00f71b070a909561b793966f39c67540c80204d38c792322c20348ccbfb
46043711441  ae3dd85e0cfd4954e6774b5f854d75a0f31992407cc50eda7f8ec1f5a32153b4
46044121903  5187f34599911310dbf60dd2181b3ceac6d306b7d0ccc61a58fc1c4c051875c9
```

O nome `SMARTEDTV-universal.apk` é repetido entre releases; o nome sozinho não identifica a versão instalada. Os números acima identificam builds, não um novo `versionCode` a cada teste. Não estou presumindo que o hash no seu aparelho foi medido.

A referência histórica obrigatória continua **45996397116 / 9436b5e**. A versão 46028834505 reconstrói essa referência e acrescenta o tracking restaurado. Ela não é o APK bruto do Dropbox.

## 3. Scripts do sistema VAST e suas funções

Caminho dos arquivos abaixo dentro do APK:

```text
assets/addons/service.smarted.bootstrap/
```

“Idêntico” significa mesmo SHA-256 do conteúdo extraído, e não apenas funções com nomes iguais.

| Script | Papel no sistema | 46035861727 → atual | 46028834505 → atual |
|---|---|---|---|
| `smart_ads.py` | Orquestração; escolha do motor; monitor do Kodi; elegibilidade; dispatch; worker e fechamento da oportunidade | **Alterado** | **Alterado** |
| `ads_openings.py` | Registro em memória das gerações/aberturas, deduplicação, aliases, observador de Home/vídeo e diagnóstico | **Alterado** | **Novo: não existia** |
| `ads_vast.py` | Consulta VAST/Wrapper, escolha de mídia, reprodução nativa, recibo, tracking e restauração do conteúdo | Idêntico | **Alterado em seis funções** |
| `ads_tracking.py` | Macros de pixels e User-Agent real do Kodi; não decide abertura nem toca vídeo | Idêntico | Idêntico |
| `ads_regra.py` | Estado/regra persistida da oportunidade: tentativa, conteúdo, anúncio e encerramento | Idêntico | Idêntico |
| `ad_return.py` | Helpers existentes de estado/retorno de conteúdo usados pela integração de anúncios | Idêntico | Idêntico |
| `retomar.py` | Helper de retomada presente no pacote; presença não prova execução no ciclo VAST testado | Idêntico | Idêntico |
| `ao_vivo.py` | Classificação e suporte a canais contínuos/reconexão; consultado para não tratar EOF live como nova abertura | Idêntico | Idêntico |
| `variante.py` | Identificação/compatibilidade de dispositivo e funções de variante | Idêntico | Idêntico |
| `vip.py` | Verificação de isenção VIP e funções VIP existentes | Idêntico | Idêntico |
| `ads_admob.py` | Configuração isolada/inativa de AdMob da referência; não é o motor VAST | Idêntico | Idêntico |
| `service.py` | Bootstrap que inicializa a integração, entre outras tarefas do serviço | Idêntico | Idêntico |
| `check.py` | Verificações/integração do bootstrap que também referencia `smart_ads` | Idêntico | Idêntico |

Também foram inventariados todos os outros `.py` desse diretório: `repository.py`, `favourites.py`, `menu_smarted.py`, `performance.py`, `repair.py`, `skin_setup.py` e `smarted_release.py`. Nenhum mudou nessas comparações. O JSON anexo contém os hashes, tamanhos e imports de **todos os scripts desse diretório**; não apenas os arquivos alterados.

A regra já usava `INTERVALO = 0` na referência reconstruída. `ads_regra.py` não recebeu uma nova remoção de cooldown entre esses APKs. Porém **o modo como `smart_ads.py` chama/limpa a regra mudou**, mesmo com o arquivo de regras idêntico.

### Caminho lógico do anúncio

```text
service.py / integração do bootstrap
  → smart_ads.iniciar_monitor()
  → callbacks do MonitorPreRoll e, nas versões estabilizadas, ads_openings
  → MonitorPreRoll._talvez_mostrar()
  → claim da abertura, nas versões estabilizadas
  → mostrar_preroll() / ads_regra / isenção VIP
  → MonitorPreRoll._disparar() → worker _ciclo_vast()
  → tocar_anuncio_de_video() → ads_vast.exibir_e_devolver()
  → tag/Wrapper → mídia selecionada → player nativo
  → impressão/eventos → macros/UA → envio HTTP em background
  → recibo / restauração do conteúdo / liberação da abertura
```

Esse é o encadeamento lógico, não uma afirmação de que todas essas etapas ocorreram no aparelho ou no último emulador.

## 4. Diferença principal: candidato 46035861727 → atual 46044121903

### 4.1 `smart_ads.py`: três alterações de função

O arquivo passou de **59.933 para 60.109 bytes**. Não foi reescrito o player VAST nessa passagem. Foram acrescentadas três atribuições:

| Função | Mudança exata | Efeito pretendido |
|---|---|---|
| `MonitorPreRoll._talvez_mostrar` | Após aceitar uma nova geração: `self._smarted_wait_for_video_boundary = False` | Liberar a cerca de Stop quando uma nova abertura é aceita |
| `MonitorPreRoll.onPlayBackStopped` | Ao fechar a geração: `self._smarted_wait_for_video_boundary = True` | Impedir que o fallback interprete o último frame/caminho stale como nova abertura |
| `MonitorPreRoll.onPlayBackEnded` | Ao fechar VOD/episódio: a mesma flag fica `True` | Aplicar a mesma proteção ao fim do conteúdo |

**Ponto de atenção:** essa flag participa da condição de chamar o gate pelo observador. Ela não é apenas telemetria. Não há prova de que ela seja a causa dos seus filmes sem anúncio; é uma diferença funcional concreta que precisa ser considerada na investigação.

### 4.2 `ads_openings.py`: alteração do observador e da identidade da abertura

O arquivo passou de **4.298 para 6.764 bytes**.

| Função/método | Antes | Atual |
|---|---|---|
| `observe()` | Não existia | Lê vídeo ativo, caminho, nome do canal, `Player.HasMedia`, Home e fullscreen; pode chamar `_talvez_mostrar()` em bordas/mudanças |
| `watch_home()` | Thread abortável a cada 0,25 s observava navegação Home → fullscreen | A mesma cadência passa a chamar `observe()` com estado anterior; registra instalação e vídeo observado |
| `Opening.claim()` | Identidade baseada nos aliases do caminho e compatibilidade do canal | Mesmo canal conhecido pode manter a abertura mesmo com URL/token diferente; acrescenta o caminho aos aliases |
| `Opening.close()` | Recusava fechamento durante anúncio | Também recusa fechar de novo uma geração já fechada |

Outros comportamentos introduzidos no novo `observe()`:

- Durante `_em_vast`, não chama novamente o gate.
- Pausa/buffering com `Player.HasMedia` preservam o estado anterior.
- Com vídeo ativo, só chama o gate em borda de vídeo/mudança de caminho/canal quando a flag de Stop permite, ou em retorno identificado da Home.
- Em ausência de mídia, VOD pode fechar a geração e limpar retomada.
- EOF de canal seguido automaticamente da Home não deve ser confundido com navegação explícita do usuário.
- O estado live é mantido durante polls consecutivos da reconexão.

**Efeito pretendido não equivale a resultado aprovado.** No teste Android do atual, o observador registrou vídeo, mas não foi encontrado `opening-claimed`. Assim, não foi demonstrado que esse fallback resolveu a ausência de anúncios.

### 4.3 O que não mudou nessa passagem

São idênticos, inclusive byte a byte:

- `ads_vast.py`: consulta, parser, seleção de mídia, reprodução, tracking e restauração desse módulo.
- `ads_tracking.py`: expansão de macros e UA.
- `ads_regra.py`, `ad_return.py`, `retomar.py`, `ao_vivo.py` e demais módulos da tabela.
- Tag/spot, recursos, bibliotecas nativas, código Android, skin, welcome, VIP/pagamento e manifesto, pois a comparação integral não encontrou outra entrada de payload diferente.

Assinaturas/metadados `META-INF` e o bloco de assinatura do ZIP não integram a contagem de igualdade de payload. Isso não é certificação da chave oficial de distribuição.

## 5. Se a versão anterior desejada é 46028834505 (“somente tracking restaurado”)

Essa comparação é mais ampla. Nessa versão anterior **não existia `ads_openings.py`**. O controle de abertura e transição ainda era o da referência reconstruída, acrescido do tracking restaurado.

### 5.1 Mudanças em `smart_ads.py` desde essa versão

Funções com AST alterada no APK:

- `iniciar_monitor`: passa a envolver o inicializador original e a instalar o observador.
- `MonitorPreRoll._talvez_mostrar`: acrescenta o claim da geração em memória antes da regra persistida; substitui a decisão de elegibilidade do caminho VAST; limpa a elegibilidade anterior ao aceitar a abertura.
- `MonitorPreRoll.onPlayBackStopped`: usa o encerramento da geração, sem deixar o getter stale de vídeo vetar o Stop; acrescenta a cerca descrita acima.
- `MonitorPreRoll.onPlayBackEnded`: distingue EOF live de VOD/episódio, usando o encerramento da geração e não a antiga supressão temporal como veto geral.
- `MonitorPreRoll._ciclo_vast`: integra geração/contexto, reduz a abrangência do lock global, registra o recibo, vincula aliases de retorno, trata conteúdo alterado e finaliza a geração após a tentativa; substitui a supressão fixa de retorno de 18 s por estado da abertura.
- `tocar_anuncio_de_video`: guarda `_smarted_last_receipt` para o ciclo consultar o resultado.
- `abrir_anuncio`: evita aguardar foco de Activity externa quando o anúncio é VAST nativo.

Foram preservadas cópias de quatro funções originais com aliases `_smarted_iniciar_monitor_original`, `_smarted_talvez_mostrar_original`, `_smarted_stop_original` e `_smarted_end_original`.

`MonitorPreRoll._disparar` aparece no diff textual por formatação/indentação, mas sua AST é igual entre esses dois APKs. Não é contado como alteração lógica nessa comparação.

### 5.2 Mudanças em `ads_vast.py` desde essa versão

O arquivo passou de **45.056 para 46.776 bytes**. Seis funções têm AST diferente:

| Função | Mudança |
|---|---|
| `exibir` | Diagnósticos de request/response, resultado e criativo escolhido; não troca endpoint nem seletor de mídia |
| `reproduzir` | Diagnósticos de início efetivamente observado, impressão/eventos enfileirados e saída do player; não substitui o mecanismo nativo de reprodução da referência |
| `restaurar` | Evita seek redundante/em zero, limita início de rotas ao deadline existente e confirma seek positivo considerando o tempo monotônico transcorrido; acrescenta diagnóstico de retomada |
| `exibir_e_devolver` | Propaga motivo `conteudo-alterado` quando há outra seleção, para o ciclo distinguir troca real de simples retorno |
| `disparar` | Identifica lote e registra status HTTP/falha dos pixels; o envio continua em background |
| `_disparar_eventos` | Captura e propaga contexto da abertura para a thread de tracking |

O helper `ads_tracking.py` é idêntico. A herança de Impression/Tracking/Error de Wrapper/InLine e o tracking já restaurado não foram retirados. **Preservar esses scripts não garante disparo dos pixels se o fluxo nem chegar ao anúncio.**

## 6. Diferença do intermediário 46043711441 para o atual

O intermediário já continha as alterações descritas na seção 4. A única diferença até o atual é esta adição em `ads_openings.observe()`:

```diff
     monitor._smarted_wait_for_video_boundary = False
+    if suppress_auto_home:
+        return previous  # retain live identity across every reconnect poll
     return (False, '', '')
```

Finalidade: conservar a identidade do canal durante mais de um poll sem mídia no EOF/reconnect. Não altera diretamente parser, tag, pixels ou retorno de filme VOD.

Isso também mostra por que é importante nomear a versão anterior: do intermediário ao atual a diferença é de duas linhas; do candidato 46035861727 ao atual há um observador de reprodução novo; da versão 46028834505 ao atual há também a camada de geração e ajustes de retomada.

## 7. Tag, tracking, controles e arquivos que não são o runtime desse APK

Preservado:

```text
https://vast.yomeno.xyz/vast?spot_id=1508180
```

Não há nova troca para o spot 6155985 nem parâmetro acrescentado para forçar frequência/fill nessa passagem. O `motor_anuncio()` inspecionado no APK atual retorna VAST com o mapping da referência de validação.

O repositório tem outras implementações que **não devem ser confundidas com os scripts empacotados desse serviço**:

- `smartedtv/js/vast.js`: implementação web, não o motor nativo Kodi analisado aqui.
- `kodi-addon/script.smartedtv.welcome/vast.py`, `vast_player.py` e `ads_tracking.py`: outra árvore do repositório; sua presença no checkout não significa que tenham substituído `service.smarted.bootstrap/ads_vast.py` nesses APKs.
- `android-build/ads-patches/`: overlays/patches de várias revisões; o build estabilizado reconstrói os arquivos históricos fixados de 9436b5e, não aplica indiscriminadamente tudo que está nessa pasta atual.
- `android-build/confirmed-tracking/ads_vast.py`: overlay de restauração de tracking.
- `android-build/stabilize-9436/smart_ads.py` e `ads_openings.py`: overlays usados na estabilização; o `ads_vast.py` final também é transformado por `tools/stabilize_confirmed_ads.py`.
- `tools/restore_confirmed_tracking.py`, `stabilize_confirmed_ads.py`, `build-universal-apk.sh` e `apk_preservation.py`: ferramentas de reconstrução/empacotamento/auditoria, não scripts Python executados pelo player no aparelho.
- `tools/android_content_cycles.py`, `android_validation_environment.py`, `read_android_monitor_logs.py`, testes e workflows: ferramentas de validação; não entraram como novo serviço no APK.

As mudanças posteriores ao commit-fonte do APK atual foram de validação/documentação. **O hash do APK atual não mudou porque um helper de emulador ou este relatório foi alterado.**

## 8. O que se sabe sobre a ausência de anúncios

### Confirmado

1. Seu relato: mais de três filmes sem anúncio no atual.
2. No emulador do APK atual, o vídeo nativo foi observado, mas a coleta do log nativo não encontrou claim/request VAST concluído na janela testada; os dois ciclos seguintes não foram executados.
3. A versão atual mantém a tag e o helper de tracking.
4. O controle que autoriza uma abertura mudou substancialmente desde a versão de tracking restaurado.

### Não confirmado

- Não foi isolada a condição que impediu o claim no emulador.
- Não foi obtido log dos filmes testados no seu aparelho.
- Não há base para dizer que “a Clickadilla devolveu no-fill nos seus filmes”, que houve bloqueio de cookie/frequência do provedor, ou que o defeito seja apenas de tracking.
- Não há base para prometer que voltar uma versão, sozinho, resolverá todos os casos.

### Ponto técnico prioritário indicado pelo comparativo, não causa provada

O trecho **antes da consulta VAST**, entre observar reprodução e aceitar a abertura em `smart_ads.py`/`ads_openings.py`, merece prioridade. O gate retorna sem request quando não há vídeo/caminho utilizável, quando existe ciclo marcado em andamento ou quando o claim considera a abertura já tentada. O fallback novo ainda acrescenta bordas e a flag de Stop como condições. O log atual não registra o motivo de cada retorno antecipado, portanto não permite escolher uma dessas hipóteses como causa certa.

Alterar o parser ou o envio de pixels não corrige uma tentativa que não chegou a ser autorizada. Ainda assim, sem logs do aparelho não se deve assumir que todo filme sem anúncio parou na mesma etapa.

## 9. Evidências entregues e método

- [Comparação completa em JSON](evidence/vast-apk-comparison.json): hashes/tamanhos dos quatro APKs; inventário dos scripts; diferenças de funções e lista integral de entradas não relacionadas a assinatura que mudaram.
- [Diff dos scripts extraídos dos APKs](evidence/vast-apk-scripts.diff): comparação textual, incluindo o código anterior e atual nos trechos alterados. Os prefixos `tracking_restored`, `previous_candidate`, `immediate_intermediate` e `current` identificam os quatro APKs da seção 2.
- [Execução somente leitura 46072046071](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46072046071): artefato `vast-apk-script-comparison`, retenção de 30 dias. Os mesmos dois arquivos pequenos foram preservados no repositório.
- [Validação anterior do APK atual](STABILIZED_OPENINGS_VALIDATION.md): limitações Android, três ciclos não aprovados e ausência de comprovação de contagem no painel.

A comparação usa SHA-256 dos bytes de todas as entradas ZIP de payload, excluindo diretórios e `META-INF`; não confunde CRC/mesmo tamanho com igualdade. O bloco binário de assinatura do APK não é uma entrada de payload dessa comparação. As funções/métodos são comparados por AST sem posições de linha; o diff textual permite examinar também formatação e comentários.

**Nenhum novo APK foi gerado nesta solicitação, nenhum anúncio foi solicitado/reproduzido para gerar o relatório, nenhum pixel foi reenviado e nenhum código VAST de runtime foi modificado.**
