# SMARTED original — somente anúncios, sem alterar a skin

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

1. `assets/addons/service.smarted.bootstrap/ads_vast.py`: apenas as funções de tag, transporte/tracking, reprodução do anúncio e confirmação de retomada. O parser, wrappers/VMAP e as rotas de reconexão originais são preservados.
2. `assets/addons/service.smarted.bootstrap/smart_ads.py`: somente a função `motor_anuncio`, que retorna VAST para todos os dispositivos durante a validação. Todo o restante do módulo, inclusive frequência/VIP e fluxo original, permanece igual.
3. `assets/addons/service.smarted.bootstrap/ads_admob.py`: configuração inerte separada, com IDs fornecidos e `ENABLED = False`. Nenhuma inicialização de SDK, novo serviço ou chamada de bridge.

Os hashes dos dois arquivos originais são conferidos antes de qualquer patch. Uma base de outra revisão faz o build falhar. As alterações de funções são feitas por intervalos do fonte; uma comparação AST exige que todos os nós não relacionados permaneçam iguais.

## O que não pode mudar

**Todo arquivo fora da lista acima**, exceto metadados criptográficos de assinatura do APK, deve ser idêntico ao original. Isso inclui:

- Todas as skins originais e suas imagens, texturas, XMLs, scripts, layouts e configurações.
- `AndroidManifest.xml` binário, `resources.arsc`, ícone, nome, versão e launcher.
- Bootstrap `service.py`, registros `addon.xml`/`assets/system/addon-manifest.xml` e preferências de interface.
- Bibliotecas nativas, Dex, plugins, seed/perfil embutido e fluxos de VIP/pagamento.

Não há substituição pelo HTML do repositório, nenhuma cópia de `skin.estilo.personalizado`, nenhum `script.smartedtv.welcome` novo nem `service.smartedtv.startup`. Os fontes web/welcome separados continuam disponíveis no Git como referência, mas **não entram neste APK**.

## Empacotamento e verificações

O novo pipeline **não usa apktool para reconstruir recursos ou manifesto**. Faz patch ZIP dos três módulos permitidos sobre o APK original, preserva os demais conteúdos, executa zipalign e assina para teste.

`tools/apk_preservation.py` compara SHA256 de **todas** as entradas antes e depois da assinatura. Qualquer modificação/remoção/adição fora da lista bloqueia publicação. Arquivos META-INF que não são assinatura também devem ser preservados. A mudança de certificado e bloco de assinatura é inevitável sem a chave original.

O pipeline também:

- Confere hash do APK original e integridade de sua assinatura.
- Executa testes rápidos JS/Python existentes e testes negativos de proteção da skin/manifesto/startup.
- Testa o parser e as funções **do próprio original já corrigido** com doubles de rede/player; isso é separado da demo welcome.
- Verifica TLS 1.2+ com certificado/hostname, UA Chrome Android, no-fill, fallback, tracking sem complete falso e seek confirmado.
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

Aguardar resultado do build corretivo e conferir seu relatório de preservação antes de usar o novo link. O APK anterior foi retirado por falha relatada no dispositivo.
