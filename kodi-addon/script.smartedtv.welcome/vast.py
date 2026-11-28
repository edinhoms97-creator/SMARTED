# -*- coding: utf-8 -*-
"""SMARTEDTV — VAST client for Kodi (ClickAdilla, Spot #1508180).

Python twin of smartedtv/js/vast.js. Fetches the VAST tag over TLS
(minimum TLS 1.2, verified), follows VAST Wrapper chains (up to
MAX_WRAPPER_DEPTH), resolves relative URLs, parses the XML and fires
tracking beacons.

Guarantees (same contract as the web client):
- Wrappers (VASTAdTagURI redirects) are followed recursively; wrapper
  impression/error/tracking URLs are merged into the final InLine ad.
- Relative URLs in MediaFile, Impression, Tracking, ClickThrough,
  ClickTracking and Error are resolved against the requesting VAST doc.
- No-fill (empty XML, minimal <VAST> without <Ad>, <VAST><Error>)
  resolves as {"nofill": True} — never raises, never blocks playback.
- Network failure / timeout resolves as {"error": ...} so the caller
  falls back immediately to the main channel/VOD (no black screen).
- NO cooldown, NO artificial 2-minute interval, NO per-session rate
  limiting. Each call is independent.

Playback itself is done by the caller with xbmc.Player; this module
only fetches, resolves wrappers, parses and tracks.
"""
import ssl
import sys
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET

VAST_TAG = "https://vast.yomeno.xyz/vast?spot_id=1508180"
DEFAULT_TIMEOUT = 8
WRAPPER_TIMEOUT = 8
MAX_WRAPPER_DEPTH = 5

# Chrome for Android (Pixel 7) — avoids handshake/EOF blocks on
# ad servers that reject non-browser user agents.
CHROME_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A.230805.001) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 "
    "Mobile Safari/537.36"
)

HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/xml,text/xml,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def _tls_context():
    """Verified TLS context with minimum TLS 1.2."""
    ctx = ssl.create_default_context()
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    except AttributeError:
        ctx.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
    return ctx


def resolve_url(base, url):
    """Resolve a (possibly relative) URL against a base URL."""
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    # Absolute URL
    if url.lower().startswith(("http://", "https://")):
        return url
    # Protocol-relative (//cdn.example.com/...)
    if url.startswith("//"):
        if base and base.lower().startswith("http"):
            scheme = base.split("//")[0]
            return scheme + url
        return "https:" + url
    if not base:
        return url
    # Use urllib.parse.urljoin for proper resolution (handles . and .. correctly)
    from urllib.parse import urljoin
    # Ensure base has a trailing path component for urljoin to work correctly
    if "/" not in base.split("://", 1)[-1] if "://" in base else "/" not in base:
        base = base + "/"
    return urljoin(base, url)


def fetch_vast(tag_url=VAST_TAG, timeout=DEFAULT_TIMEOUT):
    """Fetch the VAST XML. Returns text, or raises on network error."""
    req = urllib.request.Request(tag_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=_tls_context()) as resp:
        # Verify final URL is still HTTPS
        final_url = resp.geturl()
        if not final_url.lower().startswith("https://"):
            raise ValueError("Refusing non-HTTPS redirect to: " + final_url)
        data = resp.read()
        return data.decode("utf-8", errors="replace")


def _parse_clock(text):
    """'HH:MM:SS.mmm' | 'MM:SS' | 'SS' -> float seconds or None."""
    if not text:
        return None
    parts = text.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 1:
            return float(parts[0])
    except (ValueError, IndexError):
        return None
    return None


def _parse_offset(text):
    """VAST skipoffset: '00:00:05' -> {'type':'time','seconds':5};
    '25%' -> {'type':'percent','value':25}; else None."""
    if not text:
        return None
    text = text.strip()
    if text.endswith("%"):
        try:
            return {"type": "percent", "value": float(text[:-1])}
        except ValueError:
            return None
    sec = _parse_clock(text)
    return {"type": "time", "seconds": sec} if sec is not None else None


def _text(el, tag):
    child = el.find(".//" + tag) if el is not None else None
    return (child.text or "").strip() if child is not None and child.text else ""


