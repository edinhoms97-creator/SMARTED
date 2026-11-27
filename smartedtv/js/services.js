/* ============================================================
   SMARTEDTV — integration layer.

   Every interface action routes through EXACTLY ONE service below.
   This is the ONLY file the existing app's services need to touch —
   the UI never changes to connect a backend.

   Rules honoured by design:
   • Defaults are HONEST: services that must talk to the existing app
     answer { connected:false } until a real implementation is
     registered. The UI shows an explicit "not connected" state and
     never fakes success, payment status, codes or ad behaviour.
   • Actions that ARE an external link (Cakto checkout, APK download)
     use the URLs from js/config.js — real, provided destinations.
   • Contracts marked [TO CONFIRM] are proposals to be validated
     against the existing app during inspection (docs/HANDOFF.md).

   How the existing app plugs in (NO business logic is replaced):
     window.SmartedtvServices.register("codeAccess", {
       async activate({ code, plan }) {
         const res = await existingApi.validateCode(code, plan); // your call
         return { connected: true, granted: res.ok, message: res.msg };
       }
     });
   ============================================================ */
(function () {
  "use strict";
  var CONFIG = window.SMARTEDTV_CONFIG;

  var defaults = {

    /* PAYMENT ------------------------------------------------------
       Default: opens the official Cakto checkout in a new tab.       */
    payment: {
      openCheckout: function () {
        window.open(CONFIG.checkoutUrl, "_blank", "noopener");
        return { opened: true };
      }
    },

    /* CODE VALIDATION — VIP access (10 minutes or 1 month) ---------
       MUST be connected to the existing validation service.
       Suggested contract [TO CONFIRM against the existing app]:
         activate({ code, plan }) ->
           { connected:true, granted:true,  plan, expiresAt?, expiresLabel? }
           { connected:true, granted:false, message }
           { connected:false }                 // not wired yet
       Only resolve granted:true after REAL server confirmation.     */
    codeAccess: {
      activate: function () {
        return Promise.resolve({ connected: false });
      }
    },

    /* ADVERTISING — "Continuar com anúncios" -----------------------
       CONNECTED (2026-11-27): VAST Clickadilla Spot #1508180 via
       js/vast.js (pre-roll overlay + tracking events). No-fill,
       network failure and timeout resolve as a clean fallback —
       the caller resumes the main content, never a black screen.
       Contract:
         startSession({ resumeTarget }) ->
           { connected:true, started:bool, outcome:
             "completed"|"skipped"|"nofill"|"error", message? }
       AdMob (mobile) is a separate, flag-disabled module
       (js/admob.js) and is NOT part of this path. */
    ads: {
      startSession: function (opts) {
        opts = opts || {};
        if (!window.SmartedtvVast) {
          return Promise.resolve({ connected: false });
        }
        var player = new window.SmartedtvVast.VastPlayer({
          tagUrl: opts.tagUrl || CONFIG.vastTagUrl,
          timeoutMs: CONFIG.adTimeoutMs,
          resumeTarget: opts.resumeTarget || null,
          onEvent: opts.onEvent || null
        });
        return player.play().then(function (result) {
          var messages = {
            completed: "Anúncio concluído.",
            skipped: "Anúncio pulado.",
            nofill: "Nenhum anúncio disponível no momento — continuando sem anúncios.",
            error: "Não foi possível carregar o anúncio — continuando."
          };
          return {
            connected: true,
            started: result.outcome === "completed" || result.outcome === "skipped",
            outcome: result.outcome,
            reason: result.reason || null,
            resumeConfirmed: result.resumeConfirmed === true,
            resumeTarget: result.resumeTarget,
            resumedAt: result.resumedAt !== undefined ? result.resumedAt : null,
            message: messages[result.outcome] || "Sessão com anúncios iniciada."
          };
        });
      }
    },

    /* APP UPDATE — "ATUALIZAR APLICATIVO" --------------------------
       Default: opens the published APK download (the provided
       Dropbox file "SMARTEDTV.apk"). Register an
       implementation to plug the existing update service
       (version check / in-app update flow) instead.               */
    appUpdate: {
      checkAndInstall: function () {
        window.open(CONFIG.apkDownloadUrl, "_blank", "noopener");
        return Promise.resolve({ connected: false, openedDownload: true });
      }
    },

    /* SHARE — Web Share API with clipboard fallback.
       Used for "Compartilhar link" and the share QR payload.       */
    share: {
      shareLink: function (url) {
        if (navigator.share) {
          return navigator.share({ title: CONFIG.appName, url: url }).then(
            function () { return { method: "native" }; },
            function (err) {
              if (err && err.name === "AbortError") return { method: "cancelled" };
              return fallbackCopy(url);
            }
          );
        }
        return Promise.resolve(fallbackCopy(url));
      }
    }
  };

  function fallbackCopy(url) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(url)
        .then(function () { return { method: "clipboard" }; })
        .catch(function () { return { method: "failed" }; });
    }
    return Promise.resolve({ method: "failed" });
  }

  var impl = {};
  Object.keys(defaults).forEach(function (k) { impl[k] = defaults[k]; });

  window.SmartedtvServices = {
    /* Current implementation of a service (default until registered). */
    get: function (name) { return impl[name]; },

    /* Register/override a service with the existing app's logic.
       Methods you do not override keep the default behaviour.      */
    register: function (name, partial) {
      impl[name] = Object.assign({}, defaults[name], partial || {});
      return impl[name];
    },

    /* Restore factory defaults (useful in tests). */
    reset: function () {
      Object.keys(defaults).forEach(function (k) { impl[k] = defaults[k]; });
    },

    defaults: defaults
  };
})();
