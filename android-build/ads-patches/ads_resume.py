"""In-memory resolved-content session. No plugin routes, UI or AdMob.

Kodi ListItems are kept alive, not serialized to disk. Only already-resolved
alternatives for the SAME content may be retried; a playlist's next episode
is never a server fallback. A provider can publish resolved alternatives with
publish_context before setResolvedUrl; capture consumes that window context.
"""
import json
import math
import time
from urllib.parse import urlsplit, parse_qs
import hashlib
from collections import OrderedDict

CONTEXT_PROPERTY = 'Smarted.VAST.ResolvedContext.v1'
_RESOLVED_CACHE = OrderedDict()


def direct_stream(url):
    if not isinstance(url, str) or not url.strip() or '\n' in url or '\r' in url:
        return False
    path = url.split('|', 1)[0]
    try:
        scheme = urlsplit(path).scheme.lower()
        return (scheme in ('http', 'https', 'rtmp', 'rtmps', 'rtsp', 'rtp', 'udp',
                           'smb', 'nfs', 'file', 'special', 'pvr') or path.startswith('/')) and not path.lower().endswith('.strm')
    except ValueError:
        return False


def publish_context(current, alternatives, content_id, gui, now=None):
    """Optional provider bridge; accepts resolved URLs only, not host pages.

    The producer must mark alternatives resolved=True and bind content_id.
    No URL is resolved or guessed here. Window properties are process-memory
    transport between Kodi add-on interpreters, never preferences/files.
    """
    if not direct_stream(current) or not content_id:
        return False
    streams = []
    for candidate in alternatives or []:
        if (isinstance(candidate, dict) and candidate.get('resolved') is True
                and candidate.get('content_id') == content_id and direct_stream(candidate.get('url'))):
            streams.append({key: candidate[key] for key in ('url', 'properties', 'mime', 'label') if key in candidate})
    data = {'current': current, 'content_id': str(content_id), 'streams': streams[:12],
            'created': time.monotonic() if now is None else now}
    gui.Window(10000).setProperty(CONTEXT_PROPERTY, json.dumps(data))
    return True


def _identity(item):
    try:
        explicit = item.getProperty('smarted.resume.content_id')
        if explicit:
            return ('provider', explicit)
        tag = item.getVideoInfoTag()
        kind = tag.getMediaType()
        uid = tag.getUniqueID('imdb')
        if kind == 'movie' and uid:
            return (kind, uid)
        if kind == 'episode' and uid and tag.getSeason() >= 0 and tag.getEpisode() >= 0:
            return (kind, uid, tag.getSeason(), tag.getEpisode())
    except Exception:
        pass
    return None


