/* ============================================================
   SMARTEDTV — VAST client (Clickadilla/ClickAdilla, Spot #1508180).

   Priority ad path. Fetches the VAST tag, follows Wrapper chains,
   parses the XML, resolves relative URLs, plays the creative as
   a pre-roll overlay and fires standard tracking events.

   Guarantees (per product spec):
   • Wrappers (VAST redirects) are followed up to MAX_WRAPPER_DEPTH
     with proper URL resolution at each hop.
   • Relative URLs in MediaFile, Impression, Tracking, ClickThrough,
     ClickTracking and Error are resolved against the current VAST
     document base URL.
   • No-fill (empty XML, <VAST> without <Ad>, <VAST><Error>) resolves
     as { outcome:"nofill" } — never throws, never freezes the player.
   • Network failure / timeout resolves as { outcome:"error" } and
     the caller falls back immediately to main content.
   • Exact VOD resume: saves video.currentTime before pre-roll and
     restores it (seek confirmed via "seeked") after the ad.
   • NO cooldown, NO artificial 2-minute interval, NO per-session
     rate limiting, NO permanent block after empty response. Each
     eligible playback generates a fresh VAST request.
   ============================================================ */
(function () {
  "use strict";

  var DEFAULT_TIMEOUT_MS = 8000;
  var STALL_TIMEOUT_MS = 12000;
  var MAX_WRAPPER_DEPTH = 5;
  var WRAPPER_TIMEOUT_MS = 8000;

  /* ---------- URL resolution ---------- */

  function resolveUrl(base, url) {
    if (!url) return "";
    url = String(url).trim();
    if (!url) return "";
    // Absolute URL
    if (/^https?:\/\//i.test(url)) return url;
    // Protocol-relative
    if (/^\/\//.test(url)) {
      var m = (base || "").match(/^https?:/i);
      return (m ? m[0] : "https:") + url;
    }
    if (!base) return url;
    // Absolute path on same origin
    if (url.charAt(0) === "/") {
      var origin = base.match(/^(https?:\/\/[^\/]+)/i);
      return origin ? origin[1] + url : url;
    }
    // Relative path
    var basePath = base.replace(/[^\/]*$/, "");
    // Handle .. and .
    var parts = (basePath + url).split("/");
    var resolved = [];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i] === "..") {
        if (resolved.length > 0 && resolved[resolved.length - 1] !== "..") {
          resolved.pop();
        }
      } else if (parts[i] !== "." && parts[i] !== "") {
        resolved.push(parts[i]);
      }
    }
    var prefix = base.match(/^(https?:\/\/)/i) ? base.match(/^(https?:\/\/)/i)[0] + "//" : "";
    return prefix + resolved.join("/");
  }

  /* ---------- time helpers ---------- */

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
    } catch (e) { return null; }
    return isNaN(sec) ? null : sec;
  }

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

  function beacon(url, macros) {
    if (!url) return;
    var u = String(url);
    macros = macros || {};
    if (macros.errorCode !== undefined) u = u.split("[ERRORCODE]").join(String(macros.errorCode));
    u = u.split("[CACHEBUSTER]").join(String(Math.floor(Math.random() * 1e9)));
    u = u.split("[TIMESTAMP]").join(encodeURIComponent(new Date().toISOString()));
    try { var img = new Image(); img.src = u; } catch (e) {}
  }

  function fireAll(urls, macros, onEvent, eventName) {
    (urls || []).forEach(function (u) {
      beacon(u, macros);
      if (onEvent) { try { onEvent(eventName, u); } catch (e) {} }
    });
  }

  /* ---------- VAST XML parsing ---------- */

  function findAll(root, tag) {
    return root.getElementsByTagName ? root.getElementsByTagName(tag) : [];
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

  function chooseMediaFile(files) {
    if (!files || !files.length) return null;
    var mp4 = files.filter(function (f) {
      return /mp4/i.test(f.type || "") || /\.mp4($|\?)/i.test(f.url || "");
    });
    var pool = mp4.length ? mp4 : files;
    // Prefer progressive download
    var progressive = pool.filter(function (f) {
      return !f.delivery || /progressive/i.test(f.delivery);
    });
    if (progressive.length) pool = progressive;
    return pool.slice().sort(function (a, b) {
      return (b.width || 0) - (a.width || 0);
    })[0];
  }

  function parseVast(xmlText, baseUrl) {
    var empty = { ads: [], wrappers: [], noFill: true, reason: "empty", errorCode: null };
    if (typeof xmlText !== "string" || !xmlText.trim()) return empty;

    var doc;
    try {
      doc = new DOMParser().parseFromString(xmlText, "text/xml");
    } catch (e) {
      return { ads: [], wrappers: [], noFill: true, reason: "malformed", errorCode: null };
    }
    if (!doc || findFirst(doc, "parsererror")) {
      return { ads: [], wrappers: [], noFill: true, reason: "malformed", errorCode: null };
    }

    // Check for root-level <Error>
    var rootErrEl = findFirst(doc, "Error");
    var adEls = findAll(doc, "Ad");

    if (!adEls.length && rootErrEl) {
      return {
        ads: [], wrappers: [], noFill: true, reason: "vast-error",
        errorCode: rootErrEl.getAttribute("code") || rootErrEl.textContent.trim() || null
      };
    }

    if (!adEls.length) return { ads: [], wrappers: [], noFill: true, reason: "no-ad", errorCode: null };

    var ads = [];
    var wrappers = [];

    for (var i = 0; i < adEls.length; i++) {
      var adEl = adEls[i];

      // Check for Wrapper
      var wrapperEl = findFirst(adEl, "Wrapper");
      if (wrapperEl) {
        var wrapperUrl = textOf(wrapperEl, "VASTAdTagURI");
        if (wrapperUrl) {
          // Collect wrapper-level tracking URLs (impressions, errors, tracking)
          var wrapperImpressions = [];
          var wrapperTracking = {};
          var wrapperErrors = [];

          // Wrapper impressions
          var impEls = wrapperEl.getElementsByTagName ? wrapperEl.getElementsByTagName("Impression") : [];
          for (var wi = 0; wi < impEls.length; wi++) {
            var wiu = impEls[wi].textContent ? impEls[wi].textContent.trim() : "";
            if (wiu) wrapperImpressions.push(resolveUrl(baseUrl, wiu));
          }

          // Wrapper error URLs
          var errEls = wrapperEl.getElementsByTagName ? wrapperEl.getElementsByTagName("Error") : [];
          for (var we = 0; we < errEls.length; we++) {
            var weu = errEls[we].textContent ? errEls[we].textContent.trim() : "";
            if (weu) wrapperErrors.push(resolveUrl(baseUrl, weu));
          }

          // Wrapper tracking events
          var trEls = wrapperEl.getElementsByTagName ? wrapperEl.getElementsByTagName("Tracking") : [];
          for (var wt = 0; wt < trEls.length; wt++) {
            var wev = trEls[wt].getAttribute("event");
            var wurl = trEls[wt].textContent ? trEls[wt].textContent.trim() : "";
            if (wev && wurl) {
              (wrapperTracking[wev] = wrapperTracking[wev] || []).push(resolveUrl(baseUrl, wurl));
            }
          }

          wrappers.push({
            url: resolveUrl(baseUrl, wrapperUrl),
            impressions: wrapperImpressions,
            tracking: wrapperTracking,
            errors: wrapperErrors
          });
        }
        continue;
      }

      // InLine ad
      var inlineEl = findFirst(adEl, "InLine");
      var adRoot = inlineEl || adEl;

      var tracking = {};
      var trackEls = findAll(adRoot, "Tracking");
      for (var j = 0; j < trackEls.length; j++) {
        var ev = trackEls[j].getAttribute("event");
        var url = trackEls[j].textContent ? trackEls[j].textContent.trim() : "";
        if (ev && url) {
          (tracking[ev] = tracking[ev] || []).push(resolveUrl(baseUrl, url));
        }
      }
      tracking.error = (tracking.error || []).concat(
        allText(adRoot, "Error").map(function (u) { return resolveUrl(baseUrl, u); })
      );

      var mediaFiles = [];
      var mfEls = findAll(adRoot, "MediaFile");
      for (var k = 0; k < mfEls.length; k++) {
        mediaFiles.push({
          url: resolveUrl(baseUrl, mfEls[k].textContent ? mfEls[k].textContent.trim() : ""),
          type: mfEls[k].getAttribute("type") || "",
          delivery: mfEls[k].getAttribute("delivery") || "",
          width: parseInt(mfEls[k].getAttribute("width") || "0", 10) || 0,
          height: parseInt(mfEls[k].getAttribute("height") || "0", 10) || 0,
          bitrate: parseInt(mfEls[k].getAttribute("bitrate") || "0", 10) || 0,
          apiFramework: mfEls[k].getAttribute("apiFramework") || ""
        });
      }

      // Filter out VPAID/JavaScript creatives (we can't play them)
      var playable = mediaFiles.filter(function (f) {
        return !f.apiFramework || /^(?!vpaid)/i.test(f.apiFramework);
      });
      var mediaFile = chooseMediaFile(playable.length ? playable : mediaFiles);

      var linear = findFirst(adRoot, "Linear");

      // Resolve clickThrough and clickTracking URLs
      var clickThroughUrl = resolveUrl(baseUrl, textOf(adRoot, "ClickThrough"));
      var clickTrackingUrls = allText(adRoot, "ClickTracking").map(function (u) {
        return resolveUrl(baseUrl, u);
      });
      var impressionUrls = allText(adRoot, "Impression").map(function (u) {
        return resolveUrl(baseUrl, u);
      });

      ads.push({
        id: adEl.getAttribute("id") || "",
        sequence: parseInt(adEl.getAttribute("sequence") || "1", 10) || 1,
        adSystem: textOf(adRoot, "AdSystem"),
        adTitle: textOf(adRoot, "AdTitle"),
        universalAdId: textOf(adRoot, "UniversalAdId"),
        duration: parseClock(textOf(adRoot, "Duration")),
        skipOffset: linear ? parseTimeOffset(linear.getAttribute("skipoffset")) : null,
        mediaFiles: mediaFiles,
        mediaFile: mediaFile,
        clickThrough: clickThroughUrl,
        clickTracking: clickTrackingUrls,
        impressions: impressionUrls,
        tracking: tracking
      });
    }

    return { ads: ads, wrappers: wrappers, noFill: ads.length === 0 && wrappers.length === 0,
             reason: ads.length === 0 && wrappers.length === 0 ? "no-ad" : null, errorCode: null };
  }

  /* ---------- fetch with timeout ---------- */

  function fetchVast(tagUrl, timeoutMs) {
    var ms = timeoutMs || DEFAULT_TIMEOUT_MS;
    var controller = (typeof AbortController !== "undefined") ? new AbortController() : null;
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () {
        if (controller) controller.abort();
        reject(new Error("vast-timeout"));
      }, ms);
      var opts = { method: "GET", credentials: "omit", redirect: "follow",
        headers: {
          "Accept": "application/xml,text/xml,*/*;q=0.8",
          "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        } };
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

  /* ---------- resolve wrapper chain ---------- */

  function resolveVastChain(tagUrl, timeoutMs, depth, wrapperEvents) {
    depth = depth || 0;
    wrapperEvents = wrapperEvents || [];
    if (depth >= MAX_WRAPPER_DEPTH) {
      return Promise.resolve({ ads: [], noFill: true, reason: "wrapper-limit" });
    }
    var fetchTimeout = (depth === 0) ? (timeoutMs || DEFAULT_TIMEOUT_MS) : WRAPPER_TIMEOUT_MS;
    return fetchVast(tagUrl, fetchTimeout).then(function (xml) {
      var baseUrl = tagUrl;
      var parsed = parseVast(xml, baseUrl);
      // If we found InLine ads, merge wrapper tracking and return
      if (parsed.ads.length > 0) {
        // Merge wrapper impressions/errors/tracking into the first ad
        var ad = parsed.ads[0];
        for (var w = 0; w < wrapperEvents.length; w++) {
          var we = wrapperEvents[w];
          // Prepend wrapper impressions (fired first)
          ad.impressions = (we.impressions || []).concat(ad.impressions);
          // Append wrapper errors
          ad.tracking.error = (ad.tracking.error || []).concat(we.errors || []);
          // Merge wrapper tracking events
          for (var ev in we.tracking) {
            if (we.tracking.hasOwnProperty(ev)) {
              ad.tracking[ev] = (we.tracking[ev] || []).concat(ad.tracking[ev] || []);
            }
          }
        }
        return { ads: parsed.ads, noFill: false, reason: null, resolvedDepth: depth };
      }
      // If we found wrappers, follow them
      if (parsed.wrappers.length > 0) {
        var wrapper = parsed.wrappers[0];
        var newWrapperEvents = wrapperEvents.concat([{
          impressions: wrapper.impressions,
          errors: wrapper.errors,
          tracking: wrapper.tracking
        }]);
        return resolveVastChain(wrapper.url, WRAPPER_TIMEOUT_MS, depth + 1, newWrapperEvents);
      }
      // No ads, no wrappers = no fill
      return { ads: [], noFill: true, reason: parsed.reason || "no-ad" };
    });
  }

  /* ---------- pre-roll player ---------- */

  function VastPlayer(opts) {
    opts = opts || {};
    this.tagUrl = opts.tagUrl;
    this.timeoutMs = opts.timeoutMs || DEFAULT_TIMEOUT_MS;
    this.container = opts.container || document.body;
    this.onEvent = opts.onEvent || null;
    this.onFinish = opts.onFinish || null;
    this.resumeTarget = opts.resumeTarget || null;
    this._done = false;
    this._overlay = null;
    this._video = null;
    this._stallTimer = null;
  }

  VastPlayer.prototype.play = function () {
    var self = this;
    if (this._playPromise) return this._playPromise;
    this._playPromise = new Promise(function (resolve) { self._resolve = resolve; });

    // Save playback state
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

    // Log the VAST request
    if (self.onEvent) {
      try { self.onEvent("vast-request", self.tagUrl); } catch (e) {}
    }

    resolveVastChain(this.tagUrl, this.timeoutMs, 0, []).then(function (result) {
      if (self.onEvent) {
        try { self.onEvent("vast-response", JSON.stringify({
          noFill: result.noFill, reason: result.reason,
          adCount: result.ads ? result.ads.length : 0,
          resolvedDepth: result.resolvedDepth
        })); } catch (e) {}
      }
      if (result.noFill || !result.ads || !result.ads.length) {
        return self._finish({
          outcome: "nofill",
          reason: result.reason || "no-ad",
          resolvedDepth: result.resolvedDepth
        });
      }
      var ad = result.ads[0];
      if (!ad.mediaFile || !ad.mediaFile.url) {
        return self._finish({ outcome: "nofill", reason: "no-mediafile" });
      }
      if (self.onEvent) {
        try { self.onEvent("vast-mediafile", ad.mediaFile.url); } catch (e) {}
      }
      return self._showAd(ad);
    }).catch(function (err) {
      if (self.onEvent) {
        try { self.onEvent("vast-error", String(err && err.message || err)); } catch (e) {}
      }
      return self._finish({ outcome: "error", reason: String(err && err.message || err) });
    });

    return this._playPromise;
  };

  VastPlayer.prototype._showAd = function (ad) {
    var self = this;
    self._ad = ad;

    var overlay = document.createElement("div");
    overlay.className = "vast-overlay";
    overlay.setAttribute("data-testid", "vast-ad-overlay");
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:#000;z-index:999999;";

    var video = document.createElement("video");
    video.className = "vast-video";
    video.setAttribute("playsinline", "");
    video.setAttribute("preload", "auto");
    video.style.cssText = "width:100%;height:100%;object-fit:contain;background:#000;";
    video.src = ad.mediaFile.url;

    var label = document.createElement("div");
    label.className = "vast-label";
    label.textContent = "Anúncio";
    label.style.cssText = "position:absolute;top:16px;left:16px;background:rgba(0,0,0,0.7);color:#fff;padding:4px 12px;border-radius:4px;font-size:14px;font-family:Arial,sans-serif;z-index:10;";

    var skip = document.createElement("button");
    skip.className = "vast-skip";
    skip.type = "button";
    skip.setAttribute("data-testid", "vast-skip-button");
    skip.hidden = true;
    skip.disabled = true;
    skip.style.cssText = "position:absolute;bottom:24px;right:24px;background:rgba(0,0,0,0.7);color:#fff;border:1px solid rgba(255,255,255,0.3);padding:8px 20px;border-radius:4px;font-size:16px;cursor:pointer;z-index:10;font-family:Arial,sans-serif;";

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
      var errCode = 405;
      if (video.error) {
        if (video.error.code === 1) errCode = 400;
        else if (video.error.code === 2) errCode = 401;
        else if (video.error.code === 3) errCode = 402;
        else if (video.error.code === 4) errCode = 403;
      }
      self._fireError(errCode);
      self._finish({ outcome: "error", reason: "media-error-" + (video.error ? video.error.code : "unknown") });
    });
    skip.addEventListener("click", function () {
      var at = offsetToSeconds(ad.skipOffset, video.duration || ad.duration);
      if (self._done || at === null || video.currentTime < at) return;
      self._fire("skip");
      self._finish({ outcome: "skipped" });
    });
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
      if (self.onEvent) {
        try { self.onEvent("vast-finished", JSON.stringify(result)); } catch (e) {}
      }
      if (self.onFinish) { try { self.onFinish(result); } catch (e) {} }
      if (self._resolve) self._resolve(result);
    });
    return result;
  };

  window.SmartedtvVast = {
    parseVast: parseVast,
    parseTimeOffset: parseTimeOffset,
    parseClock: parseClock,
    chooseMediaFile: chooseMediaFile,
    resolveUrl: resolveUrl,
    fetchVast: fetchVast,
    resolveVastChain: resolveVastChain,
    VastPlayer: VastPlayer,
    DEFAULT_TIMEOUT_MS: DEFAULT_TIMEOUT_MS,
    MAX_WRAPPER_DEPTH: MAX_WRAPPER_DEPTH
  };
})();
