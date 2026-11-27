#!/usr/bin/env python3
"""3.5s startup, MP4 fallback and persistent redacted device diagnostics."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import socket
import test_vast_tracking as tracking
from test_ad_openings import Harness, NOFILL

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / 'android-build/ads-patches'
ORIGINAL = None
XML = ('<VAST><Ad><InLine><Impression>https://pixel.invalid/impression?[CACHEBUSTING]</Impression>'
       '<Creatives><Creative><Linear><Duration>00:00:21</Duration><MediaFiles>'
       '<MediaFile type="video/mp4" width="1280" height="720" bitrate="2000" codec="avc1.4d401f,mp4a.40.2">https://media.invalid/720.mp4</MediaFile>'
       '<MediaFile type="video/mp4" width="854" height="480" bitrate="900" codec="avc1.42e01e,mp4a.40.2">https://media.invalid/480.mp4</MediaFile>'
       '<MediaFile type="video/mp4" width="1920" height="1080" bitrate="6000">https://media.invalid/heavy.mp4</MediaFile>'
       '<MediaFile type="video/mp4" codec="hvc1">https://media.invalid/hevc.mp4</MediaFile>'
       '</MediaFiles></Linear></Creative></Creatives></InLine></Ad></VAST>')
WRAPPER = ('<VAST><Ad><Wrapper><Error>https://pixel.invalid/error?e=[ERRORCODE]</Error>'
           '<VASTAdTagURI>https://tag.invalid/inline</VASTAdTagURI></Wrapper></Ad></VAST>')


class Tests(unittest.TestCase):
    def setUp(self):
        tracking.ORIGINAL = ORIGINAL
        sys.path.insert(0, str(ORIGINAL or FOLDER))
        self.h = tracking.Tracking()
        self.env = self.h.env()
        self.rt = self.h.runtime
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.logfile = Path(self.tmp.name) / 'smarted_vast.log'
        self.patcher = patch.dict(sys.modules, {
            'xbmc': types.SimpleNamespace(log=lambda *args: None),
            'xbmcvfs': types.SimpleNamespace(translatePath=lambda _: str(self.logfile)),
        })
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def rows(self):
        return [json.loads(line) for line in self.logfile.read_text().splitlines()]

    def session(self, all_fail=False):
        attempts = []
        def play(url, log):
            attempts.append(url)
            self.rt.mode = 'stall' if len(attempts) == 1 or all_fail else 'ended'
            return self.rt.play_ad(url, log)
        pages = {'https://tag.invalid/wrapper': WRAPPER, 'https://tag.invalid/inline': XML}
        receipt = self.env['exibir_e_devolver'](tag='https://tag.invalid/wrapper',
                      baixar_tag=pages.get, tocar=play, dormir=self.rt.sleep)
        return receipt, attempts

    def test_720_startup_failure_tries_480_then_restores_exact_content_once(self):
        original_time = self.rt.position
        receipt, attempts = self.session()
        self.assertEqual(attempts, ['https://media.invalid/720.mp4', 'https://media.invalid/480.mp4'])
        self.assertTrue(receipt['iniciado'])
        self.assertTrue(receipt['retomada_confirmada'])
        self.assertEqual(receipt['media_attempts'], 2)
        self.assertEqual(self.rt.restores, ['https://media.invalid/movie.mp4'])
        self.assertIn(('https://media.invalid/movie.mp4', original_time), self.rt.seek_calls)
        self.assertAlmostEqual(self.rt.stop_times[0] - 1000, 3.5)
        self.assertEqual(sum('/impression?' in url for url in self.rt.events), 1)
        self.assertEqual(sum('/error?' in url for url in self.rt.events), 1)
        media_rows = [row for row in self.rows() if row['phase'] == 'media']
        self.assertEqual([row['altura'] for row in media_rows], [720, 480])
        self.assertEqual(media_rows[0]['status'], 'VAST MEDIA FAIL')
        self.assertTrue(self.rows()[-1]['status'].startswith('VAST OK'))

    def test_both_fail_in_7s_no_impression_and_content_return_is_immediate(self):
        receipt, attempts = self.session(all_fail=True)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(receipt['motivo'], 'startup-timeout')
        self.assertTrue(receipt['retomada_confirmada'])
        self.assertFalse(receipt['iniciado'])
        self.assertEqual(sum('/impression?' in url for url in self.rt.events), 0)
        self.assertEqual(sum('/error?' in url for url in self.rt.events), 2)
        self.assertAlmostEqual(self.rt.restore_times[0] - 1000, 7.0)
        self.assertEqual(self.rt.file, 'https://media.invalid/movie.mp4')

    def test_started_creative_is_not_retried_after_mid_ad_stall(self):
        attempts = []
        def play(url, log):
            attempts.append(url)
            self.rt.mode = 'mid-stall'
            return self.rt.play_ad(url, log)
        receipt = self.env['exibir_e_devolver'](tag='tag', baixar_tag=lambda _: XML,
                                               tocar=play, dormir=self.rt.sleep)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(receipt['motivo'], 'travamento')
        self.assertTrue(receipt['retomada_confirmada'])

    def test_no_compatible_file_is_media_fail_not_no_fill(self):
        xml = XML.replace('type="video/mp4"', 'type="video/webm"')
        receipt = self.env['exibir_e_devolver'](tag='tag', baixar_tag=lambda _: xml)
        self.assertEqual(receipt['motivo'], 'sem-midia-compativel')
        self.assertEqual(self.rows()[-1]['status'], 'VAST MEDIA FAIL')
        self.assertEqual(self.rt.stops, [])

    def test_startup_decoder_error_falls_back_but_late_old_error_cannot_kill_next_media(self):
        original_sleep = self.rt.sleep
        attempts = []
        def sleep(seconds):
            original_sleep(seconds)
            if len(attempts) == 1 and self.rt.file == self.rt.ad_path:
                self.rt.position = 0
                if self.rt.now - self.rt.start >= .5:
                    self.rt.observer.onPlayBackError()
        def play(url, log):
            attempts.append(url)
            if len(attempts) > 1:
                self.rt.file, self.rt.playing = '', False
                self.rt.observer.onPlayBackError()  # stale teardown, no owned new file
            return self.rt.play_ad(url, log)
        receipt = self.env['exibir_e_devolver'](tag='tag', baixar_tag=lambda _: XML,
                                               tocar=play, dormir=sleep)
        self.assertEqual(len(attempts), 2)
        self.assertTrue(receipt['retomada_confirmada'])
        self.assertTrue(receipt['iniciado'])

    def test_real_http_200_empty_is_logged_without_replacing_content(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return b''
        with patch('urllib.request.urlopen', return_value=Response()):
            receipt = self.env['exibir_e_devolver'](tag='https://tag.invalid/vast')
        self.assertEqual(receipt['http_status'], 200)
        self.assertEqual(self.rows()[-1]['status'], 'VAST NO-FILL (HTTP 200 vazio)')
        self.assertEqual(self.rt.stops, [])
        self.assertEqual(self.rt.restores, [])

    def test_http_failure_and_timeout_do_not_become_no_fill(self):
        for error, expected in ((URLError(socket.timeout()), 'VAST TIMEOUT'),
                                (HTTPError('https://private.invalid/?token=secret', 403, 'Forbidden', {}, None), 'VAST NETWORK FAIL')):
            with self.subTest(expected=expected), patch('urllib.request.urlopen', side_effect=error):
                self.env['exibir_e_devolver'](tag='https://tag.invalid/vast')
                self.assertEqual(self.rows()[-1]['status'], expected)
        self.assertNotIn('private.invalid', self.logfile.read_text())
        self.assertNotIn('secret', self.logfile.read_text())

    def test_diagnostic_is_bounded_redacted_and_can_log_monitor_and_gates(self):
        from ads_diagnostics import record
        self.logfile.write_text('x' * (128 * 1024))
        record('boot', {'active': True})
        record('gate', {'motivo': 'vip', 'url': 'https://secret.invalid/token', 'reason': 'secret'})
        self.assertTrue(Path(str(self.logfile) + '.1').exists())
        self.assertEqual(self.rows()[0]['status'], 'VAST MONITOR READY')
        self.assertEqual(self.rows()[-1]['status'], 'VAST SKIP')
        self.assertNotIn('secret', self.logfile.read_text())
        self.assertTrue(all(row['session'] for row in self.rows()))
        with patch('builtins.open', side_effect=PermissionError()):
            self.assertFalse(record('result', {'motivo': 'startup-timeout'}))

    def test_restart_does_not_inherit_failed_attempt_or_cooldown(self):
        import test_ad_openings as openings
        openings.ORIGINAL = ORIGINAL
        first = Harness([{'exibido': False, 'motivo': 'startup-timeout'}])
        first.open('same-film')
        restarted = Harness([NOFILL])
        restarted.state.update(first.state)
        restarted.open('same-film')
        restarted.repeat(new_session=True)
        self.assertEqual(restarted.calls, ['same-film'])
        self.assertTrue(any(row['phase'] == 'request' for row in self.rows()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path)
    args, rest = parser.parse_known_args()
    ORIGINAL = args.original
    result = unittest.main(argv=[__file__] + rest, exit=False).result
    for test, detail in result.failures + result.errors:
        print('::error title=VAST startup diagnostics regression::' + str(test) + ': ' + detail.strip().splitlines()[-1], flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
