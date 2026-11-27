# -*- coding: utf-8 -*-
"""Kodi adapter: verified VAST playback, beacons and VOD seek confirmation.

run_session() is blocking: invoke on a worker, not Kodi's UI thread.
If there is no current content, on_fallback is the principal addon's
hook to start its selected channel (no channel endpoint is invented here).
"""
import threading
import time

import xbmc
import vast


class AdPlayer(xbmc.Player):
    def __init__(self):
        super(AdPlayer, self).__init__()
        self.ready = threading.Event()
        self.finished = threading.Event()
        self.outcome = None

    def onAVStarted(self):
        self.ready.set()

    def onPlayBackEnded(self):
        if not self.ready.is_set():
            return
        self.outcome = "completed"
        self.finished.set()

    def onPlayBackStopped(self):
        if not self.ready.is_set():
            return
        self.outcome = "skipped"
        self.finished.set()

    def onPlayBackError(self):
        self.outcome = "error"
        self.finished.set()


def _snapshot(player):
    if not player.isPlayingVideo():
        return None
    # Preserve the resolved URL AND ListItem (MIME/properties/headers).
    return {"url": player.getPlayingFile(), "item": player.getPlayingItem(),
            "time": player.getTime(),
            "paused": xbmc.getCondVisibility("Player.Paused")}


def _restore(snapshot, monitor):
    if snapshot is None:
        return {"resumeConfirmed": False, "resumeReason": "no-current-content"}
    player = AdPlayer()
    player.play(snapshot["url"], snapshot["item"])
    deadline = time.monotonic() + 12
    while not player.ready.is_set():
        if player.finished.is_set() or time.monotonic() >= deadline or monitor.waitForAbort(0.05):
            return {"resumeConfirmed": False, "resumeReason": "content-start-failed"}
    # Live streams may not be seekable. Report an unconfirmed resume
    # rather than claiming exact VOD restoration for these streams.
    try:
        player.seekTime(snapshot["time"])
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            position = player.getTime()
            if abs(position - snapshot["time"]) <= 0.25:
                if snapshot["paused"]:
                    player.pause()
                return {"resumeConfirmed": True, "resumedAt": position,
                        "resumeTarget": snapshot["time"]}
            if monitor.waitForAbort(0.05):
                break
    except Exception:
        pass
    return {"resumeConfirmed": False, "resumeReason": "seek-not-confirmed"}


def run_session(on_fallback=None):
    monitor = xbmc.Monitor()
    main_player = xbmc.Player()
    # A failed snapshot must not replace content we cannot restore.
    try:
        snapshot = _snapshot(main_player)
    except Exception:
        return {"outcome": "error", "reason": "content-snapshot-failed"}
    if snapshot and not snapshot["paused"]:
        main_player.pause()
    replaced = False
    ad = None
    result = {"outcome": "error"}
    try:
        result = vast.play_preroll_or_fallback()
        if result["outcome"] == "ad":
            ad = result.pop("ad")
            player = AdPlayer()
            replaced = True
            player.play(ad["media_file"]["url"])
            fired = set()
            started = False
            last_pos = None
            progress_at = time.monotonic()
            while not monitor.abortRequested():
                if player.finished.is_set():
                    result["outcome"] = player.outcome
                    break
                if player.ready.is_set() and player.isPlayingVideo():
                    if not started:
                        started = True
                        vast.fire_all(ad["impressions"])
                        vast.fire_all(ad["tracking"].get("start"))
                    pos = player.getTime()
                    if pos != last_pos:
                        last_pos, progress_at = pos, time.monotonic()
                    total = player.getTotalTime() or ad.get("duration") or 0
                    for event, fraction in (("firstQuartile", .25), ("midpoint", .5),
                                            ("thirdQuartile", .75)):
                        if total and pos / total >= fraction and event not in fired:
                            fired.add(event)
                            vast.fire_all(ad["tracking"].get(event))
                if time.monotonic() - progress_at >= 12:
                    result.update(outcome="error", reason="creative-stall")
                    break
                if monitor.waitForAbort(.1):
                    break
            if result["outcome"] == "ad":
                result.update(outcome="error", reason="aborted")
            if result["outcome"] == "completed" and started:
                for event in ("firstQuartile", "midpoint", "thirdQuartile"):
                    if event not in fired:
                        vast.fire_all(ad["tracking"].get(event))
                vast.fire_all(ad["tracking"].get("complete"))
            elif result["outcome"] == "skipped":
                vast.fire_all(ad["tracking"].get("skip"))
            else:
                vast.fire_all(ad["tracking"].get("error"), error_code=405)
            if not player.finished.is_set():
                player.stop()
    except Exception as exc:
        if ad:
            vast.fire_all(ad["tracking"].get("error"), error_code=405)
        result = {"outcome": "error", "reason": str(exc)}
    finally:
        try:
            if replaced and snapshot and not monitor.abortRequested():
                result.update(_restore(snapshot, monitor))
            elif snapshot and not snapshot["paused"]:
                main_player.pause()  # no-fill: untouched source, simply unpause
                result.update(resumedAt=snapshot["time"], resumeConfirmed=True)
            elif snapshot:
                result.update(resumedAt=snapshot["time"], resumeConfirmed=True)
            elif on_fallback and not monitor.abortRequested():
                on_fallback()
        except Exception as exc:
            result.update(resumeConfirmed=False, resumeReason=str(exc))
    return result