def capture(state, player, kodi, gui=None):
    """Snapshot exact resolved file, ListItem, metadata and safe alternatives."""
    if not state:
        return None
    if state.get('_resolved_snapshot'):
        return state
    result = dict(state)
    streams = []
    seen = set()
    item = None
    try:
        owns_state = player.isPlayingVideo() and player.getPlayingFile() == result.get('caminho')
    except Exception:
        owns_state = False
    try:
        item = player.getPlayingItem() if owns_state else None
    except Exception:
        pass
    metadata = result.get('metadata') or {}
    try:
        if not owns_state:
            raise ValueError('do not snapshot the ad or a newer film')
        reply = json.loads(kodi.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1,
            'method': 'Player.GetItem', 'params': {'playerid': 1,
            'properties': ['title', 'plot', 'art', 'season', 'episode', 'uniqueid', 'streamdetails']}})))
        metadata = reply.get('result', {}).get('item') or {}
    except Exception:
        pass
    result['listitem'] = item
    result['metadata'] = metadata
    # Preserve the exact playing URL, including pipe headers and token query.
    def add(url, listitem=None, properties=None, mime='', label=''):
        if direct_stream(url) and url not in seen:
            seen.add(url)
            streams.append({'url': url, 'listitem': listitem, 'properties': properties or {},
                            'mime': mime, 'label': label})
    add(result.get('caminho'), item)
    try:
        add(item.getPath(), item)
    except Exception:
        pass
    add(result.get('url_real'), item)
    # Explicit session alternatives are accepted only with resolved status and
    # a matching content identity. No plugin/hoster selection route is opened.
    content_id = result.get('content_id')
    origins = [result.get('plugin_path', ''), metadata.get('file', '')]
    if item is not None:
        for getter in (lambda: item.getPath(), lambda: item.getProperty('original_listitem_url')):
            try:
                origins.append(getter())
            except Exception:
                pass
    origin_key = None
    result['available_servers'] = []
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            if parsed.scheme != 'plugin':
                continue
            if (parse_qs(parsed.query).get('url') or [''])[0]:
                origin_key = origin_key or hashlib.sha256(origin.encode()).hexdigest()
            # Actual bundled Brazuca contract: #movies_list=slot|slot... .
            # Only already-direct media slots can be restored without running
            # a hoster resolver/UI. Never treat a Mixdrop embed page as MP4.
            if parsed.netloc.lower() == 'plugin.video.brazucaplay.matrix':
                route = (parse_qs(parsed.query).get('url') or [''])[0]
                if route.startswith('#movies_list='):
                    for value in route[len('#movies_list='):].split('|'):
                        media_path = urlsplit(value).path.lower()
                        resolved = direct_stream(value) and media_path.endswith(('.mp4', '.m3u8', '.mpd', '.ts', '.mkv', '.m4v', '.webm'))
                        result['available_servers'].append({'url': value, 'resolved': resolved})
                        if resolved:
                            add(value)
        except Exception:
            pass
    if origin_key:
        # Retain prior resolved servers only for exactly the same plugin
        # content route, never other episodes or a generic addon root.
        cacheable = any('?' in value and 'url=' in value for value in origins if isinstance(value, str) and value.startswith('plugin://'))
        if cacheable:
            previous = _RESOLVED_CACHE.pop(origin_key, None)
            if previous and 0 <= time.monotonic() - previous[0] <= 600:
                for candidate in previous[1]:
                    add(candidate['url'], candidate.get('listitem'), candidate.get('properties'))
            _RESOLVED_CACHE[origin_key] = (time.monotonic(), list(streams[:16]))
            while len(_RESOLVED_CACHE) > 8:
                _RESOLVED_CACHE.popitem(last=False)
    for candidate in result.get('alternativas_resolvidas') or []:
        if (isinstance(candidate, dict) and content_id and candidate.get('resolved') is True
                and candidate.get('content_id') == content_id):
            add(candidate.get('url'), candidate.get('listitem'), candidate.get('properties'),
                candidate.get('mime', ''), candidate.get('label', ''))
    if gui is None:
        try:
            import xbmcgui as gui
        except ImportError:
            gui = None
    if gui is not None and owns_state:
        try:
            window = gui.Window(10000)
            context = json.loads(window.getProperty(CONTEXT_PROPERTY) or '{}')
            age = time.monotonic() - float(context.get('created', 0))
            if context.get('current') == result.get('caminho') and 0 <= age <= 600:
                window.clearProperty(CONTEXT_PROPERTY)  # consume once per opening
                result['content_id'] = context.get('content_id')
                for candidate in context.get('streams', [])[:12]:
                    add(candidate.get('url'), properties=candidate.get('properties'),
                        mime=candidate.get('mime', ''), label=candidate.get('label', ''))
        except Exception:
            pass
    identity = _identity(item) if item else None
    if identity:
        try:
            playlist = kodi.PlayList(kodi.PLAYLIST_VIDEO)
            for index in range(min(playlist.size(), 100)):
                alternative = playlist[index]
                if _identity(alternative) == identity:
                    add(alternative.getPath(), alternative)
        except Exception:
            pass
    result['_resolved_snapshot'] = True
    result['resolved_streams'] = streams[:16]
    return result


def _listitem(candidate, state, gui):
    existing = candidate.get('listitem')
    if existing is not None:
        # The original Brazuca sets ForceResolvePlugin=true. Carrying that
        # routing flag back with the metadata can re-enter the server chooser.
        try:
            existing.setPath(candidate['url'])
        except Exception:
            pass
        existing.setProperty('ForceResolvePlugin', 'false')
        existing.setProperty('original_listitem_url', '')
        existing.setProperty('IsPlayable', 'true')
        existing.setProperty('StartOffset', '0' if state.get('ao_vivo') else str(state.get('posicao') or 0))
        existing.setProperty('ResumeTime', '0' if state.get('ao_vivo') else str(state.get('posicao') or 0))
        if state.get('ao_vivo'):
            try:
                existing.getVideoInfoTag().setResumePoint(0, 0)
            except Exception:
                pass
        return existing
    if gui is None:
        return None
    item = gui.ListItem(label=candidate.get('label') or state.get('metadata', {}).get('title') or '',
                        path=candidate['url'])
    item.setProperty('IsPlayable', 'true')
    metadata = state.get('metadata') or {}
    try:
        item.setInfo('video', {key: metadata[key] for key in ('title', 'plot', 'season', 'episode') if key in metadata})
        item.setArt(metadata.get('art') or {})
    except Exception:
        pass
    for name, value in (candidate.get('properties') or {}).items():
        if isinstance(name, str) and isinstance(value, str):
            item.setProperty(name, value)
    if candidate.get('mime'):
        item.setMimeType(candidate['mime'])
        item.setContentLookup(False)
    return item


