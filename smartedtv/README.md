# SMARTEDTV — Welcome & Login Interface

Responsive HTML + CSS + JavaScript welcome/login screen for SMARTEDTV, ported 1:1 from the visual
reference `https://beamish-cupcake-5fbf43.netlify.app/` (layout, components, colors, typography,
spacing, copy and D-PAD interactions), plus only the additions requested:

- **ATUALIZAR APLICATIVO** button in the left (welcome) column
- **Pay** via the official Cakto checkout (button + real QR code)
- **Share and download the Android APK** (share QR + "Compartilhar link" + "Baixar APK")
- **Activate access by code** for **10 minutes or 1 month** (bottom bar: plan selector + code field)
- **Watch with advertisements** ("Continuar com anúncios" + confirmation dialog, as in the reference)

## Deliverables

| Path | What it is |
|---|---|
| `smartedtv/` (this folder) | Complete source project |
| `smartedtv/standalone/smartedtv-preview.html` | Final standalone preview — single HTML file, CSS/JS/QR images inlined, works offline (rebuild with `python3 tools/build-standalone.py`) |
| `smartedtv-src.zip` (Dropbox original) | Zipped copy of the source project as received on 2026-11-27 |
| App preview | The same interface is served at the app's root (copied into `frontend/public/`) |

## Structure

```
smarterdtv/
├── index.html              Interface markup (PT-BR, accessible, test ids on every control)
├── css/styles.css          Reference design tokens + components + documented additions
├── js/config.js            ALL external URLs and plan labels (single source of truth)
├── js/services.js          Integration layer — payment, codeAccess, ads, appUpdate, share
├── js/app.js               UI wiring: D-PAD, dialogs, validation, toasts, parallax
├── assets/qr-checkout.png  Real QR encoding the Cakto checkout URL
├── assets/qr-apk.png       Real QR encoding the exact Dropbox share link
├── assets/favicon.svg      Original SMARTEDTV mark (also used as the logo glyph)
├── docs/HANDOFF.md         Agent guide: inspect the existing app and connect its services
└── standalone/smartedtv-preview.html
```

## Run

Any static server works. In this workspace the interface is already served at the app root
(files mirrored into `frontend/public/`). Opening `index.html` directly in a browser also works.

## Honest states (nothing is fabricated)

| Action | Default behavior before the existing service is connected |
|---|---|
| Abrir checkout | Opens the real Cakto checkout in a new tab (provided URL) |
| QR codes | Real QR images encoding the provided Cakto / Dropbox URLs |
| Compartilhar link | Web Share API → clipboard fallback with the exact provided link |
| Baixar APK / ATUALIZAR APLICATIVO | Opens the provided Dropbox APK (direct-download form) |
| Ativar (código) | Calls `codeAccess.activate()` → shows an explicit "validation not connected" dialog. No fake success, no invented code format (only the "not empty" rule) |
| Continuar com anúncios → confirmar | VAST Clickadilla (Spot #1508180) via `js/vast.js`: pre-roll + tracking events; no-fill/failure/timeout fall back cleanly. Demo: `demo-vast.html`. AdMob is separate and flag-disabled (`js/admob.js`) |
| Payment status / ad details | Never displayed, because none were provided |

## Design fidelity notes (deliberate, documented)

- Colors, typography (Arial/Helvetica stack), radii, glass cards, buttons and copy are the reference's own values.
- Added motion: power-on reveal, masked line-by-line headline reveal, staggered card/panel entrances,
  slow editorial marquee of the reference legend, subtle pointer parallax on the ambient glows,
  button hover lift. All disabled under `prefers-reduced-motion`.
- Enter on a focused button uses the browser's native activation (the reference double-fired clicks).
- The screen stays EXACTLY horizontal at every viewport — the 16:9 letterbox stage is kept on phones
  too (portrait shows the whole TV screen as a miniature, landscape fills the width), matching the
  reference with no page scrolling. One sizing correction to the reference's ≤900px stage rule keeps
  the 16:9 ratio exact on landscape phones.

## Connecting the existing services

See `docs/HANDOFF.md`. Short version:

```js
window.SmartedtvServices.register("codeAccess", {
  async activate({ code, plan }) {
    const res = await existingValidationApi(code, plan); // your existing logic
    return { connected: true, granted: res.ok, message: res.msg };
  }
});
```
