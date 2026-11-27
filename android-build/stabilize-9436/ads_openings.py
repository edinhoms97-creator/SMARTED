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
            if self.closed or not same:
                self.generation += 1
                self.aliases, self.channel = {path}, channel
                self.attempted, self.closed = False, False
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
            if self.in_ad:
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


def watch_home(monitor, kodi):
    """Observe navigation only, using Kodi's abortable wait; no UI/player commands."""
    with _BATCH_LOCK:
        if getattr(monitor, '_smarted_home_observer', False):
            return
        monitor._smarted_home_observer = True
    def run():
        try:
            abort = kodi.Monitor()
            while not abort.abortRequested():
                if not getattr(monitor, '_em_vast', False):
                    home = bool(kodi.getCondVisibility('Window.IsActive(home)'))
                    full = bool(kodi.getCondVisibility('Window.IsActive(fullscreenvideo)'))
                    if state(monitor).observe_ui(home, full):
                        emit(kodi, 'home-return')
                        monitor._talvez_mostrar()
                if abort.waitForAbort(.25):
                    break
        except Exception as exc:
            emit(kodi, 'home-observer-unavailable', error=type(exc).__name__)
    threading.Thread(target=run, name='smarted-opening-home-observer', daemon=True).start()


def current():
    return getattr(_LOCAL, 'opening', None)
