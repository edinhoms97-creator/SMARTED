/* SMARTEDTV — central configuration.
   Every external URL used by the interface lives here. Nothing else
   in the codebase hardcodes a link, so hosts/links can be swapped in
   one place. No endpoint, credential or code format is invented: the
   only URLs below are the ones provided for this build. */
window.SMARTEDTV_CONFIG = {
  appName: "SMARTEDTV",

  /* Payment — official checkout link provided for this build (Cakto). */
  checkoutUrl: "https://pay.cakto.com.br/nkvbegd_1323120",

  /* Android APK — EXACT share link provided for this build (Dropbox, dl=1).
     Updated 2026-11-27: SMARTEDTV.apk (263 MB, /SMARTEDTV UNIVERSAL/).
     Previous file was SMARTEDTV-atual.apk (adn9elzkjzxof741bbui2). */
  apkShareUrl: "https://www.dropbox.com/scl/fi/ixfw289m0sibcyfyrxf9g/SMARTEDTV.apk?rlkey=z59708sngkysw0c1ntmmur6lv&st=okcfec6i&dl=1",

  /* Same Dropbox link in its direct-download form (Dropbox's documented
     dl=1 parameter) so the "Baixar APK" button starts the download.
     The QR code encodes apkShareUrl exactly as provided. */
  apkDownloadUrl: "https://www.dropbox.com/scl/fi/ixfw289m0sibcyfyrxf9g/SMARTEDTV.apk?rlkey=z59708sngkysw0c1ntmmur6lv&st=okcfec6i&dl=1",

  /* Access plans offered at activation. Labels only — duration semantics
     (10 minutes / 1 month) must be confirmed against the existing
     validation service. See docs/HANDOFF.md. */
  plans: [
    { id: "10min", label: "10 min" },
    { id: "1month", label: "1 mês" }
  ],
  defaultPlan: "10min",

  /* Advertising — VAST (Clickadilla, Spot #1508180). PRIORITY path.
     The player fetches this tag, plays the creative as a pre-roll and
     fires impression/start/quartile/complete/error tracking. No-fill,
     network failure and timeout all fall back cleanly to the content
     (see js/vast.js). */
  vastTagUrl: "https://vast.yomeno.xyz/vast?spot_id=1508180",
  adTimeoutMs: 8000,

  /* Advertising — AdMob (mobile). ISOLATED and DISABLED by flag.
     Validation focus is 100% on the VAST path above; AdMob is only
     activated in a later step, after VAST approval. See docs/ADMOB.md
     and js/admob.js. IDs below are the real production IDs. */
  admob: {
    enabled: false,
    appId: "ca-app-pub-2066014755407744~5076693043",
    appOpenAdUnitId: "ca-app-pub-2066014755407744/4214378379",
    interstitialAdUnitId: "ca-app-pub-2066014755407744/3572039686"
  }
};
