"""In-memory opening generations and URL-free stage diagnostics; no ad transport."""
import json
import threading
import time

_LOCAL = threading.local()
_BATCH_LOCK = threading.Lock()
_BATCH = 0


def emit(kodi, stage, **fields):
    message = dict(stage=stage, opening=getattr(_LOCAL, 'opening', None),
                   monotonic_ms=round(time.monotonic() * 1000), **fields)
    try:
        kodi.log('[SmartAdsOpening] ' + json.dumps(message, ensure_ascii=True), getattr(kodi, 'LOGINFO', 1))
    except Exception:
        pass


def context(opening):
    _LOCAL.opening = opening


def batch_id():
    global _BATCH
    with _BATCH_LOCK:
        _BATCH += 1
        return _BATCH


class Opening:
    def __init__(self):
        self.lock = threading.RLock()
        self.generation = 0
        self.aliases = set()
        self.channel = ''
        self.attempted = False
        self.closed = True
        self.in_ad = False
        self.saw_fullscreen = False
        self.home_boundary = False

    def claim(self, path, channel=''):
        with self.lock:
            if self.in_ad:
                return None
            same = path in self.aliases and (not channel or not self.channel or channel == self.channel)
            if channel and self.channel and channel == self.channel:
                same = True  # native channel identity survives proxy/token refresh
            if self.closed or not same:
                self.generation += 1
                self.aliases, self.channel = {path}, channel
                self.attempted, self.closed = False, False
            if same:
                self.aliases.add(path)
            if same and channel and not self.channel:
                self.channel = channel
            if self.attempted:
                return None
            self.attempted, self.in_ad = True, True
            self.home_boundary = False
            return self.generation

    def finish(self, generation, returned=''):
        with self.lock:
            if generation != self.generation:
                return
            if returned:
                self.aliases.add(returned)
            self.in_ad = False

    def close(self):
        with self.lock:
            if self.in_ad or self.closed:
                return False
            self.closed, self.attempted = True, False
            return True

    def observe_ui(self, home, fullscreen):
        """Home is an explicit UI boundary even when Kodi keeps video behind it.

        Never interpret OSD/pause/seek or loss of Android focus as a close.
        Initial Home and temporary ad transitions do not create boundaries.
        """
        with self.lock:
            if self.in_ad:
                return False
            if home and self.saw_fullscreen:
                self.closed, self.attempted = True, False
                self.home_boundary, self.saw_fullscreen = True, False
            elif fullscreen:
                self.saw_fullscreen = True
                if self.home_boundary:
                    self.home_boundary = False
                    return True
            return False


def state(monitor):
    # Installation/AV callbacks can race. Publish exactly one ledger per observer.
    with _BATCH_LOCK:
        found = getattr(monitor, '_smarted_openings', None)
        if found is None:
            found = Opening()
            monitor._smarted_openings = found
        return found


def observe(monitor, kodi, previous=(False, '', '')):
    """Passive fallback for native callbacks not delivered on cold bootstrap.

    Only video edges/path/channel changes or explicit Home return call the
    existing eligibility gate. Never issue play/seek/pause/menu commands here.
    Player.HasMedia keeps buffering/pause from being mistaken for a close.
    """
    if getattr(monitor, '_em_vast', False):
        return previous
    ledger = state(monitor)
    home = bool(kodi.getCondVisibility('Window.IsActive(home)'))
    full = bool(kodi.getCondVisibility('Window.IsActive(fullscreenvideo)'))
    playing = bool(monitor.isPlayingVideo())
    media = bool(kodi.getCondVisibility('Player.HasMedia'))
    path = (monitor._caminho() or '') if playing else ''
    channel = (kodi.getInfoLabel('VideoPlayer.ChannelName') or '') if playing else ''
    was_video, old_path, old_channel = previous
    live = False
    if was_video and not playing and not media:
        try:
            import ao_vivo
            live = bool(ao_vivo.eh_ao_vivo(old_path))
        except Exception:
            pass
    # Kodi can show Home automatically at a live EOF. That is not a user
    # navigation boundary; explicit Stop or Home while media is active still is.
    suppress_auto_home = live and not media and not playing and not ledger.closed
    home_return = ledger.observe_ui(home and not suppress_auto_home, full)
    if playing:
        edge = not was_video or path != old_path or channel != old_channel
        waiting = getattr(monitor, '_smarted_wait_for_video_boundary', False)
        if home_return or (edge and not waiting):
            emit(kodi, 'native-playback-observed', home_return=home_return)
            monitor._talvez_mostrar()
        return (True, path, channel)
    if media:
        return previous  # paused/buffering is not a new opening
    if was_video:
        # Live's existing reconnect helper may temporarily release media.
        # An explicit Stop closes it; EOF alone must not repeat ads.
        if not live and ledger.close():
            try:
                monitor._limpar_retomada()
            except Exception as exc:
                emit(kodi, 'close-cleanup-failed', error=type(exc).__name__)
            emit(kodi, 'opening-closed', boundary='observed-no-media')
    monitor._smarted_wait_for_video_boundary = False
    if suppress_auto_home:
        return previous  # retain live identity across every reconnect poll
    return (False, '', '')


def watch_home(monitor, kodi):
    """Abortable state observer; fallback eligibility, not a player watchdog."""
    with _BATCH_LOCK:
        if getattr(monitor, '_smarted_home_observer', False):
            return
        monitor._smarted_home_observer = True
    emit(kodi, 'state-observer-installed')
    def run():
        try:
            abort = kodi.Monitor()
            previous = (False, '', '')
            while not abort.abortRequested():
                previous = observe(monitor, kodi, previous)
                if abort.waitForAbort(.25):
                    break
        except Exception as exc:
            emit(kodi, 'home-observer-unavailable', error=type(exc).__name__)
    threading.Thread(target=run, name='smarted-opening-state-observer', daemon=True).start()


def current():
    return getattr(_LOCAL, 'opening', None)
