#!/usr/bin/env python3
"""Deterministic media-fault regressions; no network/emulator or skin changes."""
import ast
from pathlib import Path
import types
import unittest

PATCHES = Path(__file__).resolve().parent.parent / 'android-build/ads-patches'


class Runtime:
    def __init__(self, mode='ended'):
        self.mode = mode
        self.now = 1000.0
        self.start = self.now
        self.file = 'movie'
        self.playing = True
        self.position = 42.125
        self.observer = None
        self.events = []
        self.stops = []
        self.seek_calls = []
        self.restores = []
        self.callback_sent = False
        runtime = self

        class Player:
            def __init__(self):
                if type(self) is not Player:
                    runtime.observer = self
            def isPlayingVideo(self):
                return runtime.playing
            def getPlayingFile(self):
                return runtime.file
            def getTime(self):
                return runtime.position
            def seekTime(self, value):
                runtime.seek_calls.append((runtime.file, value))
                runtime.position = value
            def pause(self):
                pass
            def stop(self):
                runtime.stops.append(runtime.file)
                runtime.playing = False
                runtime.file = ''
        self.Player = Player

    def sleep(self, seconds):
        self.now += seconds
        if self.file != 'ad':
            return
        elapsed = self.now - self.start
        self.position = 0 if self.mode == 'stall' else elapsed
        if self.mode == 'late-old-stop' and not self.callback_sent and elapsed >= .2:
            self.callback_sent = True
            self.observer.onPlayBackStopped()  # old stream callback, new ad still plays
        if self.mode == 'error' and elapsed >= .6:
            self.playing = False
            self.observer.onPlayBackError()
        elif self.mode == 'stopped' and elapsed >= .6:
            self.playing = False
            self.observer.onPlayBackStopped()
        elif self.mode in ('ended', 'late-old-stop', 'old-error') and elapsed >= 15:
            self.playing = False
            self.observer.onPlayBackEnded()

    def play_ad(self, url, log):
        if self.mode == 'refused':
            return False
        if self.mode == 'old-error':
            self.observer.onPlayBackError()  # teardown of old content, before ad ownership
        self.file, self.playing, self.position, self.start = 'ad', True, 0, self.now
        return True

    def restore_route(self, route, **kwargs):
        self.restores.append(route)
        self.file, self.playing, self.position = route, True, 0
        return True

    def env(self):
        env = {
            '__name__': 'ad_regression', 'TIMEOUT_HTTP': 8, 'TEMPO_MAXIMO_ANUNCIO': 60,
            'TEMPO_TELA_PRETA_AUDIO': 3, 'TEMPO_TRAVAMENTO_ANUNCIO': 2,
            'VAST_TAG_PADRAO': 'https://vast.yomeno.xyz/vast?spot_id=1508180',
            'time': types.SimpleNamespace(time=lambda: self.now, sleep=self.sleep),
            'xbmc': types.SimpleNamespace(Player=self.Player, LOGWARNING=2, getCondVisibility=lambda _: False),
            '_agora': lambda: self.now, '_arquivo_atual': lambda: self.file,
            '_player_tocando_video': lambda: self.playing,
            '_aguardar_anuncio_tocar': lambda *a, **k: True,
            '_posicao_e_duracao': lambda: (self.position, 15),
            '_garantir_tela_cheia': lambda: None, '_audio_sem_quadro_video': lambda: False,
            '_desligar_surface_tela_preta': lambda **k: self.Player().stop(),
            '_disparar_eventos': lambda urls: self.events.extend(urls),
            '_candidatos_restauracao': lambda state: [state['caminho']],
            '_iniciar_em_tela_cheia': self.restore_route,
            '_smarted_restaurar_original': lambda *a, **k: True,
        }
        source = ast.parse((PATCHES / 'ads_vast.py').read_text())
        functions = ast.Module(body=[node for node in source.body if isinstance(node, ast.FunctionDef)], type_ignores=[])
        exec(compile(functions, str(PATCHES / 'ads_vast.py'), 'exec'), env)
        return env

    def play(self):
        env = self.env()
        ad = {'url': 'ad', 'duracao': 15, 'impressao': ['impression'], 'errors': ['error:[ERRORCODE]'],
              'eventos': {ev: [ev] for ev in ('start', 'firstQuartile', 'midpoint', 'thirdQuartile', 'complete', 'skip')}}
        return env['reproduzir'](ad, tocar=self.play_ad, dormir=self.sleep), env