def restore(state, kodi, gui=None, wait=20, sleep=None, clock=None, ad_url='', fullscreen=None, log=None):
    """Open saved streams directly; confirm progress and VOD seek before success.

    Never invokes PlayMedia(plugin://...), RunPlugin, a provider UI, or a
    synchronous resolver. Core Kodi error dialogs cannot be controlled here;
    no application error/dialog is emitted before exhausting saved streams.
    """
    if not state:
        return False
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    if gui is None:
        try:
            import xbmcgui as gui
        except ImportError:
            gui = None
    streams = [c for c in state.get('resolved_streams', []) if direct_stream(c.get('url'))]
    if not streams:
        return False
    target = max(0.0, float(state.get('posicao') or 0))
    live = bool(state.get('ao_vivo'))
    if not math.isfinite(target):
        return False
    deadline = clock() + min(max(float(wait), .1), 24.0)
    player = kodi.Player()
    observer = None
    expected = ['']
    ready = [False]
    failures = [False]
    class Observer(kodi.Player):
        active = False
        def onPlayBackError(self):
            if self.active:
                try:
                    if not self.isPlayingVideo() or self.getPlayingFile() == expected[0]:
                        failures[0] = True
                except Exception:
                    failures[0] = True
        def onAVStarted(self):
            if self.active:
                ready[0] = True
    observer = Observer()
    try:
        for index, candidate in enumerate(streams):
            if clock() >= deadline:
                break
            url = candidate['url']
            expected[0] = url
            failures[0], ready[0] = False, False
            observer.active = False
            try:
                current = player.getPlayingFile() if player.isPlayingVideo() else ''
                # A new content choice wins over this restoration session.
                allowed = {ad_url, state.get('caminho', ''), ''} | {c['url'] for c in streams}
                if current not in allowed:
                    return False
                item = _listitem(candidate, state, gui)
                observer.active = True
                player.play(url, listitem=item, windowed=False) if item is not None else player.play(url, windowed=False)
                # Reserve time for each remaining server; stale callbacks from
                # the stopped ad do not prove that this stream is ready.
                remaining = max(.1, deadline - clock())
                route_deadline = min(deadline, clock() + min(6.0, remaining / (len(streams) - index)))
                initial, advanced, progress_at, stable_since = None, False, None, None
                sought, seek_confirmed = live, live
                while clock() < route_deadline:
                    if failures[0]:
                        break
                    if player.isPlayingVideo():
                        current = player.getPlayingFile()
                        if current == ad_url or not current:
                            sleep(.1)
                            continue
                        if current != url:
                            return False  # never seek/stop a newer selection
                        position = float(player.getTime())
                        if not math.isfinite(position):
                            raise ValueError('invalid player clock')
                        if initial is None:
                            initial, progress_at = position, clock()
                        elif position > initial + .02:
                            advanced, initial, progress_at = True, position, clock()
                        if not sought and (ready[0] or advanced):
                            player.seekTime(target)
                            sought = True
                            initial, advanced, progress_at, stable_since = None, False, None, None
                            # Observe the seek on the next tick, not only the
                            # synchronous value a failed player may report.
                            sleep(.1)
                            continue
                        if sought and not live and abs(position - target) <= .25:
                            seek_confirmed = True
                        healthy = sought and seek_confirmed and advanced and progress_at is not None and clock() - progress_at <= .3
                        if healthy:
                            stable_since = clock() if stable_since is None else stable_since
                        else:
                            stable_since = None
                        if stable_since is not None and clock() - stable_since >= .8:
                            observer.active = False
                            state['_restored_path'] = current
                            if fullscreen:
                                fullscreen()
                            if state.get('smarted_estava_pausado') and not kodi.getCondVisibility('Player.Paused'):
                                player.pause()
                            return True
                    sleep(.1)
            except Exception:
                pass  # try the next saved server, with no provider dialog
            finally:
                observer.active = False
            try:
                # Stop a failed stream before trying the next one. Never stop
                # an unrelated film the user selected during this attempt.
                if player.getPlayingFile() == url:
                    player.stop()
            except Exception:
                pass
            if log:
                log('[SmartAdsDiag] retomada-alternativa %d/%d' % (index + 1, len(streams)))
        if log:
            log('[SmartAdsDiag] retomada-nao-confirmada; destinos-resolvidos-esgotados')
        return False
    finally:
        observer.active = False
