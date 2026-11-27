# Retomada resolvida e auditoria de pixels VAST

## Correção de pausa e primeiras aberturas (revisão seguinte)

A inspeção encontrou três gates que podiam impedir a consulta inicial: `_talvez_mostrar` ainda consultava `ad_return.e_volta` legado, a sessão era comparada sem comparar conteúdo, e `exibir_e_devolver` retornava antes da busca da tag quando o snapshot ainda não estava pronto. Esses casos agora têm regressões determinísticas. Sem logs do aparelho não é possível afirmar qual deles explica cada uma das duas falhas reportadas, nem distinguir isso de no-fill real.

- `onPlayBackStarted` tenta o pre-roll assim que o vídeo está pronto, sem depender só de `onAVStarted`; callbacks duplicados continuam consumindo uma única oportunidade.
- O caminho VAST não consulta `Retomada.e_volta` legado; apenas o retorno conhecido da sessão atual é suprimido. Conteúdos diferentes não são bloqueados pelo contador inicial nem pelo intervalo antigo.
- A consulta da tag não depende do snapshot inicial. Antes de substituir o vídeo, um snapshot válido é obrigatório e pode ser recapturado após o download da tag. Se não for possível retomar com segurança, o conteúdo não é interrompido; consultar não garante disponibilidade/exibição de anúncio.
- `_tocar` usa diretamente o player nativo Kodi, ListItem MP4 e `windowed=False`, sem atividade Android separada, diálogo ou espera independente. Startup sem superfície também fica limitado a 3 s.
- Pausa detectada no anúncio: tenta `Player.PlayPause(play=true)` uma vez por episódio de pausa, sem reabrir a URL; fallback para toggle apenas se a API estiver indisponível e ainda estiver pausado. O watchdog não reinicia com clique, callback, foco ou tentativa de play. Após 3 s sem avanço, stop e retomada direta.
- Recuperação de fullscreen no anúncio apenas na entrada, não a cada 500 ms: não disputar continuamente o foco dos controles. Na saída, stop da peça ainda pertencente à sessão e fechamento dos OSDs nativos `videoosd`/`seekbar`; a retomada restaura fullscreen do conteúdo. Não fecha janelas arbitrárias de uma nova seleção do usuário.
- Na referência web separada, `pause` tenta `video.play()`; rejeição encerra e limpa o overlay. O watchdog é de 3 s e não é renovado por interação. Essa referência web **não substitui o player/UI do APK**.

Novas regressões: primeiro e segundo VOD por callbacks com estado legado, callbacks duplicados, sessão zero compartilhada entre conteúdos, snapshot inicial ausente com consulta VAST, pausa em 00:01 com retomada, pausa/buffer travado em 00:01 com stop em 3 s após o último avanço, decoder sem superfície, VOD/live direto e limpeza do OSD/overlay. A aprovação em hardware continua pendente.

## Causas confirmadas na inspeção somente leitura

- `_candidatos_restauracao` original incluía `plugin_path` nos fallbacks. Reabrir esse caminho executava o provider e podia abrir novamente **ESCOLHA O SERVIDOR**.
- O Brazuca empacotado define `ForceResolvePlugin=true` no ListItem. Reutilizar metadados sem remover esse sinal também permite reentrada no resolver.
- Os antigos helpers de retomada usavam `PlayMedia` sem preservar o ListItem original.
- A cadeia VAST Python seguia Wrappers, mas não herdava seus Impression/Tracking/Error. O JS de referência nem seguia os Wrappers.
- Os transportes substituíam `[CACHEBUSTER]`, mas não `[CACHEBUSTING]`. O Python usava identidade fixa Pixel/Chrome em vez do User-Agent do runtime.

A inspeção do provider foi estática, com decodificação limitada de dados base64/zlib, **sem executar o código do addon**. Nenhuma URL de serviço, credencial, configuração de usuário ou fonte integral extraída foi adicionada ao Git. O provider e seu pacote não são modificados.

## Snapshot antes de substituir o player

`ads_resume.capture` mantém em memória da sessão:

- caminho exato reproduzido, query/tokens e pipe headers sem reconstrução;
- URL real já extraída do proxy, quando disponível;
- referência nativa do ListItem e metadados `Player.GetItem`;
- timestamp VOD, estado de pausa e classificação ao vivo originais;
- alternativas já resolvidas e vinculadas ao **mesmo conteúdo**.

A posição é atualizada imediatamente antes do anúncio, após a busca da tag. Se só houver `plugin://` e nenhum destino direto, o anúncio não interrompe o conteúdo: não se destrói um contexto que não pode ser retomado com segurança.

## Retomada direta

