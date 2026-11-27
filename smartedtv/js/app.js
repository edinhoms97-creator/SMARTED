/* SMARTEDTV — interface wiring.
   UI concerns only: D-PAD navigation, dialogs, validation feedback,
   toasts, plan selection, parallax. All business outcomes come from
   window.SmartedtvServices (js/services.js). */
(function () {
  "use strict";
  var CONFIG = window.SMARTEDTV_CONFIG;
  var Services = window.SmartedtvServices;
  function $(id) { return document.getElementById(id); }

  var els = {
    screen: document.querySelector(".screen"),
    overlayAds: $("overlay"),
    overlayStatus: $("overlay-status"),
    statusTitle: $("status-title"),
    statusText: $("status-text"),
    statusOk: $("status-ok"),
    codigo: $("codigo"),
    codigoError: $("codigo-error"),
    ativar: $("ativar"),
    checkout: $("checkout"),
    share: $("share"),
    baixar: $("baixar-apk"),
    atualizar: $("atualizar"),
    gratis: $("gratis"),
    voltar: $("voltar"),
    seguir: $("seguir"),
    toasts: $("toast-region")
  };

  /* ---------- toasts (aria-live region) ---------- */
  function toast(message) {
    var t = document.createElement("div");
    t.className = "toast";
    t.setAttribute("role", "status");
    t.textContent = message;
    els.toasts.appendChild(t);
    while (els.toasts.children.length > 2) els.toasts.removeChild(els.toasts.firstChild);
    setTimeout(function () {
      t.classList.add("out");
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 320);
    }, 3600);
  }

  /* ---------- accessible overlay control ---------- */
  var lastFocus = null;
  function openOverlay(ov) {
    lastFocus = document.activeElement;
    ov.classList.add("on");
    var target = ov.querySelector(".dialog .btn");
    if (target) target.focus();
    document.addEventListener("keydown", onOverlayKeydown, true);
  }
  function closeOverlay(ov) {
    ov.classList.remove("on");
    document.removeEventListener("keydown", onOverlayKeydown, true);
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
  }
  function onOverlayKeydown(e) {
    var ov = document.querySelector(".overlay.on");
    if (!ov) return;
    if (e.key === "Escape") { e.preventDefault(); closeOverlay(ov); return; }
    if (e.key === "Tab") {
      var focusables = Array.prototype.filter.call(
        ov.querySelectorAll("button, input"),
        function (x) { return x.offsetParent && !x.disabled; }
      );
      if (!focusables.length) return;
      var first = focusables[0], last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }
  function showStatus(title, text, okLabel) {
    els.statusTitle.textContent = title;
    els.statusText.textContent = text;
    els.statusOk.textContent = okLabel || "Entendi";
    openOverlay(els.overlayStatus);
  }
  els.statusOk.addEventListener("click", function () { closeOverlay(els.overlayStatus); });
  els.overlayAds.addEventListener("click", function (e) { if (e.target === els.overlayAds) closeOverlay(els.overlayAds); });
  els.overlayStatus.addEventListener("click", function (e) { if (e.target === els.overlayStatus) closeOverlay(els.overlayStatus); });

  /* ---------- plan selection (visual only; sent to the service) ---------- */
  var planButtons = Array.prototype.slice.call(document.querySelectorAll(".plan button"));
  planButtons.forEach(function (b) {
    b.addEventListener("click", function () {
      planButtons.forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
    });
  });
  function selectedPlan() {
    var active = planButtons.filter(function (x) { return x.getAttribute("aria-pressed") === "true"; })[0];
    return active ? active.dataset.plan : CONFIG.defaultPlan;
  }

  /* ---------- device segment (visual toggle, as in the reference) ---------- */
  var segButtons = Array.prototype.slice.call(document.querySelectorAll(".seg button"));
  segButtons.forEach(function (b) {
    b.addEventListener("click", function () {
      segButtons.forEach(function (x) { x.setAttribute("aria-selected", String(x === b)); });
    });
  });

  /* ---------- code activation (no local code-format rules) ---------- */
  function activate() {
    var code = els.codigo.value.trim();
    els.codigoError.hidden = true;
    els.codigo.setAttribute("aria-invalid", "false");
    if (!code) {
      els.codigoError.hidden = false;
      els.codigo.setAttribute("aria-invalid", "true");
      els.codigo.focus();
      return;
    }
    var original = els.ativar.textContent;
    els.ativar.disabled = true;
    els.ativar.textContent = "Verificando…";
    Promise.resolve(Services.get("codeAccess").activate({ code: code, plan: selectedPlan() }))
      .then(function (res) {
        if (res && res.connected) {
          if (res.granted) {
            var when = res.expiresLabel || res.expiresAt || "";
            showStatus("VIP ativado",
              when ? "Acesso liberado até " + when + "." : "Acesso VIP liberado pelo serviço de ativação.",
              "Começar a assistir");
          } else {
            showStatus("Código não ativado",
              res.message || "O serviço de validação não aceitou este código para o plano selecionado.",
              "Tentar novamente");
          }
        } else {
          showStatus("Validação ainda não conectada",
            "Esta interface está pronta para acionar o serviço de validação de códigos do SMARTEDTV. Nenhuma validação real foi executada e nenhuma ativação foi simulada. Ponto de integração: js/services.js (codeAccess.activate) e guia docs/HANDOFF.md.",
            "Entendi");
        }
      })
      .catch(function () {
        showStatus("Não foi possível verificar",
          "O serviço de ativação respondeu com erro. Tente novamente em instantes.",
          "Fechar");
      })
      .then(function () {
        els.ativar.disabled = false;
        els.ativar.textContent = original;
      });
  }
  els.ativar.addEventListener("click", activate);
  els.codigo.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); activate(); }
  });

  /* ---------- checkout ---------- */
  els.checkout.addEventListener("click", function () {
    Services.get("payment").openCheckout();
    toast("Checkout aberto em uma nova aba.");
  });

  /* ---------- share / download APK ---------- */
  els.share.addEventListener("click", function () {
    Promise.resolve(Services.get("share").shareLink(CONFIG.apkShareUrl)).then(function (res) {
      if (res.method === "clipboard") toast("Link copiado para a área de transferência.");
      else if (res.method === "failed") showStatus("Não foi possível compartilhar",
        "Copie manualmente o link do app exibido no QR code.", "Fechar");
    });
  });
  els.baixar.addEventListener("click", function () {
    window.open(CONFIG.apkDownloadUrl, "_blank", "noopener");
    toast("Download do APK aberto em uma nova aba.");
  });

  /* ---------- ATUALIZAR APLICATIVO ---------- */
  els.atualizar.addEventListener("click", function () {
    Promise.resolve(Services.get("appUpdate").checkAndInstall()).then(function (res) {
      if (res && res.connected) { if (res.message) toast(res.message); return; }
      if (res && res.openedDownload) toast("Abrindo o download do aplicativo atualizado…");
    });
  });

  /* ---------- ads (reference dialog copy preserved) ---------- */
  els.gratis.addEventListener("click", function () { openOverlay(els.overlayAds); });
  els.voltar.addEventListener("click", function () { closeOverlay(els.overlayAds); });
  els.seguir.addEventListener("click", function () {
    closeOverlay(els.overlayAds);
    Promise.resolve(Services.get("ads").startSession())
      .then(function (res) {
        if (res && res.connected) toast(res.message || "Sessão com anúncios iniciada.");
        else showStatus("Anúncios ainda não conectados",
          "A exibição de anúncios será iniciada pelo serviço de anúncios existente do SMARTEDTV quando ele for conectado a esta interface. Nenhum anúncio foi simulado. Ponto de integração: js/services.js (ads.startSession) e guia docs/HANDOFF.md.",
          "Entendi");
      })
      .catch(function () {
        showStatus("Não foi possível iniciar",
          "O serviço de anúncios respondeu com erro. Tente novamente em instantes.",
          "Fechar");
      });
  });

  /* ---------- D-PAD: arrows cycle focus, Esc closes (reference behavior) ---------- */
  document.addEventListener("keydown", function (e) {
    if (["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].indexOf(e.key) === -1) return;
    e.preventDefault();
    var open = document.querySelector(".overlay.on");
    var scope = open || document;
    var list = Array.prototype.filter.call(
      scope.querySelectorAll("button, input"),
      function (x) { return x.offsetParent && !x.disabled; }
    );
    if (!list.length) return;
    var i = list.indexOf(document.activeElement);
    if (i < 0) i = 0;
    var dir = (e.key === "ArrowRight" || e.key === "ArrowDown") ? 1 : -1;
    list[(i + dir + list.length) % list.length].focus();
  });

  /* ---------- ambient parallax (fine pointers only) ---------- */
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduced && window.matchMedia("(pointer: fine)").matches) {
    var raf = 0;
    window.addEventListener("mousemove", function (e) {
      if (raf) return;
      raf = requestAnimationFrame(function () {
        raf = 0;
        var x = (e.clientX / window.innerWidth) * 2 - 1;
        var y = (e.clientY / window.innerHeight) * 2 - 1;
        els.screen.style.setProperty("--px", x.toFixed(3));
        els.screen.style.setProperty("--py", y.toFixed(3));
      });
    });
  }
})();
