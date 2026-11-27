/* ============================================================
   SMARTEDTV — VAST client (Clickadilla, Spot #1508180).

   Priority ad path. Fetches the VAST tag, parses the XML,
   plays the creative as a pre-roll overlay and fires the
   standard tracking events (impression, start, firstQuartile,
   midpoint, thirdQuartile, complete, error).

   Guarantees (per product spec):
   • No-fill is NOT an error: empty XML, a minimal <VAST> root
     without <Ad>, or a <VAST><Error> response resolves as
     { outcome:"nofill" } — no parse exception, no frozen player.
   • Network failure / timeout resolves as { outcome:"error" }
     and the caller falls back immediately to the main content
     (the overlay is removed; no black screen is left behind).
   • Exact VOD resume: pass resumeTarget { video } and the
     player saves video.currentTime before the pre-roll and
     restores it (seek confirmed via "seeked") after the ad.

   Transport note: in the browser, fetch() negotiates TLS 1.2+
   using platform security settings and the actual browser UA. JS
   cannot force a minimum TLS version or impersonate Chrome Android;
   configure those in the native shell for older devices. The Kodi
   (Python) twin of this client enforces them explicitly in
   kodi-addon/script.smartedtv.welcome/vast.py.

   Testable without a browser: parseVast / parseTimeOffset /
   chooseMediaFile are pure and covered by tools/test-vast.js.
   ============================================================ */