def _all_text(el, tag):
    return [(c.text or "").strip() for c in el.findall(".//" + tag)
            if c.text and (c.text or "").strip()]


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def choose_media_file(files):
    """Prefer progressive MP4, highest width first; else first file."""
    if not files:
        return None
    # Filter out VPAID/JavaScript creatives
    playable = [f for f in files if not (f.get("api_framework") or "").lower().startswith("vpaid")]
    pool = playable if playable else files
    mp4 = [f for f in pool if "mp4" in (f.get("type") or "").lower()
           or (f.get("url") or "").split("?")[0].lower().endswith(".mp4")]
    if mp4:
        pool = mp4
    # Prefer progressive delivery
    progressive = [f for f in pool if not f.get("delivery") or f.get("delivery", "").lower() == "progressive"]
    if progressive:
        pool = progressive
    return sorted(pool, key=lambda f: f.get("width") or 0, reverse=True)[0]


def parse_vast(xml_text, base_url=""):
    """Parse VAST XML text.

    Returns {"ads": [...], "wrappers": [...], "nofill": bool,
    "reason": str|None, "error_code": str|None}. NEVER raises on no-fill
    or malformed input.
    """
    empty = {"ads": [], "wrappers": [], "nofill": True, "reason": "empty", "error_code": None}
    if not xml_text or not xml_text.strip():
        return empty
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"ads": [], "wrappers": [], "nofill": True, "reason": "malformed", "error_code": None}

    ad_els = root.findall(".//Ad")
    err = root.find(".//Error")

    if not ad_els and err is not None:
        return {"ads": [], "wrappers": [], "nofill": True, "reason": "vast-error",
                "error_code": err.get("code") or (err.text or "").strip() or None}

    if not ad_els:
        return {"ads": [], "wrappers": [], "nofill": True, "reason": "no-ad", "error_code": None}

    ads = []
    wrappers = []

    for ad_el in ad_els:
        # Check for Wrapper first
        wrapper_el = ad_el.find(".//Wrapper")
        if wrapper_el is not None:
            wrapper_url = _text(wrapper_el, "VASTAdTagURI")
            if wrapper_url:
                w_impressions = [resolve_url(base_url, (i.text or "").strip())
                                for i in wrapper_el.findall(".//Impression")
                                if i.text and (i.text or "").strip()]
                w_errors = [resolve_url(base_url, (e.text or "").strip())
                           for e in wrapper_el.findall(".//Error")
                           if e.text and (e.text or "").strip()]
                w_tracking = {}
                for tr in wrapper_el.findall(".//Tracking"):
                    ev, u = tr.get("event"), (tr.text or "").strip()
                    if ev and u:
                        w_tracking.setdefault(ev, []).append(resolve_url(base_url, u))
                wrappers.append({
                    "url": resolve_url(base_url, wrapper_url),
                    "impressions": w_impressions,
                    "errors": w_errors,
                    "tracking": w_tracking,
                })
            continue

        # InLine ad
        inline_el = ad_el.find(".//InLine")
        ad_root = inline_el if inline_el is not None else ad_el

        tracking = {}
        for tr in ad_root.findall(".//Tracking"):
            ev, url = tr.get("event"), (tr.text or "").strip()
            if ev and url:
                tracking.setdefault(ev, []).append(resolve_url(base_url, url))

        error_urls = [resolve_url(base_url, (e.text or "").strip())
                     for e in ad_root.findall(".//Error")
                     if e.text and (e.text or "").strip()]
        tracking["error"] = tracking.get("error", []) + error_urls

        media_files = []
        for mf in ad_root.findall(".//MediaFile"):
            media_files.append({
                "url": resolve_url(base_url, (mf.text or "").strip()),
                "type": mf.get("type") or "",
                "delivery": mf.get("delivery") or "",
                "width": _integer(mf.get("width")),
                "height": _integer(mf.get("height")),
                "bitrate": _integer(mf.get("bitrate")),
                "api_framework": mf.get("apiFramework") or "",
            })

        media_file = choose_media_file(media_files)

        linear = ad_root.find(".//Linear")

        ads.append({
            "id": ad_el.get("id") or "",
            "ad_system": _text(ad_root, "AdSystem"),
            "ad_title": _text(ad_root, "AdTitle"),
            "duration": _parse_clock(_text(ad_root, "Duration")),
            "skip_offset": _parse_offset(linear.get("skipoffset")) if linear is not None else None,
            "media_files": media_files,
            "media_file": media_file,
            "click_through": resolve_url(base_url, _text(ad_root, "ClickThrough")),
            "click_tracking": [resolve_url(base_url, u) for u in _all_text(ad_root, "ClickTracking")],
            "impressions": [resolve_url(base_url, u) for u in _all_text(ad_root, "Impression")],
            "tracking": tracking,
        })

    return {"ads": ads, "wrappers": wrappers,
            "nofill": len(ads) == 0 and len(wrappers) == 0,
            "reason": None if (ads or wrappers) else "no-ad",
            "error_code": None}


