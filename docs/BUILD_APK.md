# Build manual do APK universal SMARTEDTV

## O que este pipeline faz (e o que ele não faz)

O repositório contém a welcome web, addons Python e skin Kodi, **não contém o projeto Android/Gradle nem os fontes nativos do Kodi**. Logo, não é possível compilar o player Kodi/NDK do zero aqui em 5–10 minutos.

O pipeline reempacota um **APK-base Kodi existente**, preservando byte a byte todos os `classes*.dex` e bibliotecas `.so`. Decodifica os recursos com apktool, aplica os fontes atuais, registra os addons no manifesto Kodi, recompila os recursos, alinha e assina um único `SMARTEDTV-universal.apk` de teste. Não há WebView vazia fingindo ser o player, nem união de APKs incompatíveis.

**Compatibilidade universal neste build:** um único APK com ARM32 (`armeabi-v7a`) **e** ARM64 (`arm64-v8a`), bibliotecas correspondentes e a mesma Activity em Mobile, TV Box e Projetor **Android**. Arquiteturas adicionais já presentes são preservadas. Não promete x86 quando a base não o contém, nem compatibilidade com todo Android/hardware. SDK mínimo e ABIs constam dos relatórios. Roteamento de dispositivo não seleciona outro provedor de anúncios: VAST é o mesmo caminho, AdMob permanece desligado.

> A arquitetura do APK original ainda não foi inspecionada: o sandbox não acessa o Dropbox diretamente, e o conector não transfere o APK de 263 MB. O workflow **falha deliberadamente** se a base só tiver ARM32 ou só ARM64. Não inventa as bibliotecas ausentes nem publica um APK incorretamente chamado universal. Nesse caso, fornecer uma base Kodi genuinamente multi-ABI ou os fontes Android/NDK compatíveis.

## Execução manual

Arquivo: [`.github/workflows/build-universal-apk.yml`](../.github/workflows/build-universal-apk.yml).

**Primeiro registro no GitHub:** para um workflow com somente `workflow_dispatch` ser descoberto/disparável, seu arquivo precisa existir na branch padrão (`main`). O desenvolvimento e o push desta sessão continuam em `arena/16384c6f-smarted`; não há trigger de push para contornar essa restrição. Integrar a configuração por PR é uma ação separada; o pipeline não altera a branch padrão.

Depois de o workflow existir em `main`:

```sh
gh workflow run build-universal-apk.yml \
  --ref arena/16384c6f-smarted \
  -f publish_release=true

gh run list --workflow build-universal-apk.yml --limit 5
# Usar o ID real retornado:
# gh run watch ID --exit-status
# gh run download ID --name SMARTEDTV-universal --dir dist
```

Também disponível na aba **Actions → Build SMARTEDTV universal APK (manual) → Run workflow**, escolhendo a branch/revisão desejada.

- **Somente** `workflow_dispatch`. Sem push, PR, cron, workflow_run ou cascata após releases.
- Concorrência limitada por ref; não cancela um build em andamento.
- `base_url` + `base_sha256`: opcionais, mas obrigatoriamente fornecidos juntos para outra base. Só HTTPS e SHA256 validado. Não inserir links temporários/privados com credenciais em inputs públicos.
- `publish_release=true`: publica uma **pre-release de teste** com link direto para o APK apenas se todas as verificações passarem. Nunca promove automaticamente a versão estável.
- O build exige que `0fea261` seja ancestral da revisão e empacota os fontes dessa revisão completa, não um arquivo baixado de outra branch.

## Base fixada e cache

`android-build/base-apk.json` registra o link público fornecido, tamanho `263222483`, revisão Dropbox `016612000089f9e00000003401bbf21` e content hash verificado pelo conector em 2026-11-27:

```
03c2b45efbe3256e6c11f8cc9809babe133a90b180eb007cf5908f597643e277
```

Esse é o **Dropbox content hash**, não o SHA256 simples do arquivo. O helper implementa o algoritmo de blocos de 4 MiB. Ambos os hashes são calculados e relatados. A base é verificada mesmo quando veio do cache. Uma revisão trocada silenciosamente no Dropbox interrompe o build.

Apktool 2.12.1 fixado por SHA256 publicado na API do release upstream:

```
66cf4524a4a45a7f56567d08b2c9b6ec237bcdd78cee69fd4a59c8a0243aeafa
```

Caches: npm, APK-base por hash, Android build-tools 35.0.0, JAR apktool e chave **apenas de debug**. O runner Ubuntu já fornece SDK/cmdline-tools. Só instala build-tools se ausentes. Java 17, Node 22, Python 3.11. **Não há Gradle/NDK para cachear**, porque este é um reempacotamento dos fontes disponíveis, não um projeto Gradle.

## Tempo

Meta: **5–10 minutos com cache aquecido**, sem emulador, testes instrumentados ou compilação NDK. Testes unitários JS/Python + os 14 testes de empacotamento levam aproximadamente 1 segundo neste sandbox.