- Usa `xbmc.Player.play(url, listitem, windowed=False)`, nunca a rota de escolha do addon.
- Ajusta somente os sinais de roteamento do ListItem: caminho direto, `ForceResolvePlugin=false`, remove `original_listitem_url` e configura o offset da sessão. Metadados/arte/inputstream/headers do item são preservados.
- VOD: espera o player, aplica seek, confirma tolerância de 250 ms e observa progresso estável. Não usa apenas `isPlayingVideo()` como prova de sucesso.
- Ao vivo: reprodução limpa, sem seek; exige progresso. Retira o ponto de resume do ListItem quando a API permite.
- Erro do player, ausência de progresso ou seek não confirmado tenta a próxima alternativa salva, com orçamento total limitado a 24 s, dividido entre as rotas disponíveis.
- Uma seleção nova do usuário não deve ser parada nem receber o seek da sessão antiga.
- Retorno por outro servidor/proxy é migrado para a mesma oportunidade lógica do monitor: não dispara outro anúncio só porque a URL mudou.

### De onde vêm os servidores alternativos

Não se transforma página de hoster em MP4 por suposição. As fontes de alternativas são:

1. stream atual e URL real do proxy, já resolvidos antes do anúncio;
2. slots de mídia diretos do contrato real `#movies_list=` na rota original do Brazuca, quando essa rota está disponível no item/estado;
3. itens de playlist com identidade explícita do mesmo filme/episódio (o próximo episódio nunca é fallback);
4. streams resolvidos anteriormente para a mesma rota de conteúdo, em cache de memória limitado a 8 conteúdos/10 minutos;
5. contexto opcional de provider `publish_context`, consumido uma única vez e vinculado à URL atual; não é presumido como integração existente de todo addon.

A lista bruta de slots disponíveis é mantida em `available_servers`, mas páginas Mixdrop/Streamtape/Doodstream e rotas que ainda precisam de resolver/diálogo **não são executadas na retomada**. Se o provider não expõe outras URLs já resolvidas, só as rotas diretas efetivamente capturadas podem ser tentadas. Renovação arbitrária de tokens/links de todos os hosters não é implementada nem garantida.

Não há diálogo de erro da aplicação entre tentativas. Diálogos nativos do core Kodi em falhas de rede/decoder não podem ser universalmente suprimidos por este addon; se todos os destinos expirarem/falharem, não se inventa sucesso. A eliminação do seletor é garantida pelo caminho de código (sem chamadas plugin), não por esconder janelas de erro do usuário.

## Impressões e tracking

- A cadeia selecionada acumula **todos** os nós `<Impression>` de cada Wrapper e do Inline, preservando inclusive nós distintos com o mesmo URL.
- Também herda Tracking e Error dos Wrappers. Não mistura anúncios/ramificações não selecionados.
- A busca/resolução do XML não envia impressão. Impressões/start são emitidos no início efetivo da mídia e somente uma vez por evento de sessão; falha/no-fill antes da mídia não gera impressão.
- Falha gera Error quando há URL correspondente. Não gera `complete` falso.
- Macros: `[CACHEBUSTING]`, `[CACHEBUSTER]`, `[RANDOM]`, `[TIMESTAMP]`, `[ERRORCODE]` e `[DEVICEUA]`, incluindo formas `%5B...%5D` e `%%...%%`. Cachebuster tem 8 dígitos. Macros desconhecidas não recebem identificadores inventados.
- Browser: pixels via Image mantido vivo até load/error ou limpeza limitada. O navegador envia seu **próprio User-Agent real**; JS não tenta forjar esse header. No WebView Android, usa a identidade configurada pelo próprio WebView.
- Kodi/Python: todas as Requests usam `xbmc.getUserAgent()`. Se a API não estiver disponível mas Android for confirmado, fallback honesto `Kodi (Android)`; fora do Kodi usa o UA Python real. Não há mais modelo Pixel ou versão Chrome fabricados. A mesma identificação é usada no transporte da tag. TLS mínimo 1.2, certificado/hostname verificados, continuam obrigatórios.
- Tracking permanece assíncrono e best-effort: uma Request emitida não prova recebimento/contabilização pela rede de anúncios. CORS, ad blockers, DNS/TLS ou falta de rede podem bloquear pixels; isso não deve travar a retomada.

## Escopo e testes

Dois módulos de anúncios isolados novos: `ads_resume.py` e `ads_tracking.py`. O plano continua bloqueando alterações de skin, XMLs, manifesto, bibliotecas e inicialização. AdMob continua isolado e desativado. As correções anteriores de frequência, watchdog e botões Dropbox permanecem.

Testes com doubles/HTTP interceptado:

- `test_resolved_resume.py`: VOD, live, seek, token/stream que falha, segundo servidor, stall na retomada, item/headers, troca do usuário, playlist de episódios e contextos antigos.
- `test_ads_regressions.py`: término, pulo e aborto chamam retomada direta; congelamento em 5 s continua abortando após 3 s.
- `test_ad_openings.py`: troca de URL no fallback não cria outra oportunidade de anúncio.
- `test_vast_tracking.py` e `test-vast-tracking.js`: dois Wrappers + Inline com seis impressões, URLs duplicados, macros, User-Agent real do runtime simulado, no-fill, recusa de playback e ciclo de Wrappers.
- CI repete testes Python sobre os módulos originais corrigidos, além de validar assinatura/alinhamento e comparar todas as entradas do APK.

Teste de cold start, codecs, tokens reais e recebimento de pixels em aparelho/rede de anúncios continua necessário. Testes determinísticos não constituem validação de hardware nem de receita de anúncios.
