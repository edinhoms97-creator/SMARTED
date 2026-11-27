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
        names = {'motor_anuncio', 'mostrar_preroll', 'tocar_anuncio_de_video', 'esquecer'}
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

    def test_vip_exemption_is_preserved(self):
        h = Harness([])
        h.env['vip_ativo'] = lambda: True
        h.open('filme')
        self.assertEqual(h.calls, [])

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
