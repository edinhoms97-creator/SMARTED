# SMARTEDTV — Integration Handoff Guide

**Audience:** the agent/engineer who will connect this interface to the EXISTING SMARTEDTV app
(its current payment flow, code-validation flow, advertising and app-update services).

**Prime directive:** do not fabricate anything. No invented endpoints, credentials, code formats,
payment status, or ad-provider details. Every contract below is a proposal to be CONFIRMED by
inspecting the existing app. The UI renders only what a registered service returns.

---

## 1. What is already real in this interface

| Element | Where | Already real? |
|---|---|---|
| Cakto checkout | "Abrir checkout" + checkout QR | Yes — opens `https://pay.cakto.com.br/nkvbegd_1323120` (provided) |
| APK share | Share QR + "Compartilhar link" | Yes — encodes/shares the EXACT provided Dropbox link |
| APK download / update | "Baixar APK", "ATUALIZAR APLICATIVO" | Partially — opens the provided Dropbox APK (direct-download form `dl=1`) |
| Code activation (10 min / 1 month) | Bottom bar "Ativar" | NO — calls the `codeAccess` service hook; default answers `{connected:false}` |
| Ads | "Continuar com anúncios" → confirm | NO — calls the `ads` service hook; default answers `{connected:false}` |

The QR images were generated from the provided URLs at build time
(`assets/qr-checkout.png`, `assets/qr-apk.png`). Regenerate them if the links change.

## 2. Step 1 — Inspect the existing app

Locate and record (in this file, under "Findings"):

1. **Code-validation flow**
   - Endpoint(s) or SDK calls the existing app uses to validate a VIP/access code.
   - Request payload shape (parameter names) and response shape (success, expiry, plan).
   - The REAL duration semantics of plans: what "10 minutes" and "1 month" map to server-side
     (the UI currently sends `plan: "10min" | "1month"` — rename in `js/config.js` if needed).
   - Any code FORMAT rules (length, charset, masking). The UI deliberately has none yet.
2. **Payment flow**
   - Confirm the Cakto product/plan the checkout link belongs to; webhook or return URL that
     marks a payment as paid; whether the existing app polls a status endpoint afterwards.
3. **Advertising**
   - Which ad provider/SDK the existing app uses, how an ad session starts, and what happens
     after the ad (entry into the player, cooldowns, frequency caps).
4. **App update**
   - Existing version-check endpoint or channel, current APK version, and the in-app update flow.
5. **Device/session context**
   - How the existing app identifies the device (the interface has an "Android TV / Celular"
     segment that is currently visual-only) and whether activation binds to a device id.

## 3. Step 2 — Map each interface action to a service hook

All hooks live in `window.SmartedtvServices` (`js/services.js`). The UI never changes.

| UI action (id / data-testid) | Hook | Suggested contract [TO CONFIRM] |
|---|---|---|
| "Ativar" (`ativar` / `activate-code-button`) | `codeAccess.activate({code, plan})` | `{connected:true, granted:true, expiresAt?, expiresLabel?}` or `{connected:true, granted:false, message}` |
| "Continuar com anúncios" confirm (`seguir` / `ads-confirm-button`) | `ads.startSession()` | `{connected:true, started:true, message?}` |
| "Abrir checkout" (`checkout` / `open-checkout-button`) | `payment.openCheckout()` | default already correct; override only to add pre-checkout logic |
| "Compartilhar link" (`share` / `share-link-button`) | `share.shareLink(url)` | default uses Web Share API + clipboard fallback |
| "Baixar APK" (`baixar-apk` / `download-apk-button`) | direct link (config) | override `appUpdate` if the existing flow differs |
| "ATUALIZAR APLICATIVO" (`atualizar` / `update-app-button`) | `appUpdate.checkAndInstall()` | `{connected:true, handled:true, message?}` — return `{connected:false}` to keep the default download |
| Device segment (`device-*-button`) | none yet | wire after Findings §5 |

## 4. Step 3 — Register the existing implementations

In the existing app's bootstrap (before `js/app.js` runs, or any time before user interaction):

```js
// Example — replace bodies with calls to the EXISTING services.
window.SmartedtvServices.register("codeAccess", {
  async activate({ code, plan }) {
    const res = await existingApi.validateCode(code, plan); // ← existing logic
    return { connected: true, granted: res.valid, expiresLabel: res.expiresAtHuman, message: res.error };
  }
});

window.SmartedtvServices.register("ads", {
  async startSession() {
    await existingAds.start();                               // ← existing logic
    return { connected: true, started: true };
  }
});

window.SmartedtvServices.register("appUpdate", {
  async checkAndInstall() {
    await existingUpdate.checkAndInstall();                  // ← existing logic
    return { connected: true, handled: true };
  }
});

window.SmartedtvServices.register("payment", {
  openCheckout() {
    existingPayment.startCheckout();                         // ← existing logic (or keep the Cakto link)
    return { opened: true };
  }
});
```

Rules:
- Keep ALL business logic inside the existing services; the hook is a thin adapter.
- Never resolve `granted:true` / `started:true` without real confirmation.
- On failure, throw — the UI shows an error dialog and keeps the form intact.

## 5. Step 4 — Verify after wiring

- [ ] Activation with a REAL 10-minute code → VIP granted, expiry shown from the service response
- [ ] Activation with a REAL 1-month code → VIP granted
- [ ] Invalid/expired code → "Código não ativado" with the service's own message
- [ ] Checkout opens the correct Cakto product; paid status reflected by the EXISTING flow (not this UI)
- [ ] Share sheet / clipboard carries the exact APK link; QR scans to the same URL
- [ ] "Baixar APK" and "ATUALIZAR APLICATIVO" trigger the existing update flow
- [ ] "Continuar com anúncios" starts a REAL ad session
- [ ] D-PAD: arrows cycle every control, Enter activates, Esc closes dialogs
- [ ] 1440px desktop, 390px mobile in portrait AND landscape (16:9 letterbox kept at both), `prefers-reduced-motion`

## 6. Findings (fill during inspection)

- Code-validation endpoint/payload/response: _
- Plan semantics (10min / 1month): _
- Code format rules: _
- Payment product + paid-status flow: _
- Ad provider + session lifecycle: _
- Update channel + current version: _
- Device identity: _
