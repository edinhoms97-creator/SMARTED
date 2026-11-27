#!/usr/bin/env python3
"""Lifecycle/transport regression doubles, NOT Android playback or dashboard proof."""
import argparse
import ast
import copy
from pathlib import Path
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

import stabilize_confirmed_ads as stabilize
import restore_confirmed_tracking as reference

sys.path.insert(0, str(stabilize.FOLDER))
import ads_openings

ORIGINAL = None


def defs(path, env, classes=True):
    tree = ast.parse(Path(path).read_text())
    names = {'mostrar_preroll', 'abrir_anuncio', 'tocar_anuncio_de_video', 'iniciar_monitor', '_smarted_iniciar_monitor_original'}
    selected = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names) or classes and isinstance(n, ast.ClassDef)]
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), env)


class Harness:
    def __init__(self, receipts=None):
        self.file, self.playing, self.vip = 'film-a', True, False
        self.state = {'conteudo': 'film-a', 'tentativa': 'film-a', 'anunciado': True, 'ultimo_anuncio': time.time()}
        self.calls, self.threads, self.logs, self.bookings = [], [], [], []
        self.receipts = list(receipts or [{'exibido': True, 'retomada_confirmada': True}]*20)
        self.hold = None
        h = self
        def thread(*args, **kwargs):
            worker = threading.Thread(*args, **kwargs)
            self.threads.append(worker)
            return worker
        def open_key(key):
            if self.state.get('conteudo') != key:
                self.state.clear()
                self.state['conteudo'] = key
        def cancel(key=None):
            self.state.pop('em_exibicao', None)
            self.state.pop('anunciado', None)
        def register(key, when):
            self.bookings.append(key)
            self.state.update(conteudo=key, anunciado=True)
        rules = types.SimpleNamespace(
            _ler=lambda: copy.deepcopy(self.state), _gravar=lambda d: (self.state.clear(), self.state.update(d)),
            abrir_troca=open_key, pode_anunciar=lambda key, now: (self.state.get('tentativa') != key, 'claimed'),
            registrar_anuncio=register, concluir_anuncio=lambda *a: None,
            cancelar_anuncio=cancel, encerrar_conteudo=lambda: self.state.clear())
        class Player:
            def getPlayingFile(self): return h.file
            def isPlayingVideo(self): return h.playing
        self.env = dict(__name__='stabilized_test', time=time, threading=types.SimpleNamespace(Thread=thread, Lock=threading.Lock),
                        _BasePlayer=object, _LOCK_OPORTUNIDADE=threading.RLock(), ads_regra=rules,
                        MOTOR_VAST='vast', ATIVIDADE_PREROLL='preroll', VAST_TAG_PADRAO=reference.TAG,
                        vip_ativo=lambda: h.vip, usar_vast=lambda: True, android=lambda: True,
                        _e_video=lambda p: h.playing, _chave_conteudo=lambda path: path,
                        _normalizar_caminho_chave=lambda path: path.split('|')[0],
                        xbmc=types.SimpleNamespace(Player=Player, LOGINFO=1, LOGWARNING=2,
                             log=lambda msg, *a: h.logs.append(msg), getInfoLabel=lambda k: '',
                             getCondVisibility=lambda k: False, executebuiltin=lambda k: None))
        # Original mostrar_preroll remains identical to 9436b5e.
        source = reference.historical('android-build/ads-patches/smart_ads.py')
        tree = ast.parse(source)
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[]), '<9436 functions>', 'exec'), self.env)
        defs((ORIGINAL / 'smart_ads.py') if ORIGINAL else stabilize.FOLDER / 'smart_ads.py', self.env)
        def forget():
            self.state.clear()
            self.env['_ultima_sessao'] = None
        self.env['esquecer'] = forget
        self.env['abrir_anuncio'] = lambda *a: self.ad()
        self.monitor = self.env['MonitorPreRoll']()
        for k, v in dict(_em_vast=False, _vast_lock=threading.Lock(), ultimo_caminho=None, sessao=0,
                         retomada=False, _ate_ignorar_volta_vast=0, _volta_vast_chave='', log=lambda *a: None, intervalo=0).items():
            setattr(self.monitor, k, v)
        self.monitor._caminho = lambda: self.file
        self.monitor._garantir_player_tela_cheia = lambda: None
        self.monitor._vigiar_imagem = lambda path: None
        self.monitor._limpar_retomada = forget
        self.monitor._retomada = lambda: False

    def ad(self):
        self.calls.append(self.file)
        if self.hold: self.hold.wait(2)
        receipt = self.receipts.pop(0)
        if isinstance(receipt, Exception): raise receipt
        if 'returned' in receipt: self.file = receipt['returned']
        self.env['_smarted_last_receipt'] = receipt
        return bool(receipt.get('exibido')) and receipt.get('retomada_confirmada') is not False

    def callback(self):
        if hasattr(self.monitor, 'onPlayBackStarted'): self.monitor.onPlayBackStarted()
        if hasattr(self.monitor, 'onAVStarted'):
            self.monitor.onAVStarted()
            self.monitor.onPlay()
        else: self.monitor._talvez_mostrar()

    def join(self):
        for worker in self.threads:
            worker.join(3)
            if worker.is_alive(): raise AssertionError('deadlocked worker')
        self.threads.clear()


