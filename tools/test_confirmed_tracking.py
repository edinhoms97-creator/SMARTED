#!/usr/bin/env python3
"""Compare against user-confirmed 9436b5e. Fixtures only; no live ad requests."""
import argparse
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import restore_confirmed_tracking as restore

ORIGINAL = None
BASE_APK = None
sys.path.insert(0, str(restore.HELPER_SOURCE.parent))


def strip(xml):
    root = ET.fromstring(xml)
    for node in root.iter(): node.tag = node.tag.rsplit('}', 1)[-1]
    return ET.tostring(root, encoding='unicode')


class Tests(unittest.TestCase):
    def env(self):
        events, selected, calls = [], [], []
        def choose(data, height):
            root = ET.fromstring(strip(data))
            if root.find('.//InLine') is None: return None
            return {'url': 'ad', 'impressao': [n.text for n in root.iter('Impression')],
                    'eventos': {'start': ['inline-start']}, 'tipo': 'video/mp4', 'duracao': 25}
        def fetch(url, **kw):
            calls.append((url, kw)); return b''
        env = {'TIMEOUT_HTTP': 8, 'TEMPO_MAXIMO_ANUNCIO': 45, 'PROFUNDIDADE_WRAPPER': 2,
               '_agora': lambda: 1000, 'sem_namespace': strip, 'escolher_anuncio': choose,
               'tag_do_wrapper': lambda data: ET.fromstring(strip(data)).findtext('.//VASTAdTagURI') or '',
               'tag_do_vmap': lambda data: '', 'baixar': fetch,
               '_disparar_eventos': lambda urls: events.extend(urls),
               'reproduzir': lambda ad, **kw: selected.append(ad) or {'exibido': True},
               'xbmc': types.SimpleNamespace(getUserAgent=lambda: 'Kodi/21 Android actual')}
        exec(compile(restore.OVERLAY.read_text(), str(restore.OVERLAY), 'exec'), env)
        return env, events, selected, calls

    def test_player_and_all_nontracking_functions_unchanged(self):
        source = restore.historical('android-build/ads-patches/ads_vast.py')
        updated = restore.update_tracking(source)
        self.assertEqual(restore.player_without_error(source), restore.player_without_error(updated))
        old = {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
        new = {n.name: ast.get_source_segment(updated, n) for n in ast.parse(updated).body if isinstance(n, ast.FunctionDef)}
        for name in old.keys() - {'disparar', 'exibir', 'reproduzir'}:
            self.assertEqual(old[name], new[name], name)

    def test_pixel_transport_changes_no_tag_request_and_expands_macros(self):
        env, _, _, calls = self.env()
        requests = []
        class Response:
            def close(self): pass
        def open_url(request, **kw): requests.append((request, kw)); return Response()
        with patch('urllib.request.urlopen', side_effect=open_url):
            self.assertEqual(env['disparar'](['https://pixel.invalid/?c=[CACHEBUSTING]&u=[DEVICEUA]']), 1)
        self.assertEqual(calls, [])  # tag baixar is never monkeypatched/reconfigured
        request, kw = requests[0]
        self.assertEqual(request.get_header('User-agent'), 'Kodi/21 Android actual')
        self.assertNotIn('[', request.full_url)
        self.assertEqual(kw['timeout'], 6)
        self.assertTrue(kw['context'].check_hostname)

    def test_selected_wrapper_pixels_inherited_duplicates_not_discarded(self):
        env, events, selected, _ = self.env()
        wrapper = '<VAST><Ad><Wrapper><Impression>outer</Impression><Impression>duplicate</Impression><Impression>duplicate</Impression><VASTAdTagURI>inline</VASTAdTagURI><Creatives><Creative><Linear><TrackingEvents><Tracking event="start">outer-start</Tracking></TrackingEvents></Linear></Creative></Creatives></Wrapper></Ad><Ad><Wrapper><Impression>unselected</Impression><VASTAdTagURI>other</VASTAdTagURI></Wrapper></Ad></VAST>'
        inline = '<VAST><Ad><InLine><Impression>inner</Impression></InLine></Ad></VAST>'
        queries = []
        def fetch(url): queries.append(url); return {'tag': wrapper, 'inline': inline}[url]
        env['exibir'](tag='tag', baixar_tag=fetch)
        self.assertEqual(queries, ['tag', 'inline'])
        self.assertEqual(selected[0]['impressao'], ['outer', 'duplicate', 'duplicate', 'inner'])
        self.assertEqual(selected[0]['eventos']['start'], ['outer-start', 'inline-start'])
        self.assertEqual(events, [])  # resolution alone is not an impression

    def test_nofill_keeps_reference_receipt_without_starting_player(self):
        env, events, selected, _ = self.env()
        receipt = env['exibir'](tag=restore.TAG, baixar_tag=lambda url: '<VAST/>')
        self.assertEqual(receipt, {'exibido': False, 'motivo': 'no-fill-ou-sem-midia'})
        self.assertEqual(selected, [])
        self.assertEqual(events, [])

    def test_wrapper_error_has_expanded_code_but_no_impression(self):
        env, events, selected, _ = self.env()
        wrapper = '<VAST><Ad><Wrapper><Impression>must-not-fire</Impression><Error>https://pixel.invalid/?e=%5BERRORCODE%5D</Error><VASTAdTagURI>inline</VASTAdTagURI></Wrapper></Ad></VAST>'
        pages = {'tag': wrapper, 'inline': '<broken'}
        receipt = env['exibir'](tag='tag', baixar_tag=pages.get)
        self.assertEqual(receipt['motivo'], 'xml-invalido')
        self.assertEqual(events, ['https://pixel.invalid/?e=100'])
        self.assertEqual(selected, [])

    def test_generated_modules_match_exact_historical_payload_except_tracking(self):
        if not ORIGINAL or not BASE_APK: self.skipTest('Actual APK modules checked in runner')
        _, expected = restore.reference_payload(BASE_APK)
        for path, code in expected.items():
            actual = (ORIGINAL / Path(path).name).read_bytes()
            if path == restore.AD:
                self.assertEqual(actual.decode(), restore.update_tracking(code.decode()))
            else:
                self.assertEqual(actual, code, path)
        self.assertEqual((ORIGINAL / 'ads_tracking.py').read_bytes(), restore.HELPER_SOURCE.read_bytes())
        source = (ORIGINAL / 'ads_vast.py').read_text()
        tree = ast.parse(source)
        tag = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'VAST_TAG_PADRAO' for t in n.targets))
        self.assertEqual(tag, restore.TAG)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path)
    parser.add_argument('--base', type=Path)
    args, rest = parser.parse_known_args()
    ORIGINAL, BASE_APK = args.original, args.base
    if ORIGINAL: sys.path.insert(0, str(ORIGINAL))
    result = unittest.main(argv=[__file__] + rest, exit=False).result
    for test, detail in result.failures + result.errors:
        print('::error title=Confirmed reference tracking regression::' + str(test) + ': ' + detail.strip().splitlines()[-1])
    raise SystemExit(0 if result.wasSuccessful() else 1)
