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
    names = {'motor_anuncio', 'mostrar_preroll', 'abrir_anuncio', 'tocar_anuncio_de_video', 'iniciar_monitor', '_smarted_iniciar_monitor_original'}
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
        self.env['usar_vast'] = lambda: True
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

    def test_late_channel_metadata_binds_identity_without_extra_attempt(self):
        ledger = ads_openings.Opening()
        first = ledger.claim('shared-stream')
        ledger.finish(first, 'shared-stream')
        self.assertIsNone(ledger.claim('shared-stream', 'channel-one'))
        self.assertIsNotNone(ledger.claim('shared-stream', 'channel-two'))

    def observer(self, h):
        h.monitor.isPlayingVideo = lambda: h.playing
        h.media = h.playing
        kodi = types.SimpleNamespace(log=lambda msg, *a: h.logs.append(msg),
                    getCondVisibility=lambda key: h.media if key == 'Player.HasMedia' else key == 'Window.IsActive(fullscreenvideo)',
                    getInfoLabel=lambda key: '')
        return kodi

    def test_passive_native_observer_three_openings_without_any_av_callback(self):
        h = Harness(); kodi = self.observer(h)
        previous = ads_openings.observe(h.monitor, kodi); h.join()
        for _ in range(20): previous = ads_openings.observe(h.monitor, kodi, previous)
        h.join(); self.assertEqual(h.calls, ['film-a'])
        h.playing = h.media = False
        previous = ads_openings.observe(h.monitor, kodi, previous)
        h.playing = h.media = True
        previous = ads_openings.observe(h.monitor, kodi, previous); h.join()
        h.file = 'film-b'
        ads_openings.observe(h.monitor, kodi, previous); h.join()
        self.assertEqual(h.calls, ['film-a', 'film-a', 'film-b'])

    def test_passive_observer_stale_stop_does_not_claim_closing_video(self):
        h = Harness(); kodi = self.observer(h)
        previous = ads_openings.observe(h.monitor, kodi); h.join()
        h.monitor.onPlayBackStopped()  # getter still exposes the old frame
        previous = ads_openings.observe(h.monitor, kodi, (False, '', '')); h.join()
        self.assertEqual(h.calls, ['film-a'])
        h.playing = h.media = False
        previous = ads_openings.observe(h.monitor, kodi, previous)
        h.playing = h.media = True
        ads_openings.observe(h.monitor, kodi, previous); h.join()
        self.assertEqual(h.calls, ['film-a', 'film-a'])

    def test_passive_observer_buffering_reconnect_is_not_close(self):
        h = Harness(); kodi = self.observer(h)
        previous = ads_openings.observe(h.monitor, kodi); h.join()
        h.playing, h.media = False, True
        previous = ads_openings.observe(h.monitor, kodi, previous)
        h.playing = True
        ads_openings.observe(h.monitor, kodi, previous); h.join()
        self.assertEqual(h.calls, ['film-a'])

    def test_passive_observer_live_eof_reconnect_does_not_repeat(self):
        h = Harness(); kodi = self.observer(h)
        previous = ads_openings.observe(h.monitor, kodi); h.join()
        with patch.dict(sys.modules, {'ao_vivo': types.SimpleNamespace(eh_ao_vivo=lambda path: True)}):
            h.playing = h.media = False
            previous = ads_openings.observe(h.monitor, kodi, previous)
        h.playing = h.media = True
        ads_openings.observe(h.monitor, kodi, previous); h.join()
        self.assertEqual(h.calls, ['film-a'])

    def test_live_automatic_home_on_eof_is_not_a_user_home_return(self):
        h = Harness(); kodi = self.observer(h)
        h.home = False
        kodi.getCondVisibility = lambda key: (h.media if key == 'Player.HasMedia' else h.home if key == 'Window.IsActive(home)' else not h.home)
        previous = ads_openings.observe(h.monitor, kodi); h.join()
        with patch.dict(sys.modules, {'ao_vivo': types.SimpleNamespace(eh_ao_vivo=lambda path: True)}):
            h.playing = h.media = False; h.home = True
            for _ in range(5):
                previous = ads_openings.observe(h.monitor, kodi, previous)
        h.playing = h.media = True; h.home = False
        ads_openings.observe(h.monitor, kodi, previous); h.join()
        self.assertEqual(h.calls, ['film-a'])

    def test_live_channel_token_refresh_not_new_opening_but_stop_is(self):
        ledger = ads_openings.Opening()
        first = ledger.claim('stream?token=one', 'Channel A')
        ledger.finish(first, 'stream?token=one')
        self.assertIsNone(ledger.claim('stream?token=two', 'Channel A'))
        self.assertIn('stream?token=two', ledger.aliases)
        ledger.close()
        self.assertIsNotNone(ledger.claim('stream?token=three', 'Channel A'))

    def test_stop_then_switch_without_no_media_poll_is_not_permanently_fenced(self):
        h = Harness(); kodi = self.observer(h)
        previous = ads_openings.observe(h.monitor, kodi); h.join()
        h.monitor.onPlayBackStopped()
        # Kodi changed directly A -> B between two polls; HasMedia never sampled false.
        h.file = 'film-b'
        for _ in range(4):
            previous = ads_openings.observe(h.monitor, kodi, previous)
        h.join()
        self.assertEqual(h.calls, ['film-a', 'film-b'])

    def test_first_video_edge_with_temporarily_missing_metadata_is_retried_locally(self):
        h = Harness(); kodi = self.observer(h)
        h.env['_e_video'] = lambda player: False
        previous = ads_openings.observe(h.monitor, kodi); h.join()
        # Only the gate getter was briefly not ready; native edge/path are stable.
        h.env['_e_video'] = lambda player: True
        for _ in range(4):
            previous = ads_openings.observe(h.monitor, kodi, previous)
        h.join()
        self.assertEqual(h.calls, ['film-a'])

    def test_validation_stage_vast_even_on_admob_compatible_phone(self):
        source = (ORIGINAL / 'smart_ads.py') if ORIGINAL else stabilize.FOLDER/'smart_ads.py'
        node = stabilize.nodes(source.read_text())['motor_anuncio']
        logs = []
        env = dict(MOTOR_VAST='vast', MOTOR_ADMOB='admob', _SAUDE_ADMOB={},
                   xbmc=types.SimpleNamespace(log=lambda *a: logs.append(a)))
        def variant(compatible, selected):
            return types.SimpleNamespace(compatibilidade_admob=lambda: {'compativel': compatible},
                selecionar_motor_anuncio=lambda **kw: (selected, 'native-selection', {}))
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<provider>', 'exec'), env)
        for supported, choice, expected in ((True, 'admob', 'vast'), (False, 'admob', 'vast'),
                                              (True, 'vast', 'vast')):
            env['_variante'] = variant(supported, choice)
            self.assertEqual(env['motor_anuncio']()[0], expected)
        self.assertTrue(any('provider-selected' in str(line) for line in logs))

    def test_blocked_reason_distinguishes_vip_duplicate_pending_and_running(self):
        h = Harness(); h.vip = True
        self.assertEqual(h.monitor._talvez_mostrar(), 'blocked')
        self.assertTrue(any('vip-exempt' in line for line in h.logs))
        h.vip = False; h.playing = False
        self.assertEqual(h.monitor._talvez_mostrar(), 'pending')
        h.playing = True; h.callback(); h.join()
        self.assertEqual(h.monitor._talvez_mostrar(), 'blocked')
        self.assertTrue(any('opening-already-attempted' in line for line in h.logs))

    def test_transient_native_read_does_not_create_extra_network_attempts(self):
        h = Harness(); kodi = self.observer(h)
        previous = ads_openings.observe(h.monitor, kodi); h.join()
        h.env['_e_video'] = lambda p: False
        h.monitor._smarted_pending_metadata = True
        previous = ads_openings.observe(h.monitor, kodi, previous)
        h.env['_e_video'] = lambda p: True
        for _ in range(20): previous = ads_openings.observe(h.monitor, kodi, previous)
        h.join(); self.assertEqual(len(h.calls), 1)

    def test_http_error_timeout_and_network_logs_do_not_leak_urls(self):
        from urllib.error import HTTPError, URLError
        lines = []
        kodi = types.SimpleNamespace(log=lambda line, *a: lines.append(line))
        for error in (HTTPError('https://private.invalid/?token=secret', 503, 'error', {}, None),
                      URLError(TimeoutError('private URL hidden')), OSError('secret')):
            ads_openings.transport_failure(kodi, error)
        self.assertIn('503', lines[0])
        self.assertIn('vast-transport-timeout', lines[1])
        self.assertNotIn('secret', ''.join(lines))
        self.assertNotIn('private.invalid', ''.join(lines))

    def test_new_content_selected_during_nofill_gets_its_own_attempt(self):
        h = Harness([{'exibido': False, 'motivo': 'no-fill', 'returned': 'film-b'}, {'exibido': False, 'motivo': 'no-fill'}])
        h.callback(); h.join()
        self.assertEqual(h.calls, ['film-a', 'film-b'])
        h.callback(); h.join()
        self.assertEqual(h.calls, ['film-a', 'film-b'])

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

    def test_actual_full_module_retries_readiness_with_unmodified_native_path_getter(self):
        if not ORIGINAL:
            self.skipTest('full native module import runs against generated APK modules in runner')
        h = Harness()
        class NativePlayer:
            reads = 0
            def isPlayingVideo(self):
                NativePlayer.reads += 1
                return NativePlayer.reads != 2  # gate read lags the first observer edge
            def getPlayingFile(self): return 'file:///sdcard/Movies/movie.mp4'
        kodi = types.SimpleNamespace(Player=NativePlayer, LOGINFO=1, LOGWARNING=2,
            getCondVisibility=lambda key: key in ('System.Platform.Android', 'Window.IsActive(fullscreenvideo)', 'Player.HasMedia'),
            getInfoLabel=lambda key: '', log=lambda line, *a: h.logs.append(line), executebuiltin=lambda *a: None)
        modules = {'xbmc': kodi, 'xbmcvfs': types.SimpleNamespace(),
                   'ads_regra': h.env['ads_regra'], 'variante': types.SimpleNamespace()}
        with patch.dict(sys.modules, modules):
            env = {'__name__': 'full_native_test', '__file__': str(ORIGINAL/'smart_ads.py')}
            exec(compile((ORIGINAL/'smart_ads.py').read_text(), env['__file__'], 'exec'), env)
            env['threading'] = h.env['threading']
            env['vip_ativo'] = lambda: False
            env['abrir_anuncio'] = lambda *a: h.calls.append('dispatch') or False
            monitor = env['MonitorPreRoll']()
            previous = ads_openings.observe(monitor, kodi)
            self.assertTrue(monitor._smarted_pending_metadata)
            for _ in range(4): previous = ads_openings.observe(monitor, kodi, previous)
            h.join()
            self.assertEqual(h.calls, ['dispatch'])
            self.assertTrue(any('video-not-ready' in line for line in h.logs))
            self.assertTrue(any('opening-claimed' in line for line in h.logs))

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

    def test_actual_seek_confirmation_allows_native_clock_to_keep_advancing(self):
        case, player = self.actual_vast()
        clock, sleeps = [0.0], []
        old_seek, old_time = player.seekTime, player.getTime
        def seek(self, target):
            player.current = target
            clock[0] += .4  # native seek/decode returned after clock advanced
        try:
            player.seekTime = seek
            player.getTime = lambda self: player.current + clock[0]
            def sleep(seconds):
                clock[0] += seconds
                sleeps.append(seconds)
            ready = case.env['restaurar']({'caminho': 'movie', 'posicao': 42.125},
                                          dormir=sleep, agora=lambda: clock[0])
            self.assertTrue(ready)
            self.assertEqual(sleeps, [])  # old fixed-target check waits/fails for 3s
        finally:
            player.seekTime, player.getTime = old_seek, old_time

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
        self.assertEqual(ast.dump(stabilize.nodes(vast)['tag_configurada']), ast.dump(stabilize.nodes(old)['tag_configurada']))
        def without_transport_diagnostics(node):
            node = copy.deepcopy(node)
            for parent in ast.walk(node):
                if isinstance(parent, ast.ExceptHandler):
                    parent.name = None
                for field in ('body', 'orelse', 'finalbody'):
                    body = getattr(parent, field, None)
                    if isinstance(body, list):
                        setattr(parent, field, [item for item in body if not (
                            isinstance(item, ast.ImportFrom) and item.module == 'ads_openings'
                            or isinstance(item, ast.Expr) and isinstance(item.value, ast.Call)
                            and isinstance(item.value.func, ast.Name) and item.value.func.id == 'transport_failure')])
            return ast.dump(node)
        self.assertEqual(without_transport_diagnostics(stabilize.nodes(vast)['baixar']),
                         without_transport_diagnostics(stabilize.nodes(old)['baixar']))
        self.assertEqual((ORIGINAL/'ads_tracking.py').read_bytes(), reference.HELPER_SOURCE.read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path)
    args, remaining = parser.parse_known_args()
    ORIGINAL = args.original
    if ORIGINAL: sys.path.insert(0, str(ORIGINAL))
    unittest.main(argv=[sys.argv[0]]+remaining, verbosity=2)
