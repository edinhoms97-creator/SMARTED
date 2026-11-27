#!/usr/bin/env python3
"""One opportunity per opening, real threads + persisted-state model, no ads/network.

CI additionally runs with --original against patched ORIGINAL modules/classes.
"""
import ast
import copy
import json
import re
import os
import hashlib
from pathlib import Path
import sys
import threading
import types
import unittest

PATCHES = Path(__file__).resolve().parent.parent / 'android-build/ads-patches'
ORIGINAL = None


def definitions(path, env, names=None, classes=False):
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
    selected = [node for node in tree.body if
                (isinstance(node, ast.FunctionDef) and (names is None or node.name in names)) or
                (classes and isinstance(node, ast.ClassDef) and node.name == 'MonitorPreRoll')]
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), env)
    return env


class Harness:
    def __init__(self, receipts):
        self.now = 1000.0
        self.file = ''
        self.playing = False
        self.state = {}
        self.calls = []
        self.bookings = []
        self.logs = []
        self.threads = []
        self.receipts = iter(receipts)
        self.lock = threading.RLock()
        clock = types.SimpleNamespace(time=lambda: self.now, monotonic=lambda: self.now)
        self.rule_env = {'__name__': 'rules_test', 'time': clock, 'INTERVALO': 0,
                         'json': json, 're': re, 'os': os, 'hashlib': hashlib}
        if ORIGINAL:
            definitions(ORIGINAL / 'ads_regra.py', self.rule_env)
        else:
            # Original storage/transition contracts audited from the APK.
            def open_key(key):
                if self.state.get('conteudo') == key:
                    return False
                self.state['conteudo'] = key
                for field in ('tentativa', 'anunciado', 'anunciados'):
                    self.state.pop(field, None)
                return True
            def register(key, when):
                self.state.update(conteudo=key, tentativa=key, anunciado=True, ultimo_anuncio=when, em_exibicao=when)
            def end(when):
                self.state['ultimo_anuncio'] = when
                self.state.pop('em_exibicao', None)
            def cancel(key=None):
                self.state.pop('anunciado', None)
                self.state.pop('em_exibicao', None)
            def close():
                self.state.clear()
            self.rule_env.update(abrir_troca=open_key, registrar_anuncio=register, concluir_anuncio=end,
                                 cancelar_anuncio=cancel, encerrar_conteudo=close)
            definitions(PATCHES / 'ads_regra.py', self.rule_env)
        self.rule_env['_ler'] = lambda: copy.deepcopy(self.state)
        self.rule_env['_gravar'] = self.save
        original_register = self.rule_env['registrar_anuncio']
        def register(*args):
            self.bookings.append(args)
            return original_register(*args)
        self.rule_env['registrar_anuncio'] = register
        rules = types.SimpleNamespace(**self.rule_env)
        harness = self
        class Player:
            def isPlayingVideo(self):
                return harness.playing
        def make_thread(*args, **kwargs):
            worker = threading.Thread(*args, **kwargs)
            self.threads.append(worker)
            return worker
        self.env = {
            '__name__': 'smart_ads_test', '_BasePlayer': object, 'time': clock,
            'MOTOR_VAST': 'vast', 'ATIVIDADE_PREROLL': 'preroll', 'VAST_TAG_PADRAO': 'tag',
            'threading': types.SimpleNamespace(Thread=make_thread, Lock=threading.Lock),
            'xbmc': types.SimpleNamespace(Player=Player, LOGWARNING=2, getInfoLabel=lambda _: '',
                                          getCondVisibility=lambda _: False, executebuiltin=lambda _: None),
            'ads_regra': rules, '_LOCK_OPORTUNIDADE': self.lock,
            '_chave_conteudo': lambda path: path, '_normalizar_caminho_chave': lambda path: path,
            'vip_ativo': lambda: False, 'usar_vast': lambda: True, 'android': lambda: True,
            '_e_video': lambda player: self.playing, '_info': lambda _: '720',
            'esquecer': lambda: self.rule_env['encerrar_conteudo'](),
        }
        names = {'motor_anuncio', 'mostrar_preroll', 'tocar_anuncio_de_video', 'esquecer',
                 'iniciar_monitor', '_smarted_iniciar_monitor_original'}
        definitions((ORIGINAL or PATCHES) / 'smart_ads.py', self.env, names=names, classes=True)
        self.env['_ads_vast'] = lambda: types.SimpleNamespace(tag_configurada=lambda _: 'tag', exibir_e_devolver=self.ad)
        self.env['abrir_anuncio'] = lambda activity, log: self.env['tocar_anuncio_de_video'](log)
        self.monitor = self.env['MonitorPreRoll']()
        for name, value in {'_em_vast': False, '_vast_lock': threading.Lock(), 'ultimo_caminho': None,
                            'sessao': 0, 'retomada': False, '_ate_ignorar_volta_vast': 0,
                            '_volta_vast_chave': '', 'log': self.logs.append, 'intervalo': 0}.items():
            setattr(self.monitor, name, value)
        self.monitor._caminho = lambda: self.file
        self.monitor._garantir_player_tela_cheia = lambda: None
        self.monitor._vigiar_imagem = lambda path: None
        self.monitor._limpar_retomada = lambda: self.rule_env['encerrar_conteudo']()
        self.env['_monitor'] = self.monitor
        if not ORIGINAL:
            self.env['_smarted_iniciar_monitor_original'] = lambda log, intervalo: self.monitor

    def save(self, data):
        self.state.clear()
        self.state.update(copy.deepcopy(data))
        return True

    def ad(self, **kwargs):
        self.calls.append(self.file)
        receipt = next(self.receipts)
        if isinstance(receipt, BaseException):
            raise receipt
        self.now += receipt.get('segundos', 0)
        if receipt.get('caminho_devolvido'):
            self.file = receipt['caminho_devolvido']
        return dict(receipt)

    def join(self):
        for worker in self.threads:
            worker.join(timeout=2)
            if worker.is_alive():
                raise AssertionError('Ad worker deadlocked')
        self.threads.clear()

    def open(self, key):
        self.file, self.playing = key, True
        self.monitor.sessao += 1
        self.env['mostrar_preroll'](self.logs.append, caminho=key, chave=key,
                                    sessao=self.monitor.sessao, disparar=self.monitor._disparar)
        self.join()

    def repeat(self, new_session=False):
        if new_session:
            self.monitor.sessao += 1
        self.env['mostrar_preroll'](self.logs.append, caminho=self.file, chave=self.file,
                                    sessao=self.monitor.sessao, disparar=self.monitor._disparar)
        self.join()


