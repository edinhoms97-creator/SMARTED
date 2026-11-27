# VAST 1508249 — diagnóstico restrito a uma função

## Entrega e limites

**APK novo para teste físico:** [SMARTEDTV-universal.apk](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-vast-only-46078577850-1/SMARTEDTV-universal.apk).

- Build/laboratório: [46078577850](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46078577850), concluído com sucesso; fonte `12a161928e32b195c60dd9dd88faf0c24838adf7`.
- Base exata: APK 46074593488, SHA-256 `2b64c443f42902cb07031db1106137a59d852ae39bb8fbd8b9379b8a6d2682bc`.
- **Novo SHA-256:** `be858543111b725d741ff2ec2d1238a40ea3256c28e0c91ff87856db2d4e5bd7` (digest do asset publicado, conferência também no pipeline).
- Tamanho: 263.230.975 bytes. Mesmo tamanho não significa mesmo arquivo: o hash é diferente e o payload foi auditado.
- Única entrada de código diferente da base: `assets/addons/service.smarted.bootstrap/ads_vast.py`; **8.053 entradas não-assinatura preservadas**.
- Dentro desse arquivo, **somente `exibir()`**: todos os bytes anteriores/posteriores e a AST das demais definições/constantes foram comparados e preservados.
- ARM32+ARM64, manifesto/recursos/skin/bootstrap, assinatura de teste, welcome, VIP/pagamento, AdMob, player/retomada, Home/navegação e monitor preservados. `ads_tracking.py` não foi modificado. Zipalign e apksigner passaram; certificado SHA-256 comparado com a base.

**Não foi demonstrado que a regressão das aberturas no aparelho físico está resolvida.** Não foi reproduzido bloqueio persistente dentro da função autorizada. Esta entrega troca a tag e melhora a separação diagnóstica, sem inventar um defeito nem modificar gates externos proibidos. Browser, regressões com doubles e build não comprovam anúncio no Kodi/Android ou impressão em painel.

O relatório anterior `VAST_REGRESSION_RELEASE.md` descreve a entrega histórica 46074593488/tag 1508180, não esta entrega. As alterações históricas já presentes naquela base não foram reaplicadas/modificadas agora.

## Ordem da investigação

1. Commit `a977e9b`: laboratório isolado criado **antes** de qualquer novo patch de produção.
2. Baseline [46078100066](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46078100066): executou o módulo da base, chamando diretamente `exibir(tag=nova_tag)`. As três consultas reais retornaram `<VAST/>`; isso não significa que a configuração antiga já utilizava a nova tag.
3. O download do MP4 público do laboratório falhou por HTTPError. A seleção de mídia já estava comprovada, **a reprodução de fixture ainda não**. Não foi tratado como anúncio reproduzido.
4. Build 46078577850: antes do patch, o mesmo módulo-base foi retestado com fixtures e vídeo local determinístico; todos os casos válidos avançaram no Chromium. Só depois disso foi aplicado o patch de `exibir()` e gerado o APK novo.
5. O APK assinado novo foi extraído e usado no laboratório depois da alteração: três chamadas reais + fixtures. As três chamadas reais novamente receberam XML vazio; todas as fixtures válidas reproduziram o padrão local, inclusive após vazio/erro/timeout.
6. Coleta complementar, sem reconstruir o APK e sem novas consultas reais: regressões dos módulos completos do mesmo APK e fixtures com captura dos logs nativos. O vídeo da fixture é um **padrão de teste**, não um anúncio da Clickadilla.

## Alteração de produção efetiva

Em `exibir()` apenas:

- Define a raiz efetiva como `https://vast.yomeno.xyz/vast?spot_id=1508249` para toda chamada, independentemente do argumento legado. Não há fallback automático para 1508180 nem para MP4.
- Gera `vast_attempt_id` por invocação e acrescenta aos logs locais emitidos pela função e ao recibo. UUID não é enviado na tag/pixels; não é parâmetro de frequência.
- Emite `vast-entry-called` com a raiz pública fixa e `vast-selection-diagnostic` com `ad_present` e motivo `empty-vast` ou `ad-without-supported-media`.
- Não altera seletor, transporte, headers, limites/timeout, mapeamento, reprodução, tracking, Error code/dispatch nem retorno fail-open existente.

