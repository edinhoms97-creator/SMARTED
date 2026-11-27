#!/usr/bin/env python3
"""Deterministic media-fault regressions; no network/emulator or skin changes."""
import ast
import sys
from pathlib import Path
import types
import unittest

ORIGINAL = None

PATCHES = Path(__file__).resolve().parent.parent / 'android-build/ads-patches'


class Runtime:
    def __init__(self, mode='ended'):
        self.mode = mode
        self.now = 1000.0
        self.duration = 21
        self.start = self.now
        self.file = 'https://media.invalid/movie.mp4'
        self.playing = True
        self.position = 42.125
        self.observer = None
        self.events = []
        self.stops = []
        self.stop_times = []
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
            def play(self, url, listitem=None, windowed=False):
                runtime.restore_route(url)
                if runtime.observer and hasattr(runtime.observer, 'onAVStarted'):
                    runtime.observer.onAVStarted()
            def seekTime(self, value):
                runtime.seek_calls.append((runtime.file, value))
                runtime.position = value
            def pause(self):
                pass
            def stop(self):
                runtime.stops.append(runtime.file)
                runtime.stop_times.append(runtime.now)
                runtime.playing = False
                runtime.file = ''
        self.Player = Player

    def sleep(self, seconds):
        self.now += seconds
        if self.file != 'ad':
            if self.playing:
                self.position += seconds
            return
        elapsed = self.now - self.start
        self.position = (0 if self.mode == 'stall' else
                         min(elapsed, 5.0) if self.mode == 'mid-stall' else
                         elapsed / 2 if self.mode == 'slow-clock' else elapsed)
        if self.mode == 'error-playing' and elapsed >= 5:
            self.observer.onPlayBackError()  # Kodi may still report playing!
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
        sys.path.insert(0, str(ORIGINAL or PATCHES))
        env = {
            '__name__': 'ad_regression', 'TIMEOUT_HTTP': 8, 'TEMPO_MAXIMO_ANUNCIO': 60,
            'TEMPO_TELA_PRETA_AUDIO': 3, 'TEMPO_TRAVAMENTO_ANUNCIO': 2,
            'VAST_TAG_PADRAO': 'https://vast.yomeno.xyz/vast?spot_id=1508180',
            'time': types.SimpleNamespace(time=lambda: self.now, sleep=self.sleep),
            'xbmc': types.SimpleNamespace(Player=self.Player, LOGWARNING=2, getCondVisibility=lambda _: False),
            '_smarted_estado_do_conteudo_original': lambda **kw: {'caminho': self.file, 'posicao': self.position, 'ao_vivo': False},
            '_agora': lambda: self.now, '_arquivo_atual': lambda: self.file,
            '_player_tocando_video': lambda: self.playing,
            '_aguardar_anuncio_tocar': lambda *a, **k: True,
            '_posicao_e_duracao': lambda: (self.position, self.duration),
            '_garantir_tela_cheia': lambda: None, '_audio_sem_quadro_video': lambda: False,
            '_desligar_surface_tela_preta': lambda **k: self.Player().stop(),
            '_disparar_eventos': lambda urls: self.events.extend(urls),
            '_candidatos_restauracao': lambda state: [state['caminho']],
            '_iniciar_em_tela_cheia': self.restore_route,
            '_smarted_restaurar_original': lambda *a, **k: True,
        }
        patch_source = ast.parse((PATCHES / 'ads_vast.py').read_text())
        names = {node.name for node in patch_source.body if isinstance(node, ast.FunctionDef)}
        source = ast.parse((ORIGINAL / 'ads_vast.py').read_text()) if ORIGINAL else patch_source
        functions = ast.Module(body=[node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
        exec(compile(functions, str(PATCHES / 'ads_vast.py'), 'exec'), env)
        return env

    def play(self):
        env = self.env()
        ad = {'url': 'ad', 'duracao': 15, 'impressao': ['impression'], 'errors': ['error:[ERRORCODE]'],
              'eventos': {ev: [ev] for ev in ('start', 'firstQuartile', 'midpoint', 'thirdQuartile', 'complete', 'skip')}}
        return env['reproduzir'](ad, tocar=self.play_ad, dormir=self.sleep), env


class Regressions(unittest.TestCase):
    def session(self, runtime, duration=21):
        runtime.duration = duration
        env = runtime.env()
        ad = {'url': 'ad', 'duracao': duration, 'errors': ['error:[ERRORCODE]'],
              'impressao': ['impression'], 'eventos': {'complete': ['complete']}}
        env['exibir'] = lambda **kw: env['reproduzir'](ad, tocar=kw['tocar'], dormir=runtime.sleep)
        result = env['exibir_e_devolver'](tocar=runtime.play_ad, dormir=runtime.sleep,
                  estado={'caminho': 'https://media.invalid/movie.mp4', 'posicao': 42.125})
        return result

    def test_completion_skip_and_abort_restore_same_vod_without_plugin_helpers(self):
        for mode in ('ended', 'stopped', 'mid-stall', 'error'):
            with self.subTest(mode=mode):
                runtime = Runtime(mode)
                result = self.session(runtime)
                self.assertTrue(result['retomada_confirmada'])
                self.assertEqual(runtime.restores, ['https://media.invalid/movie.mp4'])
                self.assertIn(('https://media.invalid/movie.mp4', 42.125), runtime.seek_calls)
                self.assertNotIn('plugin://', str(runtime.restores))

    def test_cold_start_21s_ad_freezes_at_5s_aborts_in_3s_and_restores_movie(self):
        runtime = Runtime('mid-stall')
        result = self.session(runtime)
        self.assertEqual(result['motivo'], 'travamento')
        self.assertGreaterEqual(runtime.stop_times[0] - runtime.start, 8.0)
        self.assertLessEqual(runtime.stop_times[0] - runtime.start, 8.5)
        self.assertEqual(runtime.stops, ['ad'])
        self.assertEqual(runtime.events.count('error:405'), 1)
        self.assertNotIn('complete', runtime.events)
        self.assertTrue(result['retomada_confirmada'])
        self.assertEqual(runtime.file, 'https://media.invalid/movie.mp4')
        self.assertIn(('https://media.invalid/movie.mp4', 42.125), runtime.seek_calls)

    def test_decoder_error_while_kodi_still_claims_playing_aborts_immediately(self):
        runtime = Runtime('error-playing')
        result = self.session(runtime)
        self.assertEqual(result['motivo'], 'erro-player')
        self.assertLessEqual(runtime.stop_times[0] - runtime.start, 5.5)
        self.assertEqual(runtime.stops, ['ad'])
        self.assertTrue(result['retomada_confirmada'])

    def test_black_frame_even_with_advancing_clock_releases_movie(self):
        runtime = Runtime('slow-clock')
        env = runtime.env()
        env['_audio_sem_quadro_video'] = lambda: runtime.now - runtime.start >= 5
        result = env['reproduzir']({'url': 'ad', 'duracao': 21}, tocar=runtime.play_ad, dormir=runtime.sleep)
        self.assertEqual(result['motivo'], 'tela-preta-sem-quadro')
        self.assertLessEqual(runtime.stop_times[0] - runtime.start, 8.5)
        self.assertEqual(runtime.stops, ['ad'])

    def test_absolute_duration_plus_5_and_35s_cap_even_when_clock_advances(self):
        for duration, limit in ((21, 26), (120, 35), (0, 35)):
            with self.subTest(duration=duration):
                runtime = Runtime('slow-clock')
                result = self.session(runtime, duration)
                self.assertEqual(result['motivo'], 'timeout-anuncio')
                self.assertLessEqual(runtime.stop_times[0] - runtime.start, limit + .5)
                self.assertGreaterEqual(runtime.stop_times[0] - runtime.start, limit)
                self.assertTrue(result['retomada_confirmada'])
                self.assertEqual(runtime.stops, ['ad'])
                self.assertNotIn('complete', runtime.events)

    def test_xml_latency_counts_against_35s_total_preroll_budget(self):
        runtime = Runtime('slow-clock')
        runtime.duration = 120
        env = runtime.env()
        env.update(PROFUNDIDADE_WRAPPER=3, sem_namespace=lambda data: data,
                   escolher_anuncio=lambda *args: {'url': 'ad', 'duracao': 120})
        def fetch(url):
            runtime.sleep(7)
            return '<VAST/>'
        result = env['exibir'](tag='tag', baixar_tag=fetch, tocar=runtime.play_ad, dormir=runtime.sleep)
        self.assertEqual(result['motivo'], 'timeout-anuncio')
        self.assertLessEqual(runtime.now - 1000, 35.5)
        self.assertEqual(runtime.stops, ['ad'])

    def test_decoder_startup_is_included_in_absolute_deadline(self):
        runtime = Runtime('slow-clock')
        env = runtime.env()
        def delayed_play(url, log):
            runtime.play_ad(url, log)
            runtime.sleep(7)
            return True
        result = env['reproduzir']({'url': 'ad', 'duracao': 21}, tocar=delayed_play, dormir=runtime.sleep)
        self.assertEqual(result['motivo'], 'timeout-anuncio')
        self.assertLessEqual(runtime.now - runtime.start, 26.5)

    def test_safe_mp4_selection_for_cold_decoder(self):
        import xml.etree.ElementTree as ET
        env = Runtime().env()
        def media(attrs, name):
            return '<MediaFile ' + attrs + '>https://ad.invalid/' + name + '</MediaFile>'
        safe = media('type="video/mp4" width="1280" height="720" bitrate="1800" codec="avc1.4d401f,mp4a.40.2"', 'safe.mp4')
        candidates = [
            media('type="video/mp4" width="3840" height="2160" bitrate="15000"', '4k.mp4'),
            media('type="video/mp4" width="1920" height="1080" bitrate="9000"', 'huge.mp4'),
            media('type="video/mp4" codec="hvc1"', 'hevc.mp4'),
            media('type="video/mp4" codec="avc1.640028"', 'high.mp4'),
            media('type="video/webm"', 'vp9.webm'),
            media('type="application/x-mpegURL"', 'stream.m3u8'),
            media('type="video/mp4" width="1920" height="1080" bitrate="3500"', '1080.mp4')]
        inline = ET.fromstring('<InLine><Linear><MediaFiles>' + ''.join(candidates + [safe]) + '</MediaFiles></Linear></InLine>')
        chosen = env['_media_escolhido'](inline, 1080)
        self.assertEqual(chosen['url'], 'https://ad.invalid/safe.mp4')
        inline = ET.fromstring('<InLine><Linear>' + ''.join(candidates[:6]) + '</Linear></InLine>')
        self.assertIsNone(env['_media_escolhido'](inline, 720))

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
        self.assertEqual(runtime.file, 'https://media.invalid/movie.mp4')
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
        self.assertEqual(runtime.file, 'https://media.invalid/movie.mp4')

    def test_exception_after_player_replacement_restores_vod(self):
        runtime = Runtime()
        env = runtime.env()
        env['estado_do_conteudo'] = lambda **kw: {'caminho': 'https://media.invalid/movie.mp4', 'posicao': 42.125}
        def broken(**kw):
            runtime.file, runtime.playing = 'ad', False
            raise RuntimeError('media callback failure')
        env['exibir'] = broken
        receipt = env['exibir_e_devolver']()
        self.assertFalse(receipt['exibido'])
        self.assertTrue(receipt['retomada_confirmada'])
        self.assertEqual(runtime.file, 'https://media.invalid/movie.mp4')
        self.assertIn(('https://media.invalid/movie.mp4', 42.125), runtime.seek_calls)

    def test_restore_never_seeks_the_ad(self):
        runtime = Runtime()
        env = runtime.env()
        runtime.file, runtime.playing = 'ad', True
        runtime.Player.play = lambda *a, **k: None  # asynchronous command not accepted yet
        result = env['restaurar']({'caminho': 'https://media.invalid/movie.mp4', 'posicao': 42.125}, dormir=runtime.sleep,
                                 agora=lambda: runtime.now, espera=1, url_anuncio='ad')
        self.assertFalse(result)
        self.assertEqual(runtime.seek_calls, [])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path)
    args, remaining = parser.parse_known_args()
    ORIGINAL = args.original
    unittest.main(argv=[__file__] + remaining)