def fire(url, error_code=None):
    """Fire-and-forget tracking beacon. Never raises."""
    if not url:
        return
    if error_code is not None:
        url = url.replace("[ERRORCODE]", str(error_code))
    import random
    import datetime
    url = url.replace("[CACHEBUSTER]", str(random.randint(10000000, 99999999)))
    url = url.replace("[TIMESTAMP]", urllib.parse.quote(
        datetime.datetime.now(datetime.timezone.utc).isoformat()))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
        urllib.request.urlopen(req, timeout=5, context=_tls_context()).close()
    except Exception:
        pass  # tracking must never break playback


def fire_all(urls, error_code=None):
    import threading

    def send():
        for url in urls or []:
            fire(url, error_code=error_code)

    threading.Thread(target=send, daemon=True).start()


def resolve_chain(tag_url=VAST_TAG, timeout=DEFAULT_TIMEOUT, depth=0, wrapper_events=None):
    """Resolve VAST wrapper chain recursively, following up to MAX_WRAPPER_DEPTH hops.

    Returns {"outcome": "ad"|"nofill"|"error", "ad": dict|None, ...}.
    Wrapper impression/error/tracking URLs are merged into the final ad.
    """
    if wrapper_events is None:
        wrapper_events = []
    if depth >= MAX_WRAPPER_DEPTH:
        return {"outcome": "nofill", "reason": "wrapper-limit", "ad": None, "depth": depth}
    try:
        fetch_timeout = timeout if depth == 0 else WRAPPER_TIMEOUT
        xml_text = fetch_vast(tag_url, timeout=fetch_timeout)
    except Exception as exc:
        return {"outcome": "error", "reason": str(exc), "ad": None, "depth": depth}
    try:
        parsed = parse_vast(xml_text, base_url=tag_url)
    except Exception as exc:
        return {"outcome": "error", "reason": "parse-error: " + str(exc), "ad": None, "depth": depth}

    if parsed["ads"]:
        ad = parsed["ads"][0]
        # Merge wrapper tracking events into the ad
        for w_evt in wrapper_events:
            ad["impressions"] = (w_evt.get("impressions", []) + ad.get("impressions", []))
            ad["tracking"]["error"] = ad.get("tracking", {}).get("error", []) + w_evt.get("errors", [])
            for ev_name, ev_urls in w_evt.get("tracking", {}).items():
                ad["tracking"][ev_name] = ev_urls + ad.get("tracking", {}).get(ev_name, [])
        return {"outcome": "ad", "ad": ad, "depth": depth}

    if parsed["wrappers"]:
        wrapper = parsed["wrappers"][0]
        new_wrapper_events = wrapper_events + [{
            "impressions": wrapper["impressions"],
            "errors": wrapper["errors"],
            "tracking": wrapper["tracking"],
        }]
        return resolve_chain(wrapper["url"], WRAPPER_TIMEOUT, depth + 1, new_wrapper_events)

    return {"outcome": "nofill", "reason": parsed.get("reason", "no-ad"),
            "error_code": parsed.get("error_code"), "ad": None, "depth": depth}


def play_preroll_or_fallback(tag_url=VAST_TAG, timeout=DEFAULT_TIMEOUT, on_event=None):
    """Fetch + resolve wrappers + select the first ad (no playback beacons yet).

    Returns {"outcome": "ad"|"nofill"|"error", "ad": ad|None, ...}.
    NEVER raises: any failure resolves as nofill/error so the caller
    can fall back immediately to the main channel/VOD.
    """
    if on_event:
        try:
            on_event("vast-request", tag_url)
        except Exception:
            pass
    try:
        result = resolve_chain(tag_url, timeout=timeout)
    except Exception as exc:
        if on_event:
            try:
                on_event("vast-error", str(exc))
            except Exception:
                pass
        return {"outcome": "error", "reason": str(exc), "ad": None}

    if on_event:
        try:
            on_event("vast-response", str({
                "outcome": result["outcome"],
                "reason": result.get("reason"),
                "depth": result.get("depth"),
                "ad_title": (result.get("ad") or {}).get("ad_title", ""),
                "media_url": ((result.get("ad") or {}).get("media_file") or {}).get("url", ""),
            }))
        except Exception:
            pass

    if result["outcome"] == "ad":
        ad = result["ad"]
        if not ad.get("media_file") or not ad["media_file"].get("url"):
            return {"outcome": "nofill", "reason": "no-mediafile", "ad": None}
        return result
    return result
