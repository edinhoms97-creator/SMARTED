# -*- coding: utf-8 -*-
"""SMARTEDTV — VAST client for Kodi (Clickadilla, Spot #1508180).

Python twin of smartedtv/js/vast.js. Fetches the VAST tag over TLS
(minimum TLS 1.2, verified) with the real Kodi/platform User-Agent,
parses the XML and fires tracking beacons.

Guarantees (same contract as the web client):
- No-fill (empty XML, minimal <VAST> without <Ad>, <VAST><Error>)
  resolves as {"nofill": True} — never raises, never blocks playback.
- Network failure / timeout resolves as {"error": ...} so the caller
  falls back immediately to the main channel/VOD (no black screen).

Playback itself is done by the caller with xbmc.Player; this module
only fetches, parses and tracks. Exact VOD resume (save position
before the pre-roll, seek back after) is the caller's job — see
default.py and docs/HANDOFF.md.
"""
import ssl
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET

VAST_TAG = "https://vast.yomeno.xyz/vast?spot_id=1508180"
DEFAULT_TIMEOUT = 8

from ads_tracking import device_user_agent, expand

HEADERS = {
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


def fetch_vast(tag_url=VAST_TAG, timeout=DEFAULT_TIMEOUT):
    """Fetch the VAST XML. Returns text, or raises on network error."""
    req = urllib.request.Request(tag_url, headers=dict(HEADERS, **{"User-Agent": device_user_agent()}))
    with urllib.request.urlopen(req, timeout=timeout, context=_tls_context()) as resp:
        return resp.read().decode("utf-8", errors="replace")


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
    except ValueError:
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


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def choose_media_file(files):
    """Prefer progressive MP4, highest width first; else first file."""
    if not files:
        return None
    mp4 = [f for f in files if "mp4" in (f.get("type") or "").lower()
           or (f.get("url") or "").split("?")[0].endswith(".mp4")]
    pool = mp4 or files
    return sorted(pool, key=lambda f: f.get("width") or 0, reverse=True)[0]


def parse_vast(xml_text):
    """Parse VAST XML text.

    Returns {"ads": [...], "nofill": bool, "reason": str|None,
    "error_code": str|None}. NEVER raises on no-fill / empty /
    malformed input — those resolve as nofill so the caller can
    fall back cleanly to the main content.
    """
    empty = {"ads": [], "nofill": True, "reason": "empty", "error_code": None}
    if not xml_text or not xml_text.strip():
        return empty
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"ads": [], "nofill": True, "reason": "malformed", "error_code": None}

    for node in root.iter():
        node.tag = node.tag.rsplit('}', 1)[-1]
    ad_els = root.findall(".//Ad")
    err = root.find(".//Error")
    if not ad_els and err is not None:
        return {"ads": [], "nofill": True, "reason": "vast-error",
                "error_code": err.get("code") or (err.text or "").strip() or None}

    if not ad_els:
        return {"ads": [], "nofill": True, "reason": "no-ad", "error_code": None}

    ads = []
    for ad_el in ad_els:
        tracking = {}
        for tr in ad_el.findall(".//Tracking"):
            ev, url = tr.get("event"), (tr.text or "").strip()
            if ev and url:
                tracking.setdefault(ev, []).append(url)
        tracking["error"] = tracking.get("error", []) + [
            (el.text or "").strip() for el in ad_el.findall(".//Error")
            if (el.text or "").strip()]
        media_files = []
        for mf in ad_el.findall(".//MediaFile"):
            media_files.append({
                "url": (mf.text or "").strip(),
                "type": mf.get("type") or "",
                "delivery": mf.get("delivery") or "",
                "width": _integer(mf.get("width")),
                "height": _integer(mf.get("height")),
                "bitrate": _integer(mf.get("bitrate")),
            })
        linear = ad_el.find(".//Linear")
        ads.append({
            "id": ad_el.get("id") or "",
            "wrapper_url": _text(ad_el, "VASTAdTagURI") or _text(ad_el, "VASTAdTagURL"),
            "ad_system": _text(ad_el, "AdSystem"),
            "ad_title": _text(ad_el, "AdTitle"),
            "duration": _parse_clock(_text(ad_el, "Duration")),
            "skip_offset": _parse_offset(linear.get("skipoffset")) if linear is not None else None,
            "media_files": media_files,
            "media_file": choose_media_file(media_files),
            "click_through": _text(ad_el, "ClickThrough"),
            "impressions": [(i.text or "").strip() for i in ad_el.findall(".//Impression") if (i.text or "").strip()],
            "tracking": tracking,
        })
    return {"ads": ads, "nofill": False, "reason": None, "error_code": None}


def fire(url, error_code=None):
    """Fire-and-forget tracking beacon. Never raises."""
    if not url:
        return
    url = expand(url, error_code=error_code, user_agent=device_user_agent())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": device_user_agent()})
        urllib.request.urlopen(req, timeout=5, context=_tls_context()).close()
    except Exception:
        pass  # tracking must never break playback


def fire_all(urls, error_code=None):
    import threading

    def send():
        for url in urls or []:
            fire(url, error_code=error_code)

    threading.Thread(target=send, daemon=True).start()


def play_preroll_or_fallback(tag_url=VAST_TAG, timeout=DEFAULT_TIMEOUT, on_event=None):
    """Fetch + parse + select the first ad (no playback beacons yet).

    Returns {"outcome": "ad"|"nofill"|"error", "ad": ad|None, ...}.
    NEVER raises: any failure resolves as nofill/error so the caller
    can fall back immediately to the main channel/VOD.
    """
    import time
    deadline = time.monotonic() + min(float(timeout), DEFAULT_TIMEOUT)
    current, visited = tag_url, set()
    inherited_impressions, inherited_tracking = [], {}
    def failure(outcome, reason, code):
        fire_all(inherited_tracking.get('error') or [], error_code=code)
        return {'outcome': outcome, 'reason': reason, 'ad': None, 'error_code': code}
    for _ in range(6):
        if current in visited:
            return failure('error', 'wrapper-cycle', 302)
        visited.add(current)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return failure('error', 'vast-timeout', 301)
        try:
            parsed = parse_vast(fetch_vast(expand(current, user_agent=device_user_agent()), timeout=remaining))
        except Exception:
            return failure('error', 'network-failed', 301)
        if not parsed['ads']:
            return failure('nofill', parsed['reason'], 303)
        ad = parsed['ads'][0]
        if ad.get('wrapper_url') and not ad.get('media_file'):
            inherited_impressions.extend(ad['impressions'])
            for event, urls in ad['tracking'].items():
                inherited_tracking.setdefault(event, []).extend(urls)
            current = ad['wrapper_url']
            continue
        if not ad['media_file'] or not ad['media_file']['url']:
            return failure('nofill', 'no-mediafile', 403)
        ad['impressions'] = inherited_impressions + ad['impressions']
        for event, urls in inherited_tracking.items():
            ad['tracking'][event] = urls + ad['tracking'].get(event, [])
        return {'outcome': 'ad', 'ad': ad}
    return failure('error', 'wrapper-limit', 302)