class Tests(unittest.TestCase):
    def test_three_openings_first_reopen_same_different(self):
        h = Harness()
        h.callback(); h.join()
        h.monitor.onPlayBackStopped()  # deliberately stale isPlayingVideo=True
        h.callback(); h.join()
        h.file = 'film-b'; h.callback(); h.join()
        self.assertEqual(h.calls, ['film-a', 'film-a', 'film-b'])
        self.assertEqual(len(h.bookings), 3)

    def test_ended_reopens_even_inside_legacy_suppression(self):
        h = Harness(); h.callback(); h.join()
        h.monitor._ate_ignorar_volta_vast = time.monotonic()+18
        h.monitor.onPlayBackEnded(); h.callback(); h.join()
        self.assertEqual(h.calls, ['film-a', 'film-a'])

    def test_duplicate_callbacks_pause_seek_reconnect_and_ad_return(self):
        h = Harness(); h.callback(); h.join()
        for _ in range(25): h.callback()
        h.join()
        self.assertEqual(h.calls, ['film-a'])
        self.assertEqual(ads_openings.state(h.monitor).generation, 1)

    def test_concurrent_av_callbacks_claim_once(self):
        h = Harness(); h.hold = threading.Event()
        callers = [threading.Thread(target=h.callback) for _ in range(12)]
        for t in callers: t.start()
        for t in callers: t.join(1); self.assertFalse(t.is_alive())
        h.hold.set(); h.join()
        self.assertEqual(h.calls, ['film-a'])

    def test_ad_stop_end_and_duplicate_complete_do_not_close_content(self):
        h = Harness(); h.hold = threading.Event(); h.callback()
        h.monitor.onPlayBackStopped(); h.monitor.onPlayBackEnded()
        h.callback(); h.hold.set(); h.join(); h.callback(); h.join()
        self.assertEqual(h.calls, ['film-a'])

    def test_nofill_and_network_failure_are_attempts_not_impressions(self):
        h = Harness([{'exibido': False, 'motivo': 'no-fill'}, RuntimeError('network'), {'exibido': True}])
        for i in range(3):
            if i: h.monitor.onPlayBackStopped()
            h.callback(); h.join(); h.callback(); h.join()
        self.assertEqual(h.calls, ['film-a']*3)
        self.assertEqual(h.bookings, ['film-a'])

    def test_returned_resolved_url_is_same_opening(self):
        h = Harness([{'exibido': True, 'returned': 'resolved-a'}])
        h.callback(); h.join(); h.callback(); h.join()
        self.assertEqual(h.calls, ['film-a'])

    def test_movie_episode_channel_switches_have_independent_generations(self):
        h = Harness()
        for key in ('film-a', 'episode-1', 'episode-2', 'channel-1', 'channel-2'):
            h.file = key; h.callback(); h.join()
        self.assertEqual(len(h.calls), 5)

    def test_home_boundary_not_osd_or_pause(self):
        h = Harness(); h.callback(); h.join(); ledger = ads_openings.state(h.monitor)
        self.assertFalse(ledger.observe_ui(False, True))
        self.assertFalse(ledger.observe_ui(False, False))  # OSD/seek/pause
        h.callback(); h.join(); self.assertEqual(len(h.calls), 1)
        ledger.observe_ui(True, False)
        self.assertTrue(ledger.observe_ui(False, True))
        h.callback(); h.join(); self.assertEqual(len(h.calls), 2)

    def test_vip_exemption(self):
        h = Harness(); h.vip = True; h.callback(); h.join()
        self.assertEqual(h.calls, []); self.assertEqual(h.bookings, [])

    def test_callback_lock_not_held_for_media_duration(self):
        h = Harness(); h.hold = threading.Event(); h.callback()
        acquired = h.env['_LOCK_OPORTUNIDADE'].acquire(timeout=.2)
        self.assertTrue(acquired)
        if acquired: h.env['_LOCK_OPORTUNIDADE'].release()
        h.hold.set(); h.join()

    def test_diagnostics_have_no_urls_and_propagate_opening(self):
        lines = []
        kodi = types.SimpleNamespace(log=lambda msg, *a: lines.append(msg))
        ads_openings.context(7); ads_openings.emit(kodi, 'tracking-http-response', status=204)
        self.assertIn('"opening": 7', lines[0]); self.assertNotIn('https://', lines[0])

    def test_focus_wait_only_external_provider(self):
        h = Harness(); calls = []
        env = dict(h.env, tocar_anuncio=lambda *a: True, _kodi_em_foco=lambda: calls.append('focus'))
        defs(stabilize.FOLDER/'smart_ads.py', env)
        env['abrir_anuncio']('preroll'); self.assertEqual(calls, [])
        env['usar_vast'] = lambda: False
        env['abrir_anuncio']('preroll'); self.assertEqual(calls, ['focus'])

    def actual_vast(self):
        if not ORIGINAL: self.skipTest('native function doubles run against generated APK modules in runner')
        import test_original_ad_patch as original_test
        case = original_test.Tests('test_exact_tag')
        case.folder = ORIGINAL
        case.setUp()
        return case, original_test.Player

    def test_actual_completion_processed_once_and_tracking_kept(self):
        case, player = self.actual_vast()
        env, clock = case.env, [0.0]
        env['_agora'] = lambda: clock[0]
        env['_posicao_e_duracao'] = lambda: (clock[0], 1)
        def play(url, log):
            player.file, player.playing = url, True
            return True
        def sleep(seconds):
            clock[0] += seconds
            if clock[0] >= 1 and player.playing:
                player.playing = False
                player.observer.onPlayBackEnded()
                player.observer.onPlayBackEnded()  # real callback duplicated
        receipt = env['reproduzir']({'url': 'creative', 'impressao': ['impression'],
                       'eventos': {'start': ['start'], 'complete': ['complete']}, 'duracao': 1},
                       tocar=play, dormir=sleep)
        self.assertEqual(receipt['motivo'], 'concluido')
        self.assertEqual(case.events.count('impression'), 1)
        self.assertEqual(case.events.count('start'), 1)
        self.assertEqual(case.events.count('complete'), 1)

    def test_actual_zero_position_resume_has_no_seek_or_poll_delay(self):
        case, player = self.actual_vast()
        sleeps, seeks = [], []
        old = player.seekTime
        try:
            player.seekTime = lambda self, value: seeks.append(value)
            self.assertTrue(case.env['restaurar']({'caminho': 'movie', 'posicao': 0}, dormir=sleeps.append))
        finally:
            player.seekTime = old
        self.assertEqual(seeks, [])
        self.assertEqual(sleeps, [])

    def test_actual_pixel_http_receipt_is_distinct_from_impression_queue(self):
        case, _ = self.actual_vast()
        received = []
        class Response:
            def getcode(self): return 204
            def close(self): pass
        with patch('urllib.request.urlopen', return_value=Response()) as network:
            sent = case.env['disparar'](['https://pixel.invalid/?c=[CACHEBUSTING]'])
        self.assertEqual(sent, 1)
        self.assertEqual(network.call_count, 1)
        self.assertNotIn('[CACHEBUSTING]', network.call_args.args[0].full_url)

    def test_actual_modules_keep_tracking_and_nonlifecycle_ast(self):
        if not ORIGINAL: self.skipTest('full APK source audit executes in build runner')
        # Build tool has already audited all other scopes against reconstructed
        # 9436b5e+tracking. Recheck tag transport/selection/constants explicitly.
        vast = (ORIGINAL/'ads_vast.py').read_text()
        old = reference.update_tracking(reference.historical('android-build/ads-patches/ads_vast.py'))
        for name in ('tag_configurada', 'baixar'):
            self.assertEqual(ast.dump(stabilize.nodes(vast)[name]), ast.dump(stabilize.nodes(old)[name]))
        self.assertEqual((ORIGINAL/'ads_tracking.py').read_bytes(), reference.HELPER_SOURCE.read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path)
    args, remaining = parser.parse_known_args()
    ORIGINAL = args.original
    unittest.main(argv=[sys.argv[0]]+remaining, verbosity=2)
