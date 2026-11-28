# SMARTED original — somente anúncios, sem alterar a skin

## Build atual: base 3 s / 5 s + transição sem menus

Builds e relatórios: [Releases de teste](https://github.com/edinhoms97-creator/SMARTED/releases). Consulte a revisão `Fonte` de cada release; builds antigos de startup 3,5 s/fallback não representam esta restauração.

O motor e a seleção de mídia foram restaurados à revisão `b86570a`, com os timings originais (startup até 8 s, stall 3 s, margem duração + 5 s, teto 35 s). `_tocar` permanece original. Somente o mapeamento de pixels e a transição/retomada sem menus são adicionados à base. Não há novo player, overlay, filtro MP4, fallback entre arquivos de anúncio ou auto-PlayPause.

Testes protegem a AST do controle e a seleção MediaFile contra mudanças, e verificam limpeza seletiva dos menus de player/legendas após início real e retorno confirmado. Detalhes, escopo e roteiro no celular: [VAST_BASE_TRANSITION.md](VAST_BASE_TRANSITION.md).

**Não foi possível executar teste Android prático: sem adb, SDK/emulador ou KVM neste ambiente.** Testes de doubles/CI não comprovam decoder, superfície ou foco no aparelho. A assinatura é de teste.

### Retomada e pixels

Snapshot em RAM preserva stream resolvido, ListItem, metadados, posição e alternativas diretas. Término, skip e aborto retomam sem chamada ao seletor do plugin; uma alternativa salva é tentada se a anterior falhar. **Não resolve automaticamente páginas de hosters nem garante renovar links expirados.** Todos os Impression dos Wrappers selecionados são herdados, com macros expandidas e User-Agent real do runtime. AdMob permanece desativado. Ver [VAST_RESUME_TRACKING.md](VAST_RESUME_TRACKING.md) para detalhes e limites.

### Regra de frequência solicitada

Sem intervalo de dois minutos: uma oportunidade VAST por abertura real de canal, filme, episódio ou outro VOD. A tentativa fica registrada antes de agendar o anúncio, evitando duplicidade. No-fill, timeout ou falha liberam o conteúdo sem outra tentativa na mesma abertura; só uma reprodução válida conta como anúncio exibido. Pause, seek, reconexão e retorno do anúncio não são novas aberturas. Trocar de conteúdo ou fechar e reabrir permite nova tentativa. VIP permanece isento; AdMob segue desativado.

Foram adicionadas regressões para sete conteúdos consecutivos, falha de reprodução, vídeo sem imagem/progresso, callback antigo e retomada sem sobrescrever uma nova seleção do usuário. Isso não garante disponibilidade de anúncios nem compatibilidade de codecs em hardware.

### Watchdog de 3 segundos e botões Dropbox

Nesta revisão, congelamento por três segundos, erro do decoder ou limite absoluto encerram a peça e acionam a retomada. Amostragem a cada 500 ms; teto mínimo entre duração + 5 s e 35 s, com o tempo da tag/início descontado. Seleção conservadora de MP4, preferência por 720p AVC baseline/main quando declarado.

Baixar/Atualizar/Compartilhar apontam para o `SMARTEDTV.apk` oficial com `dl=1`. O arquivo do Dropbox não foi substituído pelo APK de teste do GitHub; instalação/download dependem do Android/navegador e da confirmação do usuário.

Inspeção do fluxo original, limitações e cenários: [VAST_WATCHDOG.md](VAST_WATCHDOG.md).

## Correção de escopo

O build `7e300f2` foi **reprovado pelo usuário: não passou da tela inicial**. Ele preservava os Dex/libs, mas isso não bastava: copiava uma skin separada, adicionava welcome/serviço de startup e modificava o manifesto. Foi retirado da publicação pública (release convertida em rascunho). Seus testes de empacotamento não comprovavam funcionamento no aparelho.

Não usar esse build nem considerá-lo base para a correção. O empacotamento antigo e a cópia de skins foram removidos do pipeline.

## Identidade do APK correto

A auditoria somente leitura no runner GitHub confirmou o APK do **mesmo link Dropbox fornecido pelo usuário**:

- Pacote: `smartedtv.full`.
- Versão: `1.0.161`; versionCode `2103147`.
- Launcher original: `smartedtv.full.Splash`.
- ABIs originais: `arm64-v8a` e `armeabi-v7a`.
- Skins próprias: `skin.smartedtv.classic` e `skin.novatv`, ambas versão `1.0.17` (nome SMARTEDTV), além da Estuary de fábrica.
- Bootstrap original: `service.smarted.bootstrap` versão `1.0.9`.
- Tamanho: 263.222.483 bytes.
- Content hash Dropbox: `03c2b45efbe3256e6c11f8cc9809babe133a90b180eb007cf5908f597643e277`.
- Metadados e URL fixados em `android-build/base-apk.json`. Outra base está proibida neste fluxo.

Auditorias: [identidade](https://github.com/edinhoms97-creator/SMARTED/actions/runs/45990816856), [contratos dos módulos de anúncios](https://github.com/edinhoms97-creator/SMARTED/actions/runs/45991553860). Nenhum APK foi gerado nessas auditorias.

## Mudanças permitidas

Plano explícito: `android-build/ads-only-plan.json`.

1. `assets/addons/service.smarted.bootstrap/ads_vast.py`: funções revisadas de transporte/tracking, reprodução, falhas e confirmação da retomada. Parser e auxiliares originais fora do escopo são preservados.
2. `assets/addons/service.smarted.bootstrap/smart_ads.py`: seleção VAST, reprodução, reserva da oportunidade e métodos revisados de `MonitorPreRoll` para agendamento, resultado assíncrono e encerramento real do conteúdo. Demais funções/métodos são preservados.
3. `assets/addons/service.smarted.bootstrap/ads_regra.py`: elegibilidade por abertura e `INTERVALO = 0`, sem cooldown; auxiliares de armazenamento/transição permanecem originais.
4. `assets/addons/service.smarted.bootstrap/ads_admob.py`: configuração inerte separada, com IDs fornecidos e `ENABLED = False`. Nenhuma inicialização de SDK, novo serviço ou chamada de bridge.

5. `assets/addons/service.smarted.bootstrap/vip.py`: apenas constantes `APK`/`DROPBOX_URL` e sete funções de ação/resolução do link oficial. Validação de código VIP, pagamentos e demais funções permanecem com AST original.

6. `assets/addons/script.smartedtv.welcome/default.py`: somente `APK_DOWNLOAD`, `DROPBOX_URL` e helper `_link_do_dropbox_desta_versao`; classes/métodos e XML/layout originais inalterados. O download original também deixa de depender da pasta por variante ao consultar `vip.dropbox_configurado`.

7. `assets/addons/service.smarted.bootstrap/ads_resume.py`: helper isolado de snapshot e retomada direta, com fallback entre streams resolvidos capturados.
8. `assets/addons/service.smarted.bootstrap/ads_tracking.py`: helper isolado de macros e User-Agent real do runtime.

Os hashes dos cinco arquivos originais são conferidos antes de qualquer patch. Uma base de outra revisão faz o build falhar. As alterações de funções/métodos são feitas por intervalos do fonte; uma comparação AST exige que todos os nós não relacionados permaneçam iguais.

## O que não pode mudar

**Todo arquivo fora da lista acima**, exceto metadados criptográficos de assinatura do APK, deve ser idêntico ao original. Isso inclui:

- Todas as skins originais e suas imagens, texturas, XMLs, scripts, layouts e configurações.
- `AndroidManifest.xml` binário, `resources.arsc`, ícone, nome, versão e launcher.
- Bootstrap `service.py`, registros `addon.xml`/`assets/system/addon-manifest.xml` e preferências de interface.
- Bibliotecas nativas, Dex, plugins, seed/perfil embutido e fluxos de validação VIP/pagamento (o nome `vip.py` também abriga os handlers de link revisados acima).

Não há substituição pelo HTML do repositório, nenhuma cópia de `skin.estilo.personalizado`, nenhum `script.smartedtv.welcome` novo nem `service.smartedtv.startup`. Os fontes web/welcome separados continuam disponíveis no Git como referência, mas **não entram neste APK**.

## Empacotamento e verificações

O novo pipeline **não usa apktool para reconstruir recursos ou manifesto**. Faz patch ZIP dos oito caminhos permitidos sobre o APK original, preserva os demais conteúdos, executa zipalign e assina para teste.

`tools/apk_preservation.py` compara SHA256 de **todas** as entradas antes e depois da assinatura. Qualquer modificação/remoção/adição fora da lista bloqueia publicação. Arquivos META-INF que não são assinatura também devem ser preservados. A mudança de certificado e bloco de assinatura é inevitável sem a chave original.

O pipeline também:

- Confere hash do APK original e integridade de sua assinatura.
- Executa testes rápidos JS/Python existentes e testes negativos de proteção da skin/manifesto/startup.
- Testa o parser e as funções **do próprio original já corrigido** com doubles de rede/player; isso é separado da demo welcome.
- Verifica TLS 1.2+ com certificado/hostname, UA real do Kodi, no-fill, fallback, tracking sem complete falso e seek confirmado.
- Executa `apksigner verify`, `zipalign -c`, gera badging e checksum final.

**Nada disso substitui teste de inicialização e reprodução em aparelho.** Não declarar o travamento corrigido apenas porque o CI passou. `preservation.json` comprova o escopo dos arquivos, não a reprodução em hardware.

## Workflow manual

`.github/workflows/build-universal-apk.yml`: somente `workflow_dispatch`. Publicação é **false por padrão**; só ocorre com solicitação explícita.

```sh
gh workflow run build-universal-apk.yml --ref arena/16384c6f-smarted -f publish_release=true
```

Não aceitar `base_url`/`base_sha256` alternativos: os campos antigos permanecem somente para compatibilidade do registro, e o helper recusa overrides. Cache da base é revalidado por hash em toda execução; chave de debug é cacheada separadamente. Sem emulador, NDK/Gradle ou recompilação de skin.

Alterações corretivas estão na branch da sessão e no PR #2; nenhuma integração adicional à main foi executada nesta correção.

## Instalação de teste

A assinatura é de debug, diferente da chave do APK original. Não substituir uma instalação assinada com outra chave esperando atualização direta. Fazer backup antes de qualquer remoção; remover app pode apagar dados. Uma instalação limpa pode ajudar a separar dados persistidos da versão anterior, mas não deve ser imposta sem backup.

O build corretivo acima concluiu e publicou seu relatório de preservação. O APK anterior foi retirado por falha relatada no dispositivo; não reutilizar o link antigo. O novo deve ser testado no aparelho antes de ser considerado aprovado.
