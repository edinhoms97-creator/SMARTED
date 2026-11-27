#!/usr/bin/env python3
"""Execute original patched ad FUNCTIONS with media/network stubs, never Kodi boot.

Run in CI against the source extracted from the pinned original and patched
by patch_original_ads.py. No original source/settings are uploaded to Git.
"""
import ast
import json
from pathlib import Path
import re
import ssl
import sys
import time
import types
import unittest
from unittest.mock import patch


class Player:
    current = 42.125
    seek_works = True
    observer = None

    def __init__(self):
        if type(self) is not Player:
            Player.observer = self

    def isPlayingVideo(self):
        return True

    def getPlayingFile(self):
        return 'original-vod'

    def seekTime(self, value):
        if self.seek_works:
            Player.current = value

    def getTime(self):
        return Player.current

    def pause(self):
        pass


def load_functions(path):
    code = ast.parse(Path(path).read_text())
    env = {'__name__': 'original_ads_test', 'time': time, 're': re, 'json': json,
           'xbmc': types.SimpleNamespace(Player=Player, LOGWARNING=2,
                                          getCondVisibility=lambda value: False,
                                          getInfoLabel=lambda value: '')}
    for node in code.body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    env[target.id] = value
    functions = ast.Module(body=[node for node in code.body if isinstance(node, ast.FunctionDef)
                               and (Path(path).name != "smart_ads.py" or node.name == "motor_anuncio")], type_ignores=[])
    exec(compile(functions, str(path), 'exec'), env)
    return env


class Tests(unittest.TestCase):
    folder = None

    def setUp(self):
        self.env = load_functions(self.folder / 'ads_vast.py')
        Player.seek_works = True
        Player.current = 42.125
        self.env['_smarted_restaurar_original'] = lambda *args, **kw: True
        self.env['_garantir_tela_cheia'] = lambda: None
        self.env['_audio_sem_quadro_video'] = lambda: False
        self.env['_arquivo_atual'] = lambda: 'original-vod'
        self.env['_player_tocando_video'] = lambda: True
        self.env['_aguardar_anuncio_tocar'] = lambda *a, **k: True
        self.env['_posicao_e_duracao'] = lambda: (0, 30)
        self.events = []
        self.env['_disparar_eventos'] = lambda urls: self.events.extend(urls)

    def test_exact_tag(self):
        self.assertEqual(self.env['tag_configurada']('https://wrong.invalid'), 'https://vast.yomeno.xyz/vast?spot_id=1508180')
        self.assertEqual(self.env['TIMEOUT_HTTP'], 8)

    def test_mobile_tv_projector_all_choose_vast(self):
        env = load_functions(self.folder / 'smart_ads.py')
        for device in ('mobile', 'tv', 'projetor'):
            env['e_tv'] = lambda: device == 'tv'
            self.assertEqual(env['motor_anuncio']()[0], 'vast')

    def test_admob_is_inert(self):
        tree = ast.parse((self.folder / 'ads_admob.py').read_text())
        self.assertFalse(any(isinstance(node, ast.Import) for node in tree.body))
        env = {}
        exec(compile(tree, 'ads_admob.py', 'exec'), env)
        self.assertFalse(env['enabled']())
        self.assertEqual(env['APP_ID'], 'ca-app-pub-2066014755407744~5076693043')

    def test_tls_verified_and_android_headers(self):
        class Response:
            def __enter__(self):
                self.parts = [b'<VAST/>', b'']
                return self
            def __exit__(self, *args):
                pass
            def read(self, size):
                return self.parts.pop(0)
        seen = {}
        def open_url(req, **kwargs):
            seen.update(kwargs)
            seen['ua'] = req.get_header('User-agent')
            return Response()
        with patch('urllib.request.urlopen', side_effect=open_url):
            self.assertEqual(self.env['baixar']('https://test.invalid'), b'<VAST/>')
        self.assertTrue(seen['context'].check_hostname)
        self.assertEqual(seen['context'].verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(seen['context'].minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertIn('Mobile Safari', seen['ua'])
        self.assertLessEqual(seen['timeout'], 8)

    def test_network_failure_returns_none(self):
        with patch('urllib.request.urlopen', side_effect=TimeoutError()):
            self.assertIsNone(self.env['baixar']('https://test.invalid'))

    def test_original_nofill_parser_and_flow_do_not_touch_content(self):
        self.env['estado_do_conteudo'] = lambda **kw: {'caminho': 'original-vod', 'posicao': 42.125}
        self.env['restaurar'] = lambda *a, **k: self.fail('No-fill must not restart the VOD')
        for xml in (b'', b'<VAST/>', b'<VAST><Error>303</Error></VAST>', b'<VAST><broken'):
            receipt = self.env['exibir_e_devolver'](tag='https://test.invalid', baixar_tag=lambda url: xml)
            self.assertFalse(receipt['exibido'])
            self.assertEqual(self.events, [])

    def test_resume_must_be_confirmed(self):
        Player.current = 0
        self.assertTrue(self.env['restaurar']({'caminho': 'vod', 'posicao': 42.125}, dormir=lambda t: None))
        self.assertEqual(Player.current, 42.125)
        Player.current = 0
        Player.seek_works = False
        self.assertFalse(self.env['restaurar']({'caminho': 'vod', 'posicao': 42.125}, dormir=lambda t: None))

    def playback(self, outcome):
        clock = [0]
        self.env['_agora'] = lambda: clock[0]
        self.env['_posicao_e_duracao'] = lambda: (clock[0] * 30, 30)
        def sleep(seconds):
            clock[0] += seconds
            if clock[0] >= 1:
                observer = Player.observer
                if outcome == 'ended':
                    observer.onPlayBackEnded()
                elif outcome == 'stopped':
                    observer.onPlayBackStopped()
                else:
                    observer.onPlayBackError()
        ad = {'url': 'ad', 'duracao': 30, 'impressao': ['impression'],
              'errors': ['error:[ERRORCODE]'],
              'eventos': {name: [name] for name in ('start', 'firstQuartile', 'midpoint', 'thirdQuartile', 'complete', 'skip')}}
        return self.env['reproduzir'](ad, tocar=lambda *args: True, dormir=sleep)

    def test_completed_tracking_once(self):
        receipt = self.playback('ended')
        self.assertEqual(receipt['motivo'], 'concluido')
        for name in ('impression', 'start', 'firstQuartile', 'midpoint', 'thirdQuartile', 'complete'):
            self.assertEqual(self.events.count(name), 1)

    def test_stop_never_fires_complete(self):
        self.assertEqual(self.playback('stopped')['motivo'], 'pulado')
        self.assertNotIn('complete', self.events)
        self.assertIn('skip', self.events)

    def test_error_never_fires_complete(self):
        self.playback('failed')
        self.assertNotIn('complete', self.events)
        self.assertIn('error:405', self.events)

    def test_no_impression_when_player_refuses(self):
        self.env['reproduzir']({'url': 'ad', 'impressao': ['impression'], 'errors': []}, tocar=lambda *args: False)
        self.assertNotIn('impression', self.events)


if __name__ == '__main__':
    Tests.folder = Path(sys.argv.pop(1))
    result = unittest.main(exit=False).result
    for test, detail in result.failures + result.errors:
        last = detail.strip().splitlines()[-1].replace('%', '%25')
        print('::error title=Original ad regression::' + str(test) + ': ' + last, flush=True)
    sys.exit(0 if result.wasSuccessful() else 1)