(function () {
  "use strict";

  var DEFAULT_TIMEOUT_MS = 8000;
  var STALL_TIMEOUT_MS = 3000;

  /* ---------- time helpers ---------- */

  /* "HH:MM:SS.mmm" | "MM:SS" | "SS" -> seconds (float) or null */
  function parseClock(str) {
    if (typeof str !== "string") return null;
    var s = str.trim();
    if (!s) return null;
    var parts = s.split(":");
    var sec = 0;
    try {
      if (parts.length === 3) {
        sec = parseInt(parts[0], 10) * 3600 + parseInt(parts[1], 10) * 60 + parseFloat(parts[2]);
      } else if (parts.length === 2) {
        sec = parseInt(parts[0], 10) * 60 + parseFloat(parts[1]);
      } else if (parts.length === 1) {
        sec = parseFloat(parts[0]);
      } else {
        return null;
      }
    } catch (e) {
      return null;
    }
    return isNaN(sec) ? null : sec;
  }

  /* VAST time offset: "00:00:05" -> {type:"time",seconds:5}
     "25%" -> {type:"percent",value:25}; null when unparsable. */
  function parseTimeOffset(str) {
    if (typeof str !== "string") return null;
    var s = str.trim();
    if (!s) return null;
    if (s.charAt(s.length - 1) === "%") {
      var v = parseFloat(s.slice(0, -1));
      return isNaN(v) ? null : { type: "percent", value: v };
    }
    var sec = parseClock(s);
    return sec === null ? null : { type: "time", seconds: sec };
  }

  function offsetToSeconds(offset, duration) {
    if (!offset) return null;
    if (offset.type === "time") return offset.seconds;
    if (offset.type === "percent" && duration) return (offset.value / 100) * duration;
    return null;
  }

  /* ---------- beacon (tracking) ---------- */

  /* Pixels deliberately use the browser's REAL User-Agent. User-Agent is a
     browser-controlled header: do not spoof a model or try to set it in JS. */
  function expandMacros(url, macros) {
    macros = macros || {};
    var nonce = String(Math.floor(10000000 + Math.random() * 90000000));
    var values = { CACHEBUSTING: nonce, CACHEBUSTER: nonce, RANDOM: nonce,
      TIMESTAMP: encodeURIComponent(new Date().toISOString()) };
    if (macros.errorCode !== undefined) values.ERRORCODE = String(macros.errorCode);
    if (typeof navigator !== "undefined" && navigator.userAgent)
      values.DEVICEUA = encodeURIComponent(navigator.userAgent);
    var result = String(url || "");
    Object.keys(values).forEach(function (name) {
      ["\\[" + name + "\\]", "%5b" + name + "%5d", "%%" + name + "%%"].forEach(function (pattern) {
        result = result.replace(new RegExp(pattern, "gi"), function () { return values[name]; });
      });
    });
    return result;
  }

  var pendingPixels = [];
  function beacon(url, macros) {
    if (!url) return;
    try {
      var img = new Image();
      // Retain the image until load/error (or bounded cleanup), so a WebView
      // cannot collect it while its asynchronous GET is still in flight.
      pendingPixels.push(img);
      var timer;
      var release = function () {
        clearTimeout(timer);
        var index = pendingPixels.indexOf(img);
        if (index >= 0) pendingPixels.splice(index, 1);
        img.onload = img.onerror = null;
      };
      img.onload = img.onerror = release;
      timer = setTimeout(release, 10000);
      img.src = expandMacros(url, macros);
    } catch (e) { /* a blocked pixel must never break playback */ }
  }

  function fireAll(urls, macros, onEvent, eventName) {
    (urls || []).forEach(function (u) {
      beacon(u, macros);
      if (onEvent) { try { onEvent(eventName, u); } catch (e) {} }
    });
  }

  /* ---------- VAST parsing ---------- */

  /* getElementsByTagName-based helpers (work in browsers AND in
     older Android TV WebViews without querySelector on XML docs). */
  function findAll(root, tag) {
    if (!root.getElementsByTagName) return [];
    var exact = root.getElementsByTagName(tag);
    if (exact.length) return exact;
    return Array.prototype.filter.call(root.getElementsByTagName("*"), function (node) {
      return (node.localName || node.nodeName.split(":").pop()) === tag;
    });
  }
  function findFirst(root, tag) {
    var els = findAll(root, tag);
    return els.length ? els[0] : null;
  }
  function textOf(root, tag) {
    var el = findFirst(root, tag);
    return el && el.textContent ? el.textContent.trim() : "";
  }
  function allText(root, tag) {
    var out = [];
    var els = findAll(root, tag);
    for (var i = 0; i < els.length; i++) {
      var t = els[i].textContent ? els[i].textContent.trim() : "";
      if (t) out.push(t);
    }
    return out;
  }

  /* Pick the best playable media file: prefer progressive MP4,
     highest width first; fall back to the first media file. */
  function chooseMediaFile(files) {
    if (!files || !files.length) return null;
    var mp4 = files.filter(function (f) {
      return /mp4/i.test(f.type || "") || /\.mp4($|\?)/i.test(f.url || "");
    });
    var pool = mp4.length ? mp4 : files;
    return pool.slice().sort(function (a, b) {
      return (b.width || 0) - (a.width || 0);
    })[0];
  }

  /* Parse VAST XML text.
     Returns { ads:[...], noFill:bool, reason, errorCode }.
     NEVER throws on no-fill / empty / malformed input — those
     resolve as noFill so the caller can fall back cleanly. */
  function parseVast(xmlText) {
    var empty = { ads: [], noFill: true, reason: "empty", errorCode: null };
    if (typeof xmlText !== "string" || !xmlText.trim()) return empty;

    var doc;
    try {
      doc = new DOMParser().parseFromString(xmlText, "text/xml");
    } catch (e) {
      return { ads: [], noFill: true, reason: "malformed", errorCode: null };
    }
    if (!doc || findFirst(doc, "parsererror")) {
      return { ads: [], noFill: true, reason: "malformed", errorCode: null };
    }

    var adEls = findAll(doc, "Ad");
    var errEl = findFirst(doc, "Error");
    if (!adEls.length && errEl) {
      return {
        ads: [], noFill: true, reason: "vast-error",
        errorCode: errEl.getAttribute("code") || errEl.textContent.trim() || null
      };
    }

    if (!adEls.length) return { ads: [], noFill: true, reason: "no-ad", errorCode: null };

    var ads = [];
    for (var i = 0; i < adEls.length; i++) {
      var adEl = adEls[i];
      var tracking = {};
      var trackEls = findAll(adEl, "Tracking");
      for (var j = 0; j < trackEls.length; j++) {
        var ev = trackEls[j].getAttribute("event");
        var url = trackEls[j].textContent ? trackEls[j].textContent.trim() : "";
        if (ev && url) {
          (tracking[ev] = tracking[ev] || []).push(url);
        }
      }
      tracking.error = (tracking.error || []).concat(allText(adEl, "Error"));
      var mediaFiles = [];
      var mfEls = findAll(adEl, "MediaFile");
      for (var k = 0; k < mfEls.length; k++) {
        mediaFiles.push({
          url: mfEls[k].textContent ? mfEls[k].textContent.trim() : "",
          type: mfEls[k].getAttribute("type") || "",
          delivery: mfEls[k].getAttribute("delivery") || "",
          width: parseInt(mfEls[k].getAttribute("width") || "0", 10) || 0,
          height: parseInt(mfEls[k].getAttribute("height") || "0", 10) || 0,
          bitrate: parseInt(mfEls[k].getAttribute("bitrate") || "0", 10) || 0
        });
      }
      var linear = findFirst(adEl, "Linear");
      ads.push({
        id: adEl.getAttribute("id") || "",
        wrapperUrl: textOf(adEl, "VASTAdTagURI") || textOf(adEl, "VASTAdTagURL"),
        sequence: parseInt(adEl.getAttribute("sequence") || "1", 10) || 1,
        adSystem: textOf(adEl, "AdSystem"),
        adTitle: textOf(adEl, "AdTitle"),
        universalAdId: textOf(adEl, "UniversalAdId"),
        duration: parseClock(textOf(adEl, "Duration")),
        skipOffset: linear ? parseTimeOffset(linear.getAttribute("skipoffset")) : null,
        mediaFiles: mediaFiles,
        mediaFile: chooseMediaFile(mediaFiles),
        clickThrough: textOf(adEl, "ClickThrough"),
        clickTracking: allText(adEl, "ClickTracking"),
        impressions: allText(adEl, "Impression"),
        tracking: tracking
      });
    }
    return { ads: ads, noFill: false, reason: null, errorCode: null };
  }

  /* ---------- fetch with timeout ---------- */

  function fetchVast(tagUrl, timeoutMs) {
    var ms = timeoutMs || DEFAULT_TIMEOUT_MS;
    var controller = (typeof AbortController !== "undefined") ? new AbortController() : null;
    // Race covers slow response bodies AND WebViews without AbortController.
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () {
        if (controller) controller.abort();
        reject(new Error("vast-timeout"));
      }, ms);
      var opts = { method: "GET", credentials: "omit", redirect: "follow",
        headers: { Accept: "application/xml,text/xml,*/*;q=0.8" } };
      if (controller) opts.signal = controller.signal;
      Promise.resolve().then(function () { return fetch(tagUrl, opts); })
        .then(function (res) {
          if (!res.ok) throw new Error("vast-http-" + res.status);
          return res.text();
        }).then(function (text) {
          clearTimeout(timer); resolve(text);
        }, function (err) {
          clearTimeout(timer); reject(err);
        });
    });
  }

  function fetchResolvedVast(tagUrl, timeoutMs, onEvent) {
    var deadline = Date.now() + (timeoutMs || DEFAULT_TIMEOUT_MS);
    var visited = [], impressions = [], tracking = {};
    function fail(code) { fireAll(tracking.error || [], { errorCode: code }, onEvent, "error"); }
    function load(url, depth) {
      if (depth > 5 || visited.indexOf(url) >= 0) {
        fail(302);
        return Promise.resolve({ ads: [], noFill: true, reason: "wrapper-limit-or-cycle" });
      }
      visited.push(url);
      var remaining = deadline - Date.now();
      if (remaining <= 0) { fail(301); return Promise.reject(new Error("vast-timeout")); }
      return fetchVast(expandMacros(url), remaining).then(function (xml) {
        var parsed = parseVast(xml);
        if (!parsed.ads.length) { fail(303); return parsed; }
        var ad = parsed.ads[0];
        if (ad.wrapperUrl && !ad.mediaFile) {
          impressions = impressions.concat(ad.impressions);
          Object.keys(ad.tracking).forEach(function (event) {
            tracking[event] = (tracking[event] || []).concat(ad.tracking[event]);
          });
          return load(ad.wrapperUrl, depth + 1);
        }
        ad.impressions = impressions.concat(ad.impressions);
        Object.keys(tracking).forEach(function (event) {
          ad.tracking[event] = tracking[event].concat(ad.tracking[event] || []);
        });
        return parsed;
      }, function (err) { fail(301); throw err; });
    }
    return load(tagUrl, 0);
  }

  /* ---------- pre-roll player ---------- */

  function VastPlayer(opts) {
    opts = opts || {};
    this.tagUrl = opts.tagUrl;
    this.timeoutMs = opts.timeoutMs || DEFAULT_TIMEOUT_MS;
    this.container = opts.container || document.body;
    this.onEvent = opts.onEvent || null;       /* (eventName, url) — logging hook */
    this.onFinish = opts.onFinish || null;     /* (result) — resume hook */
    this.resumeTarget = opts.resumeTarget || null; /* { video } — exact VOD resume */
    this._done = false;
    this._overlay = null;
    this._video = null;
    this._stallTimer = null;
  }

  VastPlayer.prototype.play = function () {
    var self = this;
    if (this._playPromise) return this._playPromise;
    this._playPromise = new Promise(function (resolve) { self._resolve = resolve; });
    if (self.resumeTarget && self.resumeTarget.video) {
      var v = self.resumeTarget.video;
      self._savedTime = v.currentTime;
      self._wasPlaying = !v.paused;
      try { v.pause(); } catch (e) {}
    }
    if (!this.tagUrl) {
      self._finish({ outcome: "error", reason: "no-tag-url" });
      return this._playPromise;
    }
    fetchResolvedVast(this.tagUrl, this.timeoutMs, this.onEvent).then(function (parsed) {
      if (!parsed.ads.length) {
        /* No-fill: clean fallback, no overlay ever shown. */
        return self._finish({
          outcome: "nofill", reason: parsed.reason, errorCode: parsed.errorCode
        });
      }
      var ad = parsed.ads[0];
      if (!ad.mediaFile || !ad.mediaFile.url) {
        return self._finish({ outcome: "nofill", reason: "no-mediafile" });
      }
      return self._showAd(ad);
    }).catch(function (err) {
      /* Network failure / timeout: immediate clean fallback. */
      return self._finish({ outcome: "error", reason: String(err && err.message || err) });
    });
    return this._playPromise;
  };

  VastPlayer.prototype._showAd = function (ad) {
    var self = this;
    {
      self._ad = ad;

      var overlay = document.createElement("div");
      overlay.className = "vast-overlay";
      overlay.setAttribute("data-testid", "vast-ad-overlay");
      var video = document.createElement("video");
      video.className = "vast-video";
      video.setAttribute("playsinline", "");
      video.setAttribute("preload", "auto");
      video.src = ad.mediaFile.url;
      var label = document.createElement("div");
      label.className = "vast-label";
      label.textContent = "Anúncio";
      var skip = document.createElement("button");
      skip.className = "vast-skip";
      skip.type = "button";
      skip.setAttribute("data-testid", "vast-skip-button");
      skip.hidden = true;
      skip.disabled = true;
      self._previousFocus = document.activeElement;
      overlay.appendChild(video);
      overlay.appendChild(label);
      overlay.appendChild(skip);
      self.container.appendChild(overlay);
      self._overlay = overlay;
      self._video = video;
      self._skipBtn = skip;
      self._fired = {};
      self._impressionFired = false;

      /* Watch progress for both startup failure and mid-ad buffering. */
      var armStall = function () {
        clearTimeout(self._stallTimer);
        self._stallTimer = setTimeout(function () {
          if (!self._done) {
            self._fireError(405);
            self._finish({ outcome: "error", reason: "creative-stall" });
          }
        }, STALL_TIMEOUT_MS);
      };
      armStall();
      var lastPosition = -1;
      video.addEventListener("playing", function () {
        if (self._done) return;
        if (!self._impressionFired) {
          self._impressionFired = true;
          fireAll(ad.impressions, null, self.onEvent, "impression");
        }
        self._fire("start");
      });
      video.addEventListener("timeupdate", function () {
        if (self._done) return;
        if (video.currentTime !== lastPosition) { lastPosition = video.currentTime; armStall(); }
        var d = video.duration || ad.duration || 0;
        if (!d) return;
        var p = video.currentTime / d;
        if (p >= 0.25) self._fire("firstQuartile");
        if (p >= 0.50) self._fire("midpoint");
        if (p >= 0.75) self._fire("thirdQuartile");
        var skipAt = offsetToSeconds(ad.skipOffset, d);
        if (skipAt !== null) {
          if (video.currentTime >= skipAt) {
            skip.hidden = false;
            if (skip.disabled) { skip.disabled = false; skip.focus(); }
            skip.textContent = "Pular anúncio";
          } else {
            skip.hidden = false;
            skip.textContent = "Pular anúncio em " + Math.ceil(skipAt - video.currentTime) + "s";
          }
        }
      });
      video.addEventListener("ended", function () {
        self._fire("firstQuartile");
        self._fire("midpoint");
        self._fire("thirdQuartile");
        self._fire("complete");
        self._finish({ outcome: "completed" });
      });
      video.addEventListener("error", function () {
        self._fireError(405);
        self._finish({ outcome: "error", reason: "media-error" });
      });
      skip.addEventListener("click", function () {
        var at = offsetToSeconds(ad.skipOffset, video.duration || ad.duration);
        if (self._done || at === null || video.currentTime < at) return;
        self._fire("skip");
        self._finish({ outcome: "skipped" });
      });
      // A touch/media-key pause must not strand the overlay. Do not rearm
      // the progress watchdog on interaction or on another playing event.
      var resuming = false;
      var resumeAd = function () {
        if (self._done || !video.paused || resuming) return;
        resuming = true;
        var failed = function () {
          resuming = false;
          if (self._done) return;
          self._fireError(405);
          self._finish({ outcome: "error", reason: "resume-blocked" });
        };
        try {
          var attempt = video.play();
          if (attempt && attempt.then) attempt.then(function () { resuming = false; }, failed);
          else resuming = false;
        } catch (e) { failed(); }
      };
      video.addEventListener("pause", resumeAd);
      video.addEventListener("click", function () { if (video.paused) resumeAd(); });
      if (ad.clickThrough) {
        video.addEventListener("click", function () {
          fireAll(ad.clickTracking, null, self.onEvent, "click");
          window.open(ad.clickThrough, "_blank", "noopener");
        });
      }

      var playPromise = video.play();
      if (playPromise && playPromise.catch) {
        playPromise.catch(function () {
          if (self._done) return;
          /* Autoplay with sound blocked: retry muted (still counts as start). */
          video.muted = true;
          var retry = video.play();
          if (retry && retry.catch) {
            retry.catch(function () {
              self._fireError(405);
              self._finish({ outcome: "error", reason: "autoplay-blocked" });
            });
          }
        });
      }
    }
  };

  VastPlayer.prototype._fire = function (eventName) {
    if (this._done || this._fired[eventName]) return;
    this._fired[eventName] = true;
    fireAll(this._ad.tracking[eventName], null, this.onEvent, eventName);
  };

  VastPlayer.prototype._fireError = function (code) {
    if (this._done) return;
    fireAll(this._ad.tracking.error, { errorCode: code }, this.onEvent, "error");
  };

  VastPlayer.prototype._finish = function (result) {
    if (this._done) return result;
    this._done = true;
    clearTimeout(this._stallTimer);
    if (this._video) {
      try { this._video.pause(); this._video.removeAttribute("src"); this._video.load(); } catch (e) {}
    }
    if (this._overlay && this._overlay.parentNode) {
      this._overlay.parentNode.removeChild(this._overlay);
    }
    this._overlay = null;
    this._video = null;
    if (this._previousFocus && this._previousFocus.focus) this._previousFocus.focus();

    /* Exact VOD resume: restore saved position, confirm via "seeked". */
    var self = this;
    var restore = function (done) {
      if (self.resumeTarget && self.resumeTarget.video && self._savedTime !== undefined) {
        var v = self.resumeTarget.video;
        var target = self._savedTime;
        var wasPlaying = self._wasPlaying;
        var settled = false;
        var timer;
        var confirm = function () {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          v.removeEventListener("seeked", confirm);
          result.resumedAt = v.currentTime;
          result.resumeTarget = target;
          result.resumeConfirmed = !v.seeking && Math.abs(v.currentTime - target) <= 0.05;
          if (wasPlaying) {
            try {
              var p = v.play();
              if (p && p.catch) p.catch(function () { result.playbackBlocked = true; });
            } catch (e) { result.playbackBlocked = true; }
          }
          done();
        };
        v.addEventListener("seeked", confirm);
        timer = setTimeout(confirm, 1500);
        if (!v.seeking && Math.abs(v.currentTime - target) <= 0.001) confirm();
        else { try { v.currentTime = target; } catch (e) { confirm(); } }
      } else {
        done();
      }
    };

    restore(function () {
      if (self.onFinish) { try { self.onFinish(result); } catch (e) {} }
      if (self._resolve) self._resolve(result);
    });
    return result;
  };

  /* ---------- public API ---------- */

  window.SmartedtvVast = {
    parseVast: parseVast,
    parseTimeOffset: parseTimeOffset,
    parseClock: parseClock,
    chooseMediaFile: chooseMediaFile,
    fetchVast: fetchVast,
    fetchResolvedVast: fetchResolvedVast,
    expandMacros: expandMacros,
    beacon: beacon,
    VastPlayer: VastPlayer,
    DEFAULT_TIMEOUT_MS: DEFAULT_TIMEOUT_MS
  };
})();
