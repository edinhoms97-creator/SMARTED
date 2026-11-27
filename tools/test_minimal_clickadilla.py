#!/usr/bin/env python3
"""Minimal-profile tests. Optional actual APK source checks; never Android tests."""
import argparse
import ast
import json
import importlib.util
from pathlib import Path
import re
import ssl
import sys
import threading
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

import patch_minimal_clickadilla as minimal
from test_ads_regressions import Runtime

ORIGINAL = None
BASE_APK = None
sys.path.insert(0, str(minimal.FOLDER))


def definitions(path, env):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    env[target.id] = value
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and (path.name != 'smart_ads.py' or n.name == 'motor_anuncio')]
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), env)


def strip(xml):
    root = ET.fromstring(xml)
    for node in root.iter():
        node.tag = node.tag.rsplit('}', 1)[-1]
    return ET.tostring(root, encoding='unicode')


def wrapper(target, label='outer'):
    return ('<VAST><Ad><Wrapper><Impression>https://p.invalid/' + label + '</Impression>'
            '<Impression>https://p.invalid/duplicate</Impression><Error>https://p.invalid/error?e=[ERRORCODE]</Error>'
            '<VASTAdTagURI>' + target + '</VASTAdTagURI><Creatives><Creative><Linear>'
            '<TrackingEvents><Tracking event="start">https://p.invalid/start-' + label + '</Tracking>'
            '</TrackingEvents></Linear></Creative></Creatives></Wrapper></Ad></VAST>')

INLINE = ('<VAST><Ad><InLine><Impression>https://p.invalid/inline</Impression><Creatives><Creative>'
          '<Linear><Duration>00:00:15</Duration><MediaFiles><MediaFile type="video/mp4" delivery="progressive">'
          'https://m.invalid/ad.mp4</MediaFile></MediaFiles></Linear></Creative></Creatives></InLine></Ad></VAST>')