SUCCESS = {'exibido': True, 'retomada_confirmada': True, 'segundos': 15, 'motivo': 'concluido'}
NOFILL = {'exibido': False, 'motivo': 'no-fill'}


class Tests(unittest.TestCase):
    def test_seven_contents_without_two_minute_wait(self):
        h = Harness([{'exibido': False, 'motivo': 'travamento'}, NOFILL, SUCCESS, SUCCESS,
                     {'exibido': False, 'motivo': 'falha-rede-vast'}, SUCCESS, SUCCESS])
        keys = ['filme1', 'filme2', 'serie/ep1', 'canal1', 'canal2', 'serie/ep2', 'filme3']
        for key in keys:
            h.open(key)
            h.now += .1
        self.assertEqual(h.calls, keys)
        self.assertEqual(len(h.bookings), 4)
        self.assertLess(h.now - 1000, 120)

    def test_pause_seek_reconnect_do_not_repeat(self):
        h = Harness([SUCCESS])
        h.open('filme')
        for _ in range(4):
            h.repeat(new_session=True)  # reconnection may raise PlaybackStarted again
        self.assertEqual(h.calls, ['filme'])

    def test_nofill_is_one_attempt_not_a_retry_loop(self):
        h = Harness([NOFILL, SUCCESS])
        h.open('filme1')
        h.repeat(new_session=True)
        h.open('filme2')
        self.assertEqual(h.calls, ['filme1', 'filme2'])
        self.assertEqual(len(h.bookings), 1)

    def test_exception_releases_worker_and_allows_next_content(self):
        h = Harness([RuntimeError('decode failed'), SUCCESS])
        h.open('filme1')
        self.assertFalse(h.monitor._em_vast)
        h.open('canal')
        self.assertEqual(h.calls, ['filme1', 'canal'])
        self.assertEqual(len(h.bookings), 1)

    def test_failed_seek_does_not_book_success(self):
        h = Harness([dict(SUCCESS, retomada_confirmada=False), SUCCESS])
        h.open('ep1')
        h.open('ep2')
        self.assertEqual(len(h.bookings), 1)

    def test_reopening_same_content_after_explicit_close(self):
        h = Harness([SUCCESS, SUCCESS])
        h.open('filme')
        h.playing = False
        h.monitor.onPlayBackStopped()
        h.open('filme')  # even within the old 18-second resume suppression window
        self.assertEqual(h.calls, ['filme', 'filme'])

    def test_old_persisted_two_minute_state_does_not_block(self):
        h = Harness([SUCCESS])
        h.state.update(conteudo='filme', tentativa='filme', anunciado=True, ultimo_anuncio=999.9)
        h.open('filme')
        self.assertEqual(h.calls, ['filme'])

    def test_server_fallback_is_same_opening_and_does_not_request_second_ad(self):
        receipt = dict(SUCCESS, caminho_devolvido='https://backup.invalid/film.mp4', retomada_confirmada=True)
        h = Harness([receipt])
        h.open('https://proxy.invalid/film')
        self.assertEqual(h.monitor._volta_vast_chave, 'https://backup.invalid/film.mp4')
        self.assertEqual(h.state.get('tentativa'), 'https://backup.invalid/film.mp4')
        h.env['mostrar_preroll'](caminho=h.file, chave=h.file, sessao=999, disparar=h.monitor._disparar)
        h.join()
        self.assertEqual(len(h.calls), 1)

    def test_vip_exemption_is_preserved(self):
        h = Harness([])
        h.env['vip_ativo'] = lambda: True
        h.open('filme')
        self.assertEqual(h.calls, [])

    def test_monitor_installed_after_av_catches_first_film_or_channel(self):
        for first in ('filme1', 'canal1', 'serie/ep1'):
            with self.subTest(first=first):
                h = Harness([SUCCESS, SUCCESS, SUCCESS, SUCCESS])
                # No PlaybackStarted/onAVStarted delivered: AV preceded observer install.
                h.file, h.playing = first, True
                self.assertEqual(h.monitor.sessao, 0)
                h.env['iniciar_monitor'](h.logs.append, 0)
                h.join()
                h.env['iniciar_monitor'](h.logs.append, 0)
                h.join()
                for key in ('canal2', 'filme3', 'serie/ep4'):
                    h.file = key  # AV callback without PlaybackStarted; same session number
                    h.monitor._talvez_mostrar()
                    h.join()
                self.assertEqual(h.calls, [first, 'canal2', 'filme3', 'serie/ep4'])

    def test_cold_zero_session_clears_stale_duplicate_state(self):
        h = Harness([SUCCESS])
        h.env.update(_ultima_sessao=0, _ultimo_caminho_preroll='canal')
        h.state.update(conteudo='canal', tentativa='canal', anunciado=True)
        h.file, h.playing = 'canal', True
        h.env['iniciar_monitor'](h.logs.append, 0)
        h.join()
        self.assertEqual(h.calls, ['canal'])

    def test_av_not_ready_is_not_consumed_until_video_callback(self):
        h = Harness([SUCCESS])
        h.file, h.playing = 'filme', False
        h.env['iniciar_monitor'](h.logs.append, 0)
        h.join()
        self.assertEqual(h.calls, [])
        self.assertNotIn('tentativa', h.state)
        h.playing = True
        h.monitor._talvez_mostrar()
        h.join()
        self.assertEqual(h.calls, ['filme'])

    def test_no_competing_live_watchdog_is_started_while_ad_is_queued(self):
        h = Harness([SUCCESS])
        entered, release = threading.Event(), threading.Event()
        real_ad = h.ad
        def blocked_ad(**kw):
            entered.set()
            if not release.wait(timeout=2):
                raise AssertionError('release missing')
            return real_ad(**kw)
        h.env['_ads_vast'] = lambda: types.SimpleNamespace(tag_configurada=lambda _: 'tag', exibir_e_devolver=blocked_ad)
        watches = []
        h.monitor._vigiar_imagem = lambda path: watches.append(path)
        h.file, h.playing = 'canal', True
        try:
            h.monitor._talvez_mostrar()
            self.assertTrue(entered.wait(timeout=2))
            self.assertEqual(watches, [])
        finally:
            release.set()
            h.join()
        self.assertEqual(watches, ['canal'])

    @unittest.skipUnless(ORIGINAL, 'Original callbacks are available in the APK build runner')
    def test_original_playback_and_avstarted_callbacks_are_one_opportunity(self):
        h = Harness([SUCCESS, SUCCESS])
        h.file, h.playing = 'filme', True
        h.monitor.onPlayBackStarted()
        h.monitor.onAVStarted()
        h.join()
        h.monitor.onAVStarted()
        h.monitor.onPlay()
        h.join()
        self.assertEqual(h.calls, ['filme'])
        h.playing = False
        h.monitor.onPlayBackStopped()
        h.file, h.playing = 'canal', True
        h.monitor.onPlayBackStarted()
        h.monitor.onAVStarted()
        h.join()
        self.assertEqual(h.calls, ['filme', 'canal'])


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--original':
        ORIGINAL = Path(sys.argv[2])
        del sys.argv[1:3]
        # skipUnless is evaluated at class definition, before argument parsing.
        Tests.test_original_playback_and_avstarted_callbacks_are_one_opportunity.__unittest_skip__ = False
    result = unittest.main(exit=False).result
    for test, detail in result.failures + result.errors:
        print('::error title=Ad opening regression::' + str(test) + ': ' + detail.strip().splitlines()[-1])
    sys.exit(0 if result.wasSuccessful() else 1)
