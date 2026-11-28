"""VAST macro expansion and the real Kodi/platform User-Agent; no SDK/AdMob."""
import datetime
import random
import re
import sys
from urllib.parse import quote


def device_user_agent(kodi=None):
    if kodi is None:
        try:
            import xbmc as kodi
        except ImportError:
            kodi = None
    try:
        value = kodi.getUserAgent()
        if isinstance(value, str) and value.strip() and not any(c in value for c in '\r\n'):
            return value.strip()
    except Exception:
        pass
    try:
        if kodi.getCondVisibility('System.Platform.Android'):
            # Coarse but truthful fallback. Never claim Pixel/Chrome versions
            # which are not exposed by this Kodi runtime.
            return 'Kodi (Android)'
    except Exception:
        pass
    return 'Python-urllib/%d.%d' % sys.version_info[:2]


def expand(url, error_code=None, user_agent=None):
    """Replace literal AND URL-encoded common macros, with one 8-digit nonce.

    Preserve duplicate Impression nodes: expansion never deduplicates URLs.
    Unknown macros are left untouched, not populated with fabricated IDs.
    """
    nonce = str(random.randint(10000000, 99999999))
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    values = {'CACHEBUSTING': nonce, 'CACHEBUSTER': nonce, 'RANDOM': nonce,
              'TIMESTAMP': quote(timestamp, safe='')}
    if error_code is not None:
        values['ERRORCODE'] = str(error_code)
    if user_agent:
        values['DEVICEUA'] = quote(user_agent, safe='')
    text = str(url or '')
    for name, value in values.items():
        for pattern in (r'\[' + name + r'\]', r'%5b' + name + r'%5d', r'%%' + name + r'%%'):
            text = re.sub(pattern, lambda match: value, text, flags=re.I)
    return text