class Tests(unittest.TestCase):
    def env(self):
        runtime = Runtime()
        env = runtime.env()
        env.update(re=re, json=json, threading=threading, ssl=ssl)
        definitions((ORIGINAL or minimal.FOLDER) / 'ads_vast.py', env)
        env['PROFUNDIDADE_WRAPPER'] = 5
        env['sem_namespace'] = strip
        env['VAST_TAG_PADRAO'] = minimal.TAG
        env['tag_do_wrapper'] = lambda xml: ET.fromstring(strip(xml)).findtext('.//VASTAdTagURI') or ''
        env['tag_do_vmap'] = lambda xml: ''
        def choose(data, height=0):
            root = ET.fromstring(strip(data))
            if root.find('.//InLine') is None:
                return None
            return {'url': 'https://m.invalid/ad.mp4', 'duracao': 15,
                    'impressao': [n.text for n in root.iter('Impression')], 'eventos': {}, 'errors': []}
        env['escolher_anuncio'] = choose
        return runtime, env

    def test_exact_tag_and_vast_on_every_device(self):
        _, env = self.env()
        self.assertEqual(env['tag_configurada']('https://old.invalid'), minimal.TAG)
        definitions((ORIGINAL or minimal.FOLDER) / 'smart_ads.py', env)
        env['MOTOR_VAST'] = 'vast'
        for tv in (True, False):
            env['e_tv'] = lambda: tv
            self.assertEqual(env['motor_anuncio']()[0], 'vast')

    def test_wrapper_inheritance_preserves_duplicates_and_selected_branch(self):
        runtime, env = self.env()
        selected = []
        env['reproduzir'] = lambda ad, **kw: selected.append(ad) or {'exibido': True}
        pages = {'one': wrapper('two') + '', 'two': wrapper('three', 'inner'), 'three': INLINE}
        # Add a sibling Wrapper that must not contribute pixels.
        pages['one'] = pages['one'].replace('</VAST>', '<Ad><Wrapper><Impression>https://p.invalid/unselected</Impression><VASTAdTagURI>other</VASTAdTagURI></Wrapper></Ad></VAST>')
        result = env['exibir'](tag='one', baixar_tag=pages.get)
        self.assertTrue(result['exibido'])
        ad = selected[0]
        self.assertEqual(ad['impressao'].count('https://p.invalid/duplicate'), 2)
        self.assertEqual(len(ad['impressao']), 5)
        self.assertNotIn('https://p.invalid/unselected', ad['impressao'])
        self.assertEqual(len(ad['eventos']['start']), 2)
        self.assertEqual(runtime.events, [])  # parsing is not an impression

    def test_nofill_network_badxml_cycle_and_depth_never_impress(self):
        for mode, reason in (('empty', 'no-fill'), ('network', 'tag-sem-resposta'),
                             ('xml', 'xml-invalido'), ('cycle', 'wrapper-ciclico'), ('depth', 'wrapper-limite')):
            with self.subTest(mode=mode):
                runtime, env = self.env()
                env['PROFUNDIDADE_WRAPPER'] = 1 if mode == 'depth' else 5
                response = {'empty': '<VAST/>', 'network': None, 'xml': '<oops',
                            'cycle': wrapper('one'), 'depth': wrapper('three')}[mode]
                pages = {'one': wrapper('two'), 'two': response, 'three': INLINE}
                receipt = env['exibir'](tag='one', baixar_tag=pages.get)
                expected = 'vast-sem-criativo' if mode == 'empty' else reason
                self.assertEqual(receipt['motivo'], expected)
                self.assertFalse(receipt['exibido'])
                self.assertFalse(any('/duplicate' in event for event in runtime.events))
                self.assertTrue(any('/error?e=' in event for event in runtime.events))

    def test_pixels_expand_macros_and_use_real_ua_with_verified_tls(self):
        _, env = self.env()
        env['xbmc'].getUserAgent = lambda: 'Kodi/21 Android actual'
        calls = []
        class Response:
            def read(self): return b''
            def close(self): pass
        def open_url(request, **kw):
            calls.append((request, kw)); return Response()
        with patch('urllib.request.urlopen', side_effect=open_url):
            self.assertEqual(env['disparar'](['https://p.invalid/?c=[CACHEBUSTING]&e=[ERRORCODE]'.replace('[ERRORCODE]', '405')]), 1)
        request, kw = calls[0]
        self.assertEqual(request.get_header('User-agent'), 'Kodi/21 Android actual')
        self.assertRegex(request.full_url, r'c=\d{8}&e=405')
        self.assertTrue(kw['context'].check_hostname)
        self.assertGreaterEqual(kw['context'].minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_original_playback_tracking_not_request_or_synthetic_complete(self):
        if ORIGINAL is None:
            self.skipTest('Actual original player functions tested in APK runner')
        for mode in ('refused', 'stall', 'mid-stall', 'ended', 'stopped'):
            with self.subTest(mode=mode):
                runtime = Runtime(mode)
                env = runtime.env()
                definitions(ORIGINAL / 'ads_vast.py', env)
                # Retain actual patched function while stubbing native boundaries only.
                env.update(_agora=lambda: runtime.now, _arquivo_atual=lambda: runtime.file,
                           _player_tocando_video=lambda: runtime.playing,
                           _aguardar_anuncio_tocar=lambda *a, **kw: True,
                           _posicao_e_duracao=lambda: (runtime.position, 15),
                           _garantir_tela_cheia=lambda: None, _audio_sem_quadro_video=lambda: False,
                           _disparar_eventos=lambda urls: runtime.events.extend(urls))
                env['TEMPO_TRAVAMENTO_ANUNCIO'] = 3
                env['TEMPO_TELA_PRETA_AUDIO'] = 3
                env['FOLGA_FIM'] = 0
                env['QUARTIS'] = [('firstQuartile', .25), ('midpoint', .5), ('thirdQuartile', .75), ('complete', 1)]
                receipt = env['reproduzir']({'url': 'ad', 'duracao': 15, 'impressao': ['impression'],
                           'eventos': {e: [e] for e in ('start', 'complete', 'skip', 'firstQuartile', 'midpoint', 'thirdQuartile')}},
                           tocar=runtime.play_ad, dormir=runtime.sleep)
                if mode in ('refused', 'stall'):
                    self.assertNotIn('impression', runtime.events)
                else:
                    self.assertEqual(runtime.events.count('impression'), 1)
                self.assertEqual(runtime.events.count('complete'), 1 if mode == 'ended' else 0)
                self.assertEqual(runtime.resumes, [])
                if mode == 'stopped':
                    self.assertEqual(runtime.events.count('skip'), 1)
                if mode == 'refused':
                    self.assertFalse(receipt['exibido'])

    def test_actual_apk_monitor_resume_controls_and_frequency_unchanged(self):
        if BASE_APK is None:
            self.skipTest('Original APK comparison available in runner')
        with zipfile.ZipFile(BASE_APK) as archive:
            originals = {name: archive.read(minimal.BASE + name).decode() for name in ('ads_vast.py', 'smart_ads.py')}
            self.assertNotIn(minimal.BASE + 'ads_resume.py', archive.namelist())
        expected = minimal.patch_sources(originals)
        for name, code in expected.items():
            self.assertEqual((ORIGINAL / name).read_text(), code)
        original_node = next(n for n in ast.parse(originals['ads_vast.py']).body if isinstance(n, ast.FunctionDef) and n.name == 'reproduzir')
        new_node = next(n for n in ast.parse(expected['ads_vast.py']).body if isinstance(n, ast.FunctionDef) and n.name == 'reproduzir')
        self.assertEqual(minimal.native_control_calls(ast.unparse(original_node)), minimal.native_control_calls(ast.unparse(new_node)))
        self.assertEqual(set(expected), {'ads_vast.py', 'smart_ads.py', 'ads_tracking.py'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path)
    parser.add_argument('--base', type=Path)
    args, rest = parser.parse_known_args()
    ORIGINAL, BASE_APK = args.original, args.base
    if ORIGINAL:
        sys.path.insert(0, str(ORIGINAL))
    helper_spec = importlib.util.spec_from_file_location('ads_tracking', (ORIGINAL or minimal.FOLDER) / 'ads_tracking.py')
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    sys.modules['ads_tracking'] = helper
    result = unittest.main(argv=[__file__] + rest, exit=False).result
    for test, detail in result.failures + result.errors:
        print('::error title=Minimal Clickadilla regression::' + str(test) + ': ' + detail.strip().splitlines()[-1])
    raise SystemExit(0 if result.wasSuccessful() else 1)
