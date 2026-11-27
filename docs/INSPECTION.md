# SMARTEDTV — Relatório de inspeção (2026-11-27)

Inspeção feita a partir do link do Dropbox informado
(`SMARTEDTV UNIVERSAL/SMARTEDTV.apk`) e dos demais arquivos da conta Dropbox.
Tudo o que foi baixado está agora montado neste repositório.

## 1. O que foi encontrado no Dropbox

| Arquivo | Tamanho | O que é |
|---|---|---|
| `SMARTEDTV UNIVERSAL/SMARTEDTV.apk` | 263.222.483 bytes | O app (Kodi Omega 21.3 + skin + addons + dados). Modificado em 2026-11-25 |
| `smartedtv-src.zip` | 38.502 bytes | Código-fonte da interface web de boas-vindas/ativação → `smartedtv/` |
| `SMARTEDTV_Kodi_Omega_Welcome.zip` | 34.636 bytes | Addon Kodi `script.smartedtv.welcome` (Python + XML) → `kodi-addon/` |
| `skin.estilo.personalizado.zip` | 3.652.678 bytes | Skin Kodi "Nova TV" (base Estuary) → `skin/` (914 arquivos) |
| `PREVIEW_KODI.html` | 28.900 bytes | Preview das 44 telas da skin → `preview/` |
| `Kodi.for.Android.21.3.zip`, `kodi-21.3-Omega-arm64-v8a.apk`, `KODE-v1.0.13/14*.apk` | ~67–68 MB cada | Builds de referência/teste do Kodi (não montados) |
| `backup_part_aa` / `backup_part_ab` | 94 MB / 70 MB | Partes de backup (não montadas) |

## 2. Limitação: o binário do APK não pôde ser baixado neste ambiente

- O conector do Dropbox limita downloads a **100 MB**; o APK tem **263 MB**.
- A saída de rede do sandbox bloqueia `dropbox.com`/`dl.dropboxusercontent.com`
  (só GitHub/npm/PyPI são permitidos), então o download direto por `curl` também falha.
- **Consequência:** não foi feita análise estática do binário (sem `AndroidManifest.xml`,
  sem strings do DEX, sem verificação de permissões/assinatura). A inspeção cobriu
  todo o código-fonte disponível (interface web, addon Kodi e skin), que é onde
  vivem as telas e os fluxos editáveis.
- **Para inspecionar o binário depois:** baixar o APK localmente e rodar
  `unzip -l SMARTEDTV.apk` / `aapt dump badging SMARTEDTV.apk` / `apktool d SMARTEDTV.apk`,
  ou dividir o arquivo em partes < 100 MB no Dropbox.

## 3. Arquitetura identificada (a partir do fonte)

- **Base:** Kodi Omega 21.3 para Android (há `kodi-21.3-Omega-arm64-v8a.apk` na
  conta; o APK de 263 MB é ~4× maior que o Kodi puro, o que indica skin,
  addons e userdata embutidos).
- **Skin:** `skin.estilo.personalizado` ("Nova TV"), baseada no **Estuary**
  (Team Kodi), monocromática (preto fosco/branco/cinza), 4 layouts de Home
  (Aurora, Blade, Top 10, Esportes), `xbmc.gui 5.17.0` (Omega).
- **Tela de boas-vindas — 2 implementações da mesma referência visual:**
  1. **Web** (`smartedtv/`): HTML/CSS/JS 16:9, D-PAD por setas, PT-BR.
     Checkout Cakto, QR codes reais, share/download do APK, ativação por código
     (planos "10 min" e "1 mês") e "Continuar com anúncios".
  2. **Kodi nativa** (`kodi-addon/`): `WindowXMLDialog` com `DialogWelcome.xml`
     (1920×1080). Mesma tela, mas **sem** seletor de plano e **sem** botão
     "ATUALIZAR APLICATIVO" / "Baixar APK" (a versão web tem os dois).
- **Referência visual original:** `https://beamish-cupcake-5fbf43.netlify.app/`
  (citada no README e no CSS do fonte).

## 4. Achados e divergências

1. **Link do APK desatualizado no fonte.** O `js/config.js` original apontava
   para `SMARTEDTV-atual.apk` (`adn9elzkjzxof741bbui2`, `rlkey=yp1ijxk6fdtcqm93gzi24ig5j`),
   diferente do arquivo atual `SMARTEDTV.apk` (`ixfw289m0sibcyfyrxf9g`,
   `rlkey=z59708sngkysw0c1ntmmur6lv`). **Corrigido** nesta montagem, junto com
   a regeneração do QR code do APK (web + addon Kodi) e do preview standalone.
2. **QR codes do addon Kodi eram desenhos, não QR codes reais** (o próprio
   `README.txt` do addon admite). **Substituídos** por QR codes reais
   (checkout e link do APK), nos mesmos tamanhos (444×444).
3. **Serviços não conectados (honesto por design):** validação de código VIP e
   anúncios respondem `{connected:false}` — a UI mostra "ainda não conectado"
   em vez de simular. Os endpoints reais (validação, pagamento, ads, update)
   **não constam** em nenhum arquivo do Dropbox; o guia de integração está em
   `smartedtv/docs/HANDOFF.md` (seção "Findings" ainda vazia).
4. **Addon Kodi não conecta nada:** `default.py` fecha a janela na confirmação
   de anúncios e ignora checkout/share/ativação (comentários no código).
5. **Skin:** `addon.xml` declara nome "Nova TV" com id `skin.estilo.personalizado`;
   changelog herdado do Estuary (só "Updated language files from Transifex").
   Nada de suspeito: é uma skin Estuary renomeada/retocada.

## 5. O que foi alterado nesta montagem

- Repositório estruturado: `smartedtv/`, `kodi-addon/`, `skin/`, `preview/`,
  `tools/build-standalone.py`, `docs/INSPECTION.md`, README raiz.
- `smartedtv/js/config.js`: URLs do APK atualizadas (share `dl=0` / download `dl=1`).
- QR codes regenerados: `smartedtv/assets/qr-apk.png` (588×588) e
  `kodi-addon/.../media/qr_1.png` + `qr_2.png` (444×444).
- `smartedtv/standalone/smartedtv-preview.html` regenerado por
  `tools/build-standalone.py` (CSS/JS/assets inline, offline).
- `smartedtv/README.md`: caminhos `/app/...` corrigidos para o repositório.

## 6. Próximos passos sugeridos (aguardando definição)

- Conectar `codeAccess.activate()` ao serviço real de validação de códigos
  (precisa do endpoint/formato — ver HANDOFF §2).
- Conectar `ads.startSession()` ao provedor de anúncios real.
- Alinhar o addon Kodi com a web (seletor de plano, botões de APK/update,
  QR codes já corrigidos).
- Inspecionar o binário do APK quando houver como baixá-lo (ver §2).