Por restrição literal de função única, constantes históricas e `tag_configurada()` continuam byte-idênticas à base. A tag antiga pode portanto existir como texto no pacote, **mas não é raiz efetiva nem fallback de `exibir()`**. O teste passa argumentos antigos e vazios e exige exclusivamente a raiz nova.

## Onde acontece o retorno sem anúncio — e onde NÃO foi provado defeito

Cadeia em `ads_vast.exibir()`:

```
baixar(current) -> data
  data is None                 -> falha-rede-vast / 301
  not data or not data.strip() -> no-fill / 303
  XML inválido                 -> xml-invalido / 100
  escolher_anuncio(data, altura_tela)
    mídia encontrada           -> reproduzir(ad, ...)
    não encontrada             -> tag_do_wrapper(data) or tag_do_vmap(data)
      sem target               -> no-fill-ou-sem-midia / 303
      com target               -> próximo hop (visited/deadline locais)
```

**Condição exata que confundia os diagnósticos:** `if not target` depois de `escolher_anuncio()` não selecionar mídia. O recibo genérico incluía tanto VAST sem `Ad` quanto `Ad` sem mídia compatível. O log novo diferencia esses casos; a seleção e o recibo genérico foram mantidos por compatibilidade. Não há prova de que uma mídia compatível real esteja sendo descartada aí. Remover esse retorno de XML vazio não criaria MediaFile e seria uma falsa correção.

`visited`, prazo de 8s e listas Wrapper são recriados em cada invocação. No teste de mesma instância de módulo, a chamada 009, após 006 vazio, 007 rede e 008 timeout, fez seu próprio request e selecionou mídia. O mesmo criativo de fixture foi aceito consecutivamente: não há deduplicação/cache de criativo nessa entrada.

### Gates externos identificados, NÃO alterados

Leitura do código existente em `android-build/stabilize-9436/`:

- `MonitorPreRoll._talvez_mostrar()`: `_em_vast`, vídeo/caminho ainda indisponível e VIP podem impedir chegar à função; `Opening.claim()` pode retornar `None`.
- `Opening.claim()`: recusa enquanto `in_ad`; conserva a mesma identidade para alias/canal e recusa se `attempted` já é verdadeiro. Esse estado evita callbacks/seek/reconexão duplicados; não é prova de cache de resposta VAST.
- `observe()`: cerca de Stop e reconhecimento de nova borda/Home influem no envio ao gate.
- `_ciclo_vast()`: encerra geração e distingue conteúdo novo de alias após tentativa sem mídia.

Não houve sequência nativa de logs do aparelho que comprove qual desses gates causou o relato. Eles estão **fora da autorização atual**, assim como qualquer alteração no tracking. Nenhum foi relaxado ou removido nesta entrega. Os logs existentes `attempt-blocked`/`opening-claimed`, combinados com o novo `vast-entry-called`, separam uma abertura que nem chegou a VAST de uma chamada VAST com resposta vazia.

## Matriz de evidências

Último laboratório com rede: 2026-11-27, aproximadamente 22:47 UTC, runner GitHub; não é IP do celular.

| Caso | Fonte | Resultado observado |
|---|---|---|
| 001 primeira chamada | Real, tag nova | HTTP 200, 7 bytes, `<VAST/>`, sem Ad/MediaFile, sem player |
| 002 segunda chamada | Real, tag nova | HTTP 200, 7 bytes, `<VAST/>`, request próprio |
| 003 terceira chamada | Real, tag nova | HTTP 200, 7 bytes, `<VAST/>`, request próprio |
| 004 outro conteúdo A | Fixture válida | Seletor nativo aceitou video/mp4; padrão local avançou no Chromium |
| 005 outro conteúdo B | Fixture válida | Request/seleção próprios; mesmo padrão local aceito novamente |
| 006 VAST vazio | Fixture | Falha aberta, sem mídia/player/impressão |
| 007 conexão falha | Fixture URLError | Transporte registra classe; recibo falha-rede-vast |
| 008 timeout | Fixture TimeoutError | Transporte marca timeout; recibo genérico falha-rede-vast preservado |
| 009 chamada após 006–008 | Fixture válida, mesmo processo | Novo request, seleção e avanço no browser (0,2118s, readyState 4, 640×360, sem erro) |

