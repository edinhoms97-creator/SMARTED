# SMARTEDTV

App Android TV baseado em **Kodi Omega 21.3** com tela de boas-vindas/ativação
(HTML + addon Kodi), skin personalizada e fluxo de assinatura via **Cakto**.

Este repositório foi montado em 2026-11-27 a partir dos arquivos do Dropbox
(`SMARTEDTV UNIVERSAL/SMARTEDTV.apk` e os ZIPs de código-fonte). Relatório
completo da inspeção: [`docs/INSPECTION.md`](docs/INSPECTION.md).

## Estrutura

```
smartedtv/                 Interface web de boas-vindas/ativação (PT-BR, D-PAD)
  index.html               Markup (test ids em todos os controles)
  css/styles.css           Design tokens + componentes
  js/config.js             TODAS as URLs externas (checkout Cakto, APK Dropbox)
  js/services.js           Camada de integração (payment, codeAccess, ads, appUpdate, share)
  js/app.js                Wiring de UI: D-PAD, diálogos, toasts, parallax
  assets/                  QR codes (checkout + APK) e favicon
  standalone/              Preview em arquivo único (offline) — rebuild: tools/build-standalone.py
  docs/HANDOFF.md          Guia de integração com os serviços existentes
kodi-addon/
  script.smartedtv.welcome/  Addon Kodi (Python + DialogWelcome.xml) — mesma tela, nativa
skin/
  skin.estilo.personalizado/ Skin Kodi "Nova TV" (base Estuary, 914 arquivos)
preview/
  PREVIEW_KODI.html        Preview das 44 telas da skin
tools/
  build-standalone.py      Gera o preview standalone a partir do fonte
docs/
  INSPECTION.md            Relatório da inspeção do APK e dos fontes
```

## Como rodar a interface web

Qualquer servidor estático serve. Na raiz do repositório:

```bash
python3 -m http.server 8000
# abrir http://localhost:8000/smartedtv/
```

Ou abra `smartedtv/standalone/smartedtv-preview.html` direto no navegador
(funciona offline, tudo inline).

## APK: preservar exatamente o SMARTED original

**O primeiro APK de teste foi retirado:** o usuário relatou travamento na tela inicial.
Ele adicionava skin/startup indevidos. A correção usa somente o original
`smartedtv.full` **1.0.161**, do link Dropbox abaixo.

O pipeline atual permite alterações apenas nos módulos de anúncios originais.
**Skin, layout, texturas, tela inicial, bootstrap, manifesto e recursos devem
permanecer idênticos byte a byte.** Nenhuma welcome/skin nova é empacotada.

Guia e evidências: [`docs/BUILD_APK.md`](docs/BUILD_APK.md).
Publicação sob demanda e desligada por padrão. CI não comprova funcionamento em aparelho.

## APK original (Dropbox)

- **Arquivo:** `SMARTEDTV.apk` — 263.222.483 bytes, `/SMARTEDTV UNIVERSAL/` no Dropbox
- **Link (compartilhar):** https://www.dropbox.com/scl/fi/ixfw289m0sibcyfyrxf9g/SMARTEDTV.apk?rlkey=z59708sngkysw0c1ntmmur6lv&st=okcfec6i&dl=0
- **Link (download direto):** o mesmo com `dl=1` — já configurado em `smartedtv/js/config.js`
- **Checkout (Cakto):** https://pay.cakto.com.br/nkvbegd_1323120

> O APK **não** está neste repositório (263 MB, binário). Ele é distribuído
> pelo link do Dropbox acima. Ver `docs/INSPECTION.md` para o que foi e o que
> não foi possível inspecionar no binário.

## O que está conectado e o que não está

| Ação | Estado |
|---|---|
| Abrir checkout Cakto | ✅ Real (abre em nova aba) |
| QR codes (checkout + APK) | ✅ Reais, regenerados para o link atual do APK |
| Compartilhar link | ✅ Web Share API → clipboard |
| Baixar APK / ATUALIZAR APLICATIVO | ✅ Abre o download do Dropbox (`dl=1`) |
| Ativar código VIP (10 min / 1 mês) | ⚠️ **Não conectado** — `codeAccess.activate()` responde `{connected:false}`. Ver `smartedtv/docs/HANDOFF.md` |
| Continuar com anúncios | ✅ **VAST Clickadilla** (Spot #1508180) — pre-roll + tracking + fallback limpo + retomada exata do VOD. Demo: `smartedtv/demo-vast.html`. AdMob isolado e desativado por flag (`docs/ADMOB.md`) |

Nada é simulado: enquanto os serviços não forem registrados, a interface
mostra explicitamente "ainda não conectado" em vez de fingir sucesso.

## Anúncios — validação

Implementação VAST Clickadilla e testes: [docs/VAST.md](docs/VAST.md).
AdMob mobile separado e desligado: [docs/ADMOB.md](docs/ADMOB.md).

`npm ci && npm test` executa os testes locais (Node + Python).
Demo de reprodução: `smartedtv/demo-vast.html`. Validação da tag real e
em dispositivos ainda pendente. O primeiro APK de teste foi reprovado e retirado; o pipeline corretivo preserva a interface original.
