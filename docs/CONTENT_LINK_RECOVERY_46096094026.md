# Conteúdos — recuperação de conexão, build 46096094026

## Entrega para teste físico, não diagnóstico confirmado da rede do aparelho

- [APK universal ARM32 + ARM64](https://github.com/edinhoms97-creator/SMARTED/releases/download/smarted-content-46096094026-1/SMARTEDTV-universal.apk).
- [Release, diff e auditoria](https://github.com/edinhoms97-creator/SMARTED/releases/tag/smarted-content-46096094026-1).
- SHA-256: `a54bd66daf8cf44e60aedb21868b3242020630144be958f877a01d06f399379b`; **263.239.378 bytes**.
- Fonte do APK: `7aefb23ec9c248b28a55fa25043e285f975701fd`; [build aprovado](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46096094026).
- Base **exata** fisicamente confirmada pelo usuário: **46084100325**, SHA-256 `6510b917a159e2b8ab216289ada2e4b2015aa4b29fa81809caa120fc7fe8f0a2`.
- Novo contêiner reconstruído, alinhado 16 KB e assinado; certificado igual ao APK-base. Identificador da entrega é o run/release, não um novo versionCode: Manifest foi preservado.

## O que foi encontrado

A frase sobre “operadoras bloqueando / 1.1.1.1 + WARP” pertence ao `default.py` compactado do Brazuca, em tratamentos amplos de exceção. O texto é genérico: também aparece quando a consulta retorna vazio/HTML inesperado ou outra exceção. **O texto não é prova de bloqueio da operadora.** A mensagem não foi removida nem escondida.

Os APKs foram lidos e suas camadas base64/zlib descompactadas estaticamente, sem executar o addon para inspecioná-lo. Não foram trocadas as fontes, credenciais do addon, catálogo, servidores disponíveis ou o protocolo de resolução de links.

### Domínios e requisições rastreados

| Componente existente | Resultado real no runner |
|---|---|
| `https://www.overflix.download/` | DNS e TLS funcionando; HTTP 301 para `https://www.overflix.living/`, depois 200 |
| `/index.php?app=videobox&module=video&controller=view&do=playerData&id=<id>` no domínio antigo | Com AJAX original: HTTP 200, JSON de redirecionamento para o domínio atual |
| Mesmo endpoint no domínio atual | Com `X-Requested-With: XMLHttpRequest` e Referer do conteúdo: HTTP 200 e JSON com `players`, `servers_dub`, `servers_leg` |
| Mesmo endpoint **sem** cabeçalho AJAX | Redireciona para HTML e retorna 403; é um controle negativo, **não** evidência de que o addon original omitia esse cabeçalho |
| `api.geekantenado.online` / `geekantenado.fly.dev` | DNS/TLS funcionando; acesso à raiz **sem token** retorna 403 “Token não fornecido”. Isso é controle de autenticação, não bloqueio DNS. Credenciais e chamadas autenticadas originais não foram alteradas. |
| Servidor selecionado `mixdrop.ps` | Nos quatro casos testados, redirecionou para `mxdrop.click` e retornou HTTP 200 |

O código do addon instala `codec.DNSOverride` no processo: ele tenta UDP/53 em `1.1.1.1`, `8.8.8.8`, `9.9.9.9`, com **5s por servidor**, antes de recorrer ao resolvedor do sistema. Se UDP/53 estiver indisponível, são até 15s extras por nome/consulta sem cache; tentativas HTTP adicionais podem amplificar a demora. O timeout HTTP existente é `(5, 10)` — conexão/leitura — e não elimina esse caminho UDP anterior.

**Limite da conclusão:** no runner, tanto DNS nativo quanto UDP do addon funcionaram (UDP observado em 0,012s). O defeito relatado no telefone **não foi reproduzido nessa rede**; não é possível afirmar qual requisição específica falhou no aparelho sem seu log. A longa espera é compatível com o caminho de DNS/retries, mas isso não prova a causa exata da rede móvel. O novo APK trata internamente essa classe de falha, comprovada com injeção controlada; a confirmação do caso real depende do novo teste físico.

## Alteração exclusiva no transporte de links

No addon instalado, apenas duas funções de consulta recebem a preparação da sua sessão HTTP:

1. `getMovieData`: obtenção de páginas e metadados de links.
2. `valide_v2`: verificação de disponibilidade dos links.

O novo helper `content_network.py` é carregado pelo próprio addon e vale **somente para essas sessões**:

- tenta primeiro o resolvedor nativo, sem passar pelo override UDP legado;
- se a resolução nativa falhar, consulta DNS por HTTPS em um serviço com certificado e hostname verificados;
- usa bootstrap IP do serviço DNS para não depender do mesmo DNS quebrado; conserva Host/SNI da consulta DNS;
- mantém URL, Host, SNI e validação TLS da conexão ao conteúdo; não substitui o hostname do vídeo por IP;
- preserva cabeçalhos AJAX, Referer, cookies, método e política de retries existentes;
- cacheia apenas respostas DNS positivas dentro do TTL, limitado a 300s; não cacheia falhas DNS;
- não muda `socket.getaddrinfo`, requests global, DNS do Android, proxy do usuário, outro addon ou o player;
- preserva o caminho cloudrequest existente, sem substituir seu adaptador;
- não é VPN, proxy de vídeo ou promessa de contornar bloqueio de rota/IP/TLS pelo provedor da conexão.

Nenhuma URL de fonte ou host de anúncio foi substituído. Nenhuma dependência requests/urllib3 foi atualizada dentro do APK.

## Auditoria do APK final

A comparação do APK assinado com o build 46084100325 encontrou **somente**:

- `assets/addons/service.smarted.bootstrap/repair.py`: na função `repair_profile`, uma chamada local de entrega ao Brazuca já instalado, com tratamento de falha. O restante dessa função e todos os demais bytes do módulo são preservados. Não altera a ordem do reparo existente, telas, navegação, threads ou esperas.
- `assets/addons/service.smarted.bootstrap/content_link_patch.py`: helper novo de instalação idempotente. Reconhece o contrato das duas funções, preserva todas as outras linhas e camadas compactadas, escreve atomicamente o código e registra hashes. Contrato desconhecido gera falha no log, sem substituir o addon inteiro.
- `assets/addons/service.smarted.bootstrap/content_network.py`: novo transporte, copiado somente para o addon de conteúdo existente.

O seed original do Brazuca dentro do APK **não foi modificado**. O ajuste é aplicado ao código efetivamente instalado no perfil, sem apagar configuração, atualizar outras dependências, substituir o addon inteiro ou perder as adaptações de navegação existentes.

**8.053 entradas anteriores preservadas byte a byte.** VAST completo e tela inicial completos são idênticos à base, inclusive orçamento por hop e correção de corrida inicial. AdMob, VIP, player, retomada, skin, navegação, demais addons, Manifest, bibliotecas nativas e recursos intactos. Recompactar o `default.py` altera seu blob, mas o verificador descompacta novamente e exige exatamente as inserções autorizadas; preserva cabeçalhos/comentários de todas as camadas externas.

Evidências: `evidence/content-link-recovery/source-preservation.json`, `signed-preservation.json`, e os diffs `content-functions.diff` (entrega) / `runtime-content-functions.diff` (duas funções) na release. As listas de alterações são verificadas novamente **depois** de alinhar e assinar. As regras de proteção de anúncios anteriores não foram relaxadas: o patcher de conteúdos tem sua própria allowlist fechada.

## Testes executados e o que NÃO comprovam

### Rede real — dois filmes e dois episódios

As funções de consulta/resolução foram extraídas dos APKs anterior/posterior, sem executar inicialização, router ou player. Diálogos de escolha foram automatizados; cache vazio isolado; rede HTTP/TLS real. Essa extração não executa o override global original do addon, portanto os tempos não medem toda a inicialização de rede do APK.

No [build 46096094026](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46096094026), o instalador extraído do APK assinado foi aplicado a uma cópia do addon antes dos testes de rede. A auditoria Android separada verifica a entrega ao perfil real. Resultados:

| Caso do catálogo atual | Anterior: selecionou / página do servidor | Novo: selecionou / página do servidor |
|---|---|---|
| Filme — Enfeitiçadas: Bem-vindos a Hexe | sim / 200 | sim / 200 |
| Filme — Street Fighter | sim / 200 | sim / 200 |
| Episódio — Os Anéis de Poder 1x1 | sim / 200 | sim / 200 |
| Episódio — Os Anéis de Poder 1x2 | sim / 200 | sim / 200 |

As quatro consultas posteriores retornaram em aproximadamente **1,44–1,69s** nesse runner. Não se atribui essa variação a um ganho comprovado no celular: o anterior também funcionava nessa rede.

Em rodada separada, o resolvedor nativo foi deliberadamente configurado para lançar `gaierror`; o DNS por HTTPS, o TLS e as respostas do provedor continuaram **reais**. Os quatro links foram selecionados novamente, em aproximadamente 1,95–2,48s; o teste afirmou que o fallback era de fato chamado (16 invocações para os dois domínios, incluindo acessos ao cache positivo). Não são respostas simuladas do provedor nem uma medição da falha do telefone.

**As páginas de servidor responderem 200 não significa que o vídeo começou a tocar no Kodi. Não foram executados o resolver final de mídia de terceiros nem a reprodução nativa de filmes/séries nesses testes de rede.** Contagem de plays nativos: não validada, não uma alegação de sucesso. VAST não foi consultado para fabricar aprovação do teste.

### Testes locais e regressões

- `npm run verify` passou localmente com dependências de teste instaladas e no build publicado.
- Sete testes do novo transporte: TCP HTTP real com DNS de falha injetado; preservação de cabeçalhos; TLS/SNI reais; aceitação apenas do certificado confiável e rejeição de certificado não confiável; TTL e ausência de cache negativo; nenhum monkeypatch global; política de retries preservada.
- Mesmos sete testes passaram com urllib3 **2.8.0** e **1.26.20**, sem alterar as bibliotecas do APK.
- Quatro testes adicionais do patcher: somente duas inserções; contrato desconhecido falha fechado; roundtrip das camadas compactadas e preservação de cabeçalhos/comentários; atualização local idempotente sem tocar settings.
- Skips dependentes de APK/Android das suítes históricas continuam identificados como skips; não contam como teste físico.

## Candidato anterior rejeitado por entrega incompleta

O primeiro candidato **46094787897** tinha o transporte testado, mas alterava só o seed do perfil. A auditoria Android **46095020202** instalou sobre a base sem apagar dados e comprovou que o addon instalado mantinha o código anterior e não recebia o helper. Foi marcado **NÃO INSTALAR** na release e não é a entrega desta tarefa.

Esse resultado motivou exclusivamente a entrega local pelo reparador já existente, descrita acima. Não houve mudança na tela inicial para contornar o problema. O JSON da falha anterior foi preservado em `android-upgrade-rejected-46094787897.json`.

## Atualização Android sobre a base confirmada — entrega verificada

[Run 46096302583](https://github.com/edinhoms97-creator/SMARTED/actions/runs/46096302583), Android 11 com tradução ARM, instalação real via `adb install -r -g`. Primeiro foi instalado e iniciado o build 46084100325; depois o novo APK foi instalado sobre ele, **sem limpar dados/perfil**. Nenhuma ABI ou biblioteca do APK foi substituída.

O registro `android-upgrade-current.json` confirmou `content_upgrade_delivered=true`:

- APK-base: `6510b917…fe8f0a2` (hash completo no início deste relatório).
- Addon **realmente instalado**, antes: `fb070528314c82622739a6bde1f0db4301cc1fd3df32158c57b7901a4cddb6d9`.
- Mesmo arquivo após entrega: `72925271b1ee4c1df570b2483f33ac2d17c783dab0e3b8ba0b7a39a7837908bf`.
- Helper efetivamente copiado ao perfil: `90499a0d3e59b066a0cba098c0102e259a54af5040bedbbd06967da2cef606df`, igual ao payload do APK.
- Auditoria do código instalado: somente `getMovieData` e `valide_v2`, todos os demais bytes descompactados preservados. O hash anterior do registro corresponde ao arquivo observado **antes** da atualização.
- Às `02:10:38 UTC`, a tela inicial existente registra carregamento e o vigia reconhece que ela assumiu o boot. Não houve mudança de código dessa tela.

A etapa original de reparo apenas instala o helper e faz as duas inserções locais; não apaga settings, não reinstala o Brazuca inteiro e não substitui a navegação que o addon instalado já continha. É por isso que foi necessária a chamada de entrega em `repair_profile`, em vez de simplesmente mudar o seed que não chegava à instalação anterior.

**Essa auditoria verifica instalação/entrega e hashes, não execução do novo transporte dentro do Python Android nem reprodução de filme/série. Os ciclos de conteúdo desse run não foram executados.** O código instalado em runtime difere do seed antigo, e o instalador verifica seu contrato antes de editar, sem forçar substituição por uma versão antiga. As consultas reais de rede descritas acima usaram a cópia do addon do APK com o mesmo instalador, fora do Kodi.

## Teste físico necessário

Instalar o APK candidato sobre o build 46084100325 e repetir um filme e um episódio na mesma conexão que falhava, **sem WARP e sem mudar DNS**. Confirmar não apenas escolha do servidor, mas início real do vídeo e controles originais. Se persistir, registrar horário e tela completa para correlacionar o log `smarted.content.links`; não basta trocar o texto do erro.

As correções de VAST e entrada foram preservadas por auditoria binária; nenhum merge ou atualização do Dropbox oficial foi feito. Até o teste físico, esta entrega deve ser tratada como **recuperação interna de DNS testada**, não confirmação de que a causa específica do aparelho foi eliminada.