HTTP200 por si só não foi considerado anúncio. O SHA-256 bruto de cada resposta real vazia é `093777a16300e4bfada4768dee58e25a3d45de477682d97ea21d728210853801`. No baseline anterior houve outras três respostas iguais. Isso comprova somente essas respostas nesse ambiente e não falta de inventário global, no celular ou no histórico do usuário.

## Testes e honestidade de escopo

- `npm run verify`: passou localmente e no build. Casos dependentes de APK completo são explicitamente skipped no comando local, não contados como executados.
- **8 testes novos**, também contra a função extraída da base exata no runner: bytes/AST fora da função; primeira/segunda/terceira chamadas com IDs únicos; vazio/rede/timeout/XML inválido seguidos de válido; argumento antigo/vazio sem fallback; vazio vs mídia incompatível; criativo repetido; ciclo Wrapper sem envenenar a chamada seguinte; herança Wrapper/pixels e argumentos do player preservados.
- Laboratório antes e depois passou com fixtures; player nativo foi substituído SOMENTE no laboratório por captura do anúncio selecionado. Browser recebe padrão local para fixtures, nunca mídia inventada enviada como anúncio real. Pixels suprimidos em todos os cenários de laboratório.
- Completar uma reprodução Kodi, ouvir áudio, usar controles e retornar ao conteúdo original em Android físico ainda está **pendente**. A etapa Android da entrega histórica ficou bloqueada no welcome; ela não valida este APK novo e não foi citada como aprovação.
- Testes de conteúdos diferentes no laboratório chamam diretamente a função com IDs distintos; **não exercitam navegação/catálogo nem provam que o monitor nativo fez três claims**.

## Evidências para outro agente, sem reexecução

- Pasta versionada [evidence/vast-function-1508249](evidence/vast-function-1508249): `before-live.json`, `before-fixtures.json`, `after.json`, `preservation.json` e previews de screenshots reais. JSON contém todas as respostas XML sanitizadas, requests, URLs efetivas, HTTP/headers selecionados, horários UTC, hash bruto, eventos, MediaFile, recibos e resultado browser.
- No [run 46078577850](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46078577850), baixar `vast-visual-lab-evidence`: pastas `baseline/evidence` e `after/evidence`, tentativas sequenciais 001–009. Cada uma tem quatro PNGs reais de request/HTTP-XML/seleção/resultado, JSON e JSONL; `index.html` permite inspeção offline. Retenção do artefato: 30 dias.
- `SMARTED-vast-single-function` contém o APK, auditorias, `exibir.diff`, plano, assinaturas e informações de instalação.
- [Arquivo durável de evidências](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-vast-only-46078577850-1/VAST-1508249-evidence.zip): cópia dos artefatos inicial e antes/depois, mais fixtures com logs internos; sem novo APK ou reexecução de rede. Publicação complementar separada da compilação.
- Query strings sensíveis foram ocultadas; hashes brutos conservados. Não há reenvio de impression/start/complete nem aprovação atribuída ao painel.

## Teste físico recomendado

Instalar o APK novo e abrir três conteúdos elegíveis, uma vez cada. Guardar apenas linhas `[SmartAdsOpening]` relevantes do `kodi.log` (o restante pode conter dados de provedores). Para cada abertura: `opening-claimed` → `vast-entry-called`/ID → `vast-request` → resposta → seleção ou motivo. Se houver anúncio real: `ad-start-observed` → eventos de tracking → saída → conteúdo liberado. Se não houver `vast-entry-called`, investigar gate anterior **sem culpar inventário**; se XML for vazio, não repetir automaticamente a mesma abertura até obter fill. Pausa/seek/reconexão/callback duplicado não são novas oportunidades.

Não sobrescrito o Dropbox oficial. Nenhum merge. A integração AdMob permanece como estava, sem reativação.
