/* ============================================================
   SMARTEDTV — AdMob (mobile) — ISOLATED, DISABLED BY FLAG.

   This module is intentionally SEPARATE from the VAST path
   (js/vast.js). Validation focus is 100% on VAST Clickadilla
   (Spot #1508180); AdMob is only prepared here and activated
   in a later step, after VAST approval.

   Real production IDs (from config.js):
     App ID ......... ca-app-pub-2066014755407744~5076693043
     App Open ....... ca-app-pub-2066014755407744/4214378379
     Interstitial ... ca-app-pub-2066014755407744/3572039686
       (also used for Rewarded / In-Stream placements)

   IMPORTANT: the AdMob SDK is native Android. It cannot run
   inside a plain WebView — it needs a native bridge
   (window.SmartedtvAdMobBridge, e.g. a Capacitor/Cordova
   plugin or a custom @JavascriptInterface). Until that bridge
   exists AND config.admob.enabled is true, every call here
   resolves { connected:false } and nothing is shown.
   Native setup (AndroidManifest, Gradle, bridge) is
   documented in docs/ADMOB.md.
   ============================================================ */
(function () {
  "use strict";

  var CONFIG = (window.SMARTEDTV_CONFIG && window.SMARTEDTV_CONFIG.admob) || {};
  var enabled = CONFIG.enabled === true;

  function bridge() {
    return window.SmartedtvAdMobBridge || null;
  }

  function disabled(reason) {
    return Promise.resolve({ connected: false, reason: reason || "disabled" });
  }

  function callBridge(method, adUnitId) {
    if (!enabled) return disabled("disabled-by-flag");
    var b = bridge();
    if (!b || typeof b[method] !== "function") return disabled("no-native-bridge");
    try {
      var res = b[method](adUnitId);
      return Promise.resolve(res).then(function (r) {
        return { connected: true, shown: !!(r && r.shown) };
      }, function (err) {
        return { connected: true, shown: false, error: String(err) };
      });
    } catch (e) {
      return Promise.resolve({ connected: true, shown: false, error: String(e) });
    }
  }

  window.SmartedtvAdMob = {
    enabled: enabled,
    config: CONFIG,
    /* True only when the flag is on AND the native bridge exists. */
    isAvailable: function () {
      return enabled && !!bridge();
    },
    showAppOpen: function () {
      return callBridge("showAppOpen", CONFIG.appOpenAdUnitId);
    },
    showInterstitial: function () {
      return callBridge("showInterstitial", CONFIG.interstitialAdUnitId);
    },
    showRewarded: function () {
      return callBridge("showRewarded", CONFIG.interstitialAdUnitId);
    }
  };
})();