class Regressions(unittest.TestCase):
    def test_stall_must_not_consume_frequency_or_leave_ad_running(self):
        runtime = Runtime('stall')
        receipt, _ = runtime.play()
        self.assertFalse(receipt['exibido'])
        self.assertNotIn('complete', runtime.events)
        self.assertNotIn('impression', runtime.events)
        self.assertLess(runtime.now - runtime.start, 10)
        self.assertIn('ad', runtime.stops)

    def test_decoder_error_must_not_consume_frequency(self):
        runtime = Runtime('error')
        receipt, _ = runtime.play()
        self.assertFalse(receipt['exibido'])
        self.assertIn('error:405', runtime.events)
        self.assertNotIn('complete', runtime.events)

    def test_old_stream_error_is_not_ad_failure(self):
        runtime = Runtime('old-error')
        receipt, _ = runtime.play()
        self.assertEqual(receipt['motivo'], 'concluido')
        self.assertEqual(runtime.events.count('complete'), 1)

    def test_delayed_old_stop_does_not_skip_current_ad(self):
        runtime = Runtime('late-old-stop')
        receipt, _ = runtime.play()
        self.assertEqual(receipt['motivo'], 'concluido')
        self.assertNotIn('skip', runtime.events)

    def test_refused_ad_must_not_restart_or_stop_still_playing_movie(self):
        runtime = Runtime('refused')
        receipt, _ = runtime.play()
        self.assertFalse(receipt['exibido'])
        self.assertFalse(receipt.get('precisa_restaurar', False))
        self.assertEqual(runtime.file, 'movie')
        self.assertEqual(runtime.stops, [])

    def test_15s_ad_completes_once(self):
        runtime = Runtime()
        receipt, _ = runtime.play()
        self.assertTrue(receipt['exibido'])
        for event in ('impression', 'start', 'firstQuartile', 'midpoint', 'thirdQuartile', 'complete'):
            self.assertEqual(runtime.events.count(event), 1, event)

    def test_player_exception_still_returns_fallback_receipt(self):
        runtime = Runtime()
        env = runtime.env()
        def broken(*a, **k):
            raise RuntimeError('decoder setup failed')
        receipt = env['reproduzir']({'url': 'ad'}, tocar=broken)
        self.assertFalse(receipt['exibido'])
        self.assertFalse(receipt.get('precisa_restaurar', False))
        self.assertEqual(runtime.file, 'movie')

    def test_exception_after_player_replacement_restores_vod(self):
        runtime = Runtime()
        env = runtime.env()
        env['estado_do_conteudo'] = lambda **kw: {'caminho': 'movie', 'posicao': 42.125}
        def broken(**kw):
            runtime.file, runtime.playing = 'ad', False
            raise RuntimeError('media callback failure')
        env['exibir'] = broken
        receipt = env['exibir_e_devolver']()
        self.assertFalse(receipt['exibido'])
        self.assertTrue(receipt['retomada_confirmada'])
        self.assertEqual(runtime.file, 'movie')
        self.assertEqual(runtime.position, 42.125)

    def test_restore_never_seeks_the_ad(self):
        runtime = Runtime()
        env = runtime.env()
        runtime.file, runtime.playing = 'ad', True
        env['_iniciar_em_tela_cheia'] = lambda *a, **k: True  # asynchronous command not accepted yet
        result = env['restaurar']({'caminho': 'movie', 'posicao': 42.125}, dormir=runtime.sleep,
                                 agora=lambda: runtime.now, espera=1, url_anuncio='ad')
        self.assertFalse(result)
        self.assertEqual(runtime.seek_calls, [])


if __name__ == '__main__':
    unittest.main()
