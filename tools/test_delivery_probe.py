#!/usr/bin/env python3
"""Probe diagnostics only, intercepted HTTP/FFmpeg; sends no real ad requests."""
import sys
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import probe_ad_delivery as probe


class Tests(unittest.TestCase):
    def parser(self, ad=None):
        return {'escolher_anuncio': lambda xml, height: ad,
                'tag_do_wrapper': lambda xml: '', 'tag_do_vmap': lambda xml: ''}

    def response(self, data):
        class Response:
            status = 200
            url = 'https://test.invalid/vast?secret=not-logged'
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return data
        return Response()

    def test_empty_vast_does_not_reach_decode_or_tracking_and_is_not_retried(self):
        with patch.object(probe, 'urlopen', return_value=self.response(b'<VAST/>')) as get, \
                patch.object(probe, 'decode_media') as decode:
            result = probe.probe('fixture', 'https://test.invalid/vast?secret=not-logged', self.parser())
        self.assertEqual(get.call_count, 1)
        decode.assert_not_called()
        self.assertEqual(result['status'], 'no-linear-creative')
        self.assertEqual(result['requests'][0]['ads'], 0)
        self.assertEqual(result['requests'][0]['bytes'], 7)
        self.assertFalse(result['tracking_fired'])
        self.assertNotIn('not-logged', str(result))

    def test_media_rejected_is_distinguished_from_absence_of_media(self):
        data = b'<VAST><Ad><InLine><MediaFile type="video/webm">https://test.invalid/x</MediaFile></InLine></Ad></VAST>'
        with patch.object(probe, 'urlopen', return_value=self.response(data)):
            result = probe.probe('fixture', 'https://test.invalid/vast', self.parser())
        self.assertEqual(result['status'], 'media-rejected-by-base-selector')
        self.assertEqual(result['media_types'], ['video/webm'])

    def test_decoder_progress_is_not_reported_as_android_display(self):
        process = types.SimpleNamespace(returncode=0,
            stdout='frame=375\nout_time_us=15000000\nprogress=end\n',
            stderr='Duration: 00:00:15.00\nVideo: h264\nAudio: aac\n')
        with patch.object(probe, 'ffmpeg_executable', return_value='ffmpeg'), \
                patch.object(probe.subprocess, 'run', return_value=process):
            result = probe.decode_media('https://test.invalid/ad.mp4', 15)
        self.assertEqual(result['status'], 'cpu-decoded-to-end')
        self.assertEqual(result['frames'], 375)
        self.assertTrue(result['audio_stream_present'])
        self.assertFalse(result['android_validated'])

    def test_failed_or_incomplete_decode_cannot_be_success(self):
        for returncode, seconds in ((1, 15), (0, 2)):
            process = types.SimpleNamespace(returncode=returncode,
                stdout='frame=50\nout_time_us=%d\nprogress=end\n' % (seconds * 1000000),
                stderr='Duration: 00:00:15.00\nVideo: h264\n')
            with patch.object(probe, 'ffmpeg_executable', return_value='ffmpeg'), \
                    patch.object(probe.subprocess, 'run', return_value=process):
                result = probe.decode_media('https://test.invalid/ad.mp4', 15)
            self.assertEqual(result['status'], 'decode-incomplete-or-failed')

    def test_original_tag_is_read_verbatim_without_domain_substitution(self):
        tag = 'https://original.invalid/vast?spot_id=123&c=[CACHEBUSTING]'
        self.assertEqual(probe.original_tag('VAST_TAG_PADRAO = ' + repr(tag)), tag)
        with self.assertRaises(ValueError):
            probe.original_tag("VAST_TAG_PADRAO = 'file:///private'")


if __name__ == '__main__':
    unittest.main()