O job de build tem timeout de **8 minutos**, e o de publicação de **2 minutos**. Esse orçamento interrompe uma execução lenta, **não garante produzir um APK em dez minutos**. Fila de runners, primeiro download de 263 MB, indisponibilidade do Dropbox/GitHub/SDK, base inválida ou falhas de recursos/assinatura podem impedir a entrega. Não há medição de build Android completo até uma execução real concluir. Compressão do artefato desativada para não recomprimir o APK.

## O que entra no APK

- `assets/addons/script.smartedtv.welcome/`: VAST Python + adapter Kodi, incluindo no-fill, tracking e retomada com confirmação.
- `assets/addons/service.smartedtv.startup/`: abre a welcome uma vez por processo, mesma rota em todos os dispositivos Android.
- `assets/addons/skin.estilo.personalizado/`: skin do repositório (sem forçar sua seleção nas preferências existentes).
- `assets/system/addon-manifest.xml`: registro dos addons como ativos do sistema, não apenas cópia de arquivos inertes.
- `assets/smartedtv/`: fontes web exatos da revisão, VAST JS e AdMob isolado com flag `false`. Kodi executa o caminho Python; embutir o HTML não instala um runtime WebView/SDK AdMob.
- `assets/smartedtv-build.json`: revisão Git completa e flags de anúncios para proveniência.
- Manifesto Android: mesma Activity MAIN para LAUNCHER e LEANBACK_LAUNCHER; touchscreen/faketouch/leanback/television opcionais; banner TV e permissão INTERNET; sideload normal (sem `testOnly`). Mantém package ID e SDK da base.

Não inventa canal, endpoint VIP, status de pagamento ou bridge AdMob. A welcome fecha e o fluxo Kodi existente continua; para iniciar conteúdo sem vídeo ativo, o addon principal deve fornecer seu destino. Não ativa automaticamente a nova skin nem remove serviços customizados desconhecidos da base. Deve-se verificar possíveis fluxos de inicialização já existentes no teste real.

## Verificações obrigatórias antes de entregar

1. Base: hash confiável, tamanho quando é a base padrão, CRC ZIP, caminhos seguros e assinatura válida.
2. ABIs: ARM32+ARM64 reais, cabeçalho ELF correspondente a cada diretório, mesmo conjunto de dependências nativas.
3. Fontes: revisão contém `0fea261`; árvore rastreada limpa; AdMob desativado; tag #1508180 presente.
4. Assinatura de teste automática com `keytool`/`apksigner`, esquemas v1+v2+v3.
5. `apksigner verify --verbose --print-certs` após assinatura.
6. `zipalign -P 16 -c -v 4` no APK assinado.
7. `apkanalyzer manifest print` no manifesto **compilado**; valida package/SDK/rota contra o manifesto preparado. `aapt2 dump badging` incluído no relatório.
8. Conteúdo: todo arquivo web/addon/skin comparado byte a byte com a revisão; registro Kodi conferido; SHA256 de todos os Dex/libs idêntico ao da base.
9. SHA256 do APK final publicado ao lado do arquivo. Falha em qualquer gate impede publicação do APK; apenas diagnósticos são enviados em caso de erro.

Alinhar o ZIP em 16 KiB **não** recompila bibliotecas ELF feitas só para páginas de 4 KiB. Suporte nativo a aparelhos Android com páginas de 16 KiB depende da base. Sem testes de hardware, a instalação/reprodução não pode ser certificada.

## Download e instalação

Após **sucesso real**, a aba Summary do job `publish` e a pre-release gerada exibem o link direto de `SMARTEDTV-universal.apk`. O job `build` também tem um artefato ZIP `SMARTEDTV-universal` (retenção de 14 dias; pode exigir login GitHub). Cada pre-release aponta para a revisão exata e contém o checksum e os relatórios. Nenhum link de APK novo é válido antes desse sucesso.

**Assinatura de debug não atualiza o APK original assinado com outra chave.** Fazer backup; pode ser necessário desinstalar a versão anterior (apagando dados). A chave de debug é cacheada, não uma chave de produção; perda/expiração do cache pode mudar o certificado entre testes. Não distribuir este build como release de produção, nem versionar keystores.

## Reproduzir os gates localmente

```sh
npm ci
npm test
python3 -m unittest discover -s tools -p 'test_apk_pipeline.py' -v
npm run build:standalone
# Com JDK 17, SDK build-tools 35 + cmdline-tools e o JAR fixado:
# export ANDROID_HOME=/caminho/android-sdk
# export APKTOOL_JAR=/caminho/apktool_2.12.1.jar
# bash tools/build-universal-apk.sh
```

Artefatos, downloads, diretórios de trabalho e chaves ficam em `dist/` / `.cache/`, ignorados pelo Git. A validação real do VAST e da retomada no aparelho permanece obrigatória: [VAST.md](VAST.md).
