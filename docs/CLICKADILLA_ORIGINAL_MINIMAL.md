# Recomeço pelo APK original — Clickadilla + tracking somente

## Base conferida no Dropbox

Em 2026-11-27, a busca no conector Dropbox retornou `/SMARTEDTV UNIVERSAL/SMARTEDTV.apk`, 263.222.483 bytes, revisão `016612000089f9e00000003401bbf21`, content hash `03c2b45efbe3256e6c11f8cc9809babe133a90b180eb007cf5908f597643e277`. Esse é o original fixado no pipeline; **não é nenhum dos APKs experimentais publicados depois**. O runner confere esse hash antes de inspecionar e alterar o arquivo, inclusive quando usa o cache do original.

## Escopo deste novo teste

Perfil manual `minimal_clickadilla=true` de `build-universal-apk.yml` (padrão novo). Parte do ZIP original, aplica uma lista própria de **três entradas** e não chama o patcher dos experimentos de reprodução:

1. `ads_vast.py`: tag `https://vast.yomeno.xyz/vast?spot_id=1508180`, TLS verificado mínimo 1.2, transporte de pixels/macros, herança do tracking Wrapper + InLine e correções restritas aos disparos dos eventos.
2. `smart_ads.py`: constante da tag e seleção de VAST para o teste em todos os tipos de dispositivo. Não altera `MonitorPreRoll`, callbacks, gates, regras ou retomada.
3. `ads_tracking.py`: helper novo de macros/UA e observer **somente de leitura** para registrar end/stop; nenhum play/pause/seek/UI é executado por ele.

Não inclui `ads_resume.py`, guarda de menus, novos watchdogs, novo fluxo de primeira abertura ou troca de player das tentativas anteriores. `_tocar`, MediaFile, restauração, `exibir_e_devolver`, captura de estado e scheduler assíncrono dos pixels ficam originais, com igualdade AST conferida contra o APK; a classe `MonitorPreRoll` também. As chamadas nativas de controle no loop de reprodução têm comparação independente antes/depois.

**Regras de frequência do original preservadas, inclusive intervalo de dois minutos.** Este teste isola a troca da rede/tracking; não reaplica a regra alterada de uma tentativa por abertura dos builds anteriores. VIP, pagamento, skin, welcome, links, recursos, bibliotecas, manifesto e inicialização permanecem iguais ao original. AdMob não é o motor selecionado neste teste, mas seus arquivos originais não são reescritos.

## Tracking sem inventar eventos

- Impression e start são enviados após progresso observado, não pela simples consulta da tag ou tentativa de PlayMedia.
- Quartis usam o progresso do loop original; URLs duplicadas de nós XML distintos não são eliminadas.
- Wrappers selecionados e InLine têm suas URLs Impression, Error e Tracking herdadas. Ramos irmãos não selecionados não entram na conta.
- Erros de rede/XML/no-fill/Wrapper usam as URLs Error efetivamente fornecidas. Recusa/startup/sem quadro também usam Error quando presente. Macros existentes são expandidas; nenhum endpoint/ID/parâmetro é inventado.
- Complete não é mais sintetizado ao sair por travamento ou stop. Requer posição de fim observada ou callback de término; skip exige callback de stop, não mera ausência de vídeo.
- **Limite proposital:** o player original tem um corte perto do fim (`FOLGA_FIM`) e esse controle não foi alterado. Se ele retorna antes de terminar o anúncio, o teste não inventa complete para compensar. O status interno `exibido` e a política original de retomada também não foram remodelados; não confundir esse recibo com contagem no painel.
- Pixels usam UA obtido do runtime; a consulta da tag conserva o header legado Android TV do original. Macros desconhecidas continuam desconhecidas.

## Inspeção e testes

`tools/patch_minimal_clickadilla.py` valida o APK original e os hashes de cada arquivo antes da alteração, confere o escopo de funções por AST e emite `Minimal Clickadilla source audit` com o host da tag original e hashes das funções protegidas. O relatório `source-preservation.json` acompanha o APK.

`tools/test_minimal_clickadilla.py`: tag/motor, Wrapper aninhado e ramo selecionado, duplicidade de pixels, no-fill/rede/XML/ciclo/profundidade, macros/UA/TLS. No runner, também executa a função original com alterações só de tracking e compara os módulos efetivamente gerados com o APK base. Sem Android ou tráfego Clickadilla real nesses testes. O gate final compara **todas** as entradas fora das três permitidas, depois de assinar/alinhar.

## Entrega e limites

**Build e publicação concluídos:** [run 46023622889](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46023622889), fonte `455a398f35e1d78333336f803cfc46f952c99029`, perfil `minimal_clickadilla=true`, `publish_release=true`.

- [Baixar SMARTEDTV-universal.apk](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-original-ads-46023622889-1/SMARTEDTV-universal.apk), ARM32+ARM64, **263.222.584 bytes**.
- [Prerelease com identidade/assinatura e relatórios](https://github.com/edinhoms97-creator/SMARTED/releases/tag/smarted-original-ads-46023622889-1).
- SHA-256 do asset conferido pela API GitHub: `affd977a6dacc2eb91be6015683725737ae61d4240760038ec1a012a48969534`.
- Auditoria do APK original confirmou host anterior **`bid.onclckstr.com`**. Tag substituída pela URL Clickadilla acima.
- Preservação final aprovada: **três entradas alteradas/adicionadas, 8.049 preservadas**; funções protegidas e monitor originais iguais na comparação AST.
- Testes rápidos e os sete testes do perfil (incluindo parser e tracking sobre funções extraídas do APK original e comparação dos módulos gerados) passaram no runner. São testes com doubles, não reprodução Android.
- A tentativa anterior, run `46023423138`, parou por uma dependência ausente no harness de teste (`_DISPARAR_PADRAO`). Corrigido o harness, acrescentado teste do parser real e reexecutado o pipeline completo; nenhum APK daquela tentativa foi publicado.

O APK universal é uma prerelease separada. Não sobrescreve o original no Dropbox nem faz merge de PR. O registro deste resultado é atualização documental posterior ao SHA compilado, não outra versão do APK.

Assinatura de teste/debug do pipeline existente: pode não atualizar uma instalação de outra chave. Fazer backup antes de remover qualquer instalação. **Sem validação física de imagem/áudio/toque ou confirmação de impressões no painel.** O usuário testará este perfil original, não mais um remendo sobre o APK experimental anterior.
