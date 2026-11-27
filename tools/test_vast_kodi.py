#!/usr/bin/env python3
"""Kodi adapter unit tests using a fake xbmc player/clock (no Kodi install)."""
import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kodi-addon", "script.smartedtv.welcome"))
import vast


class Runtime:
    def __init__(self, mode="completed"):
        self.mode = mode
        self.clock = 0
        self.current = "vod"
        self.paused = False
        self.pos = 42.125
        self.player = None
        self.plays = []

    def wait(self, seconds):
        self.clock += seconds
        if self.current == "ad" and self.mode != "stall":
            self.pos += seconds * 100
            if self.pos >= 30:
                if self.mode == "completed":
                    self.player.onPlayBackEnded()
                else:
                    self.player.onPlayBackStopped()
        return False

    def module(self):
        rt = self

        class Player:
            def isPlayingVideo(self):
                return True

            def getPlayingFile(self):
                return "vod"

            def getPlayingItem(self):
                return "preserved-listitem"

            def getTime(self):
                return rt.pos

            def getTotalTime(self):
                return 30

            def pause(self):
                rt.paused = not rt.paused

            def play(self, url, item=None):
                rt.plays.append((url, item))
                rt.current = url
                rt.pos = 0
                rt.paused = False
                rt.player = self
                self.onAVStarted()

            def stop(self):
                self.onPlayBackStopped()

            def seekTime(self, pos):
                if rt.mode != "seek-fail":
                    rt.pos = pos

        return types.SimpleNamespace(
            Player=Player,
            Monitor=lambda: types.SimpleNamespace(abortRequested=lambda: False, waitForAbort=rt.wait),
            getCondVisibility=lambda name: rt.paused,
        )


class Tests(unittest.TestCase):
    def run_case(self, mode="completed", nofill=False):
        rt = Runtime(mode)
        ad = {"media_file": {"url": "ad"}, "duration": 30, "impressions": ["impression"],
              "tracking": {ev: [ev] for ev in ["start", "firstQuartile", "midpoint", "thirdQuartile", "complete", "skip", "error"]}}
        selection = {"outcome": "nofill"} if nofill else {"outcome": "ad", "ad": ad}
        events = []
        with patch.dict(sys.modules, {"xbmc": rt.module()}):
            sys.modules.pop("vast_player", None)
            adapter = importlib.import_module("vast_player")
            with patch.object(vast, "play_preroll_or_fallback", return_value=selection), \
                 patch.object(vast, "fire_all", side_effect=lambda urls, **kw: events.extend(urls or [])), \
                 patch.object(adapter.time, "monotonic", side_effect=lambda: rt.clock):
                result = adapter.run_session()
        return rt, result, events

    def test_completion_restores_url_item_and_position(self):
        rt, result, events = self.run_case()
        self.assertEqual(result["outcome"], "completed")
        self.assertTrue(result["resumeConfirmed"])
        self.assertEqual(result["resumedAt"], 42.125)
        self.assertEqual(rt.plays[-1], ("vod", "preserved-listitem"))
        for event in ["impression", "start", "firstQuartile", "midpoint", "thirdQuartile", "complete"]:
            self.assertEqual(events.count(event), 1, event)

    def test_nofill_does_not_replace_source(self):
        rt, result, events = self.run_case(nofill=True)
        self.assertEqual(result["outcome"], "nofill")
        self.assertFalse(rt.paused)
        self.assertEqual(rt.plays, [])
        self.assertEqual(events, [])

    def test_stop_never_reports_complete(self):
        _, result, events = self.run_case("stopped")
        self.assertEqual(result["outcome"], "skipped")
        self.assertNotIn("complete", events)
        self.assertTrue(result["resumeConfirmed"])

    def test_stall_has_bounded_fallback(self):
        rt, result, events = self.run_case("stall")
        self.assertEqual(result["outcome"], "error")
        self.assertIn("error", events)
        self.assertNotIn("complete", events)
        self.assertLess(rt.clock, 16)
        self.assertTrue(result["resumeConfirmed"])

    def test_seek_failure_is_not_confirmed(self):
        _, result, _ = self.run_case("seek-fail")
        self.assertFalse(result["resumeConfirmed"])
        self.assertEqual(result["resumeReason"], "seek-not-confirmed")

    def test_tls_is_verified_and_minimum_12(self):
        import ssl
        context = vast._tls_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)


if __name__ == "__main__":
    unittest.main()
