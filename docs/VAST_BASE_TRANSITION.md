# Base VAST 3 s / 5 s + correção isolada dos menus

## Escopo atual solicitado

Referência: `b86570a`, primeira revisão após o watchdog de 3 s sem avanço e margem de duração + 5 s. O fluxo foi restaurado a essa revisão, não à revisão posterior `bbd253a` de startup 3,5 s/fallback/diagnóstico.

- `_tocar` original do APK permanece intacto: PlayMedia nativo, sem novo player, overlay ou Activity.
- Startup original de até 8 s; amostragem de 500 ms; watchdog de 3 s sem avanço; margem de duração + 5 s e teto de 35 s. Sem novo corte de startup em 3/3,5 s.
- Seleção MediaFile original, idêntica à base (incluindo seus limites originais). Sem fallback entre MP4s de anúncio, novo filtro 720p/3000 kbps ou mudança de ordem.
- Gatilhos/callbacks e regra da base restaurados. Removidas as mudanças posteriores de startup do monitor, auto-PlayPause, hooks de clique e módulo de diagnóstico persistente.
- AdMob continua desativado, VIP isento e uma tentativa por abertura, conforme a base.
- As ações oficiais de download/atualizar/compartilhar já corrigidas permanecem fora do motor VAST; nenhuma mudança visual.

O mapeamento de pixels solicitado anteriormente é preservado como instrumentação: todos os Impression dos Wrappers/Inline selecionados, CACHEBUSTER/CACHEBUSTING e Error. A consulta da tag volta ao perfil de headers da base (UA Chrome Android fixo **legado**, não apresentado como identificação real do aparelho). **Pixels** usam explicitamente o UA real do runtime Kodi. Não há garantia de recebimento/contabilização pelo provedor.

## Única intervenção de reprodução: transição sem menus

O helper de transição fica em `ads_resume.py` e só é armado:

1. depois que o loop original confirma início/progresso do anúncio;
2. depois que a retomada direta VOD/live é confirmada.

Uma thread de UI não bloqueante observa por até 5 s apenas o stream exato da sessão. Essa janela é exclusiva de limpeza de UI, **não altera nenhum timeout/watchdog da mídia**. Ela termina se o usuário abrir outro conteúdo.

Janelas reconhecidas no Kodi Omega:

- `10153`: busca/download de legendas;
- `10159`: configurações OSD de legendas;
- `12000`: seleção nativa, somente se o título indicar player/captions/subtitles/legendas/servidor ou a lista contiver nomes reconhecidos de players;
- `10106`: menu de contexto usado por PlayerCoreFactory, somente se os botões contiverem nomes de players (ex.: VideoPlayer, MX Player, VLC).

Não há `Dialog.Close(all)`, escolha automática de item, input de teclas, desativação de faixas de legenda, alteração de playercorefactory.xml, preferência global de player ou arquivo de skin. Menus genéricos de idioma, biblioteca, PIN/VIP/pagamento e diálogos de outro filme não são fechados. Diálogos customizados desconhecidos não são cancelados indiscriminadamente.

Na retomada, o stream/ListItem/metadados/posição são preservados e reproduzidos diretamente, com ForceResolvePlugin removido. A rota do provider não é reaberta, evitando recriar o seletor de servidor/legenda. Um retorno por URL direta/proxy alternativa continua sendo a mesma abertura, não gera um segundo anúncio. Não se adicionou resolução genérica de hosters.

## Proteções automatizadas

`npm run verify` executa os testes rápidos sem emulador, incluindo:

- hash canônico da AST de `reproduzir` contra a base, ignorando **somente** construção de pixels Error e a chamada de limpeza de menu; término/quartis/callbacks e todo controle permanecem comparados;
- hash da seleção `_media_escolhido` contra a base, sem exceções de comportamento;
- anúncio saudável de 25 s, decoder iniciando em 4 s, congelamento em 5 s com aborto após outros 3 s e limite duração + 5 s/35 s;
- menus nativos de player/legenda, menu atrasado, limite da guarda, nova seleção do usuário, menus não relacionados preservados;
- término/pulo/aborto: chamada da guarda após início real e retorno direto com seek confirmado;
- Wrapper/Inline/macros, no-fill sem tocar no conteúdo, preservação de todas as entradas do APK.

Fingerprints de referência (sem diferenças autorizadas):

- controle: `a10b78c4e558ff3ad36a0609f60f9cbb1e2b854a46595a2e4b6d81a21497ccc5`;
- MediaFile: `f16a53d8f5120e2abc9b7b301dd40cf894d75c351071bc42e8b537795a7591b5`.

O build repete os testes contra os módulos do **APK original corrigido**, além de assinatura, alinhamento e inventário de preservação. O plano volta a oito caminhos; `ads_diagnostics.py` não é empacotado.

## Android celular: situação real desta execução

**Teste Android prático não executado.** Foram procurados `adb`, `emulator` e SDK/imagens nos diretórios usuais; nenhum foi encontrado. `/dev/kvm` também não existe. Não há aparelho Android conectado/disponível por ferramenta nesta sessão.

Os testes com doubles de Kodi não são teste de Android, decoder, surface, toque, foco ou entrega de anúncio real. O APK é um build de teste para validação no celular, **não uma aprovação prática em Android**.

Roteiro ainda necessário no aparelho:

1. Fazer backup antes de qualquer troca de instalação; a assinatura de teste pode não atualizar o APK original.
2. Abrir filme e reproduzir um anúncio real saudável até o final; observar que não é cortado em 1/3/5 s apenas pelo relógio total.
3. Confirmar que menus automáticos de player/captions/legendas não ficam sobre a reprodução ao iniciar o anúncio ou retornar ao filme.
4. Repetir com pulo e aborto por ausência de progresso, conferindo retorno direto e posição do VOD; em live, retorno sem seek.
5. Verificar controles normais de pausa/play da base, no-fill e VIP. Registrar qualquer diálogo customizado que permaneça para identificá-lo sem fechar menus indiscriminadamente.

A ausência de emulador/Android não foi escondida por um teste marcado como aprovado.
