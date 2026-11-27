#!/usr/bin/env python3
"""Narrow menu transition tests with Kodi doubles; NOT Android/hardware tests."""
import argparse
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import test_ads_regressions as media

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / 'android-build/ads-patches'
ORIGINAL = None


class MenuRuntime:
    def __init__(self, dialog=12000, heading='Escolha o player', labels=None):
        self.file = 'https://media.invalid/owned.mp4'
        self.playing = True
        self.dialog, self.heading = dialog, heading
        self.labels = labels or ['VideoPlayer (Padrão)', 'MX Player']
        self.commands = []
        self.now, self.workers = 0., []
        rt = self
        class Player:
            def isPlayingVideo(self): return rt.playing
            def getPlayingFile(self): return rt.file
        def builtin(command):
            self.commands.append(command)
            self.dialog = 0
        self.kodi = types.SimpleNamespace(Player=Player, executebuiltin=builtin)
        class Control:
            def __init__(self, control): self.control = control
            def getLabel(self):
                if self.control == 1: return rt.heading
                if self.control >= 1001: return rt.labels[self.control - 1001]
                raise RuntimeError('unknown control')
            def getListItem(self, index):
                return types.SimpleNamespace(getLabel=lambda: rt.labels[index])
        class Window:
            def getControl(self, control): return Control(control)
        self.gui = types.SimpleNamespace(Window=lambda _: Window(), getCurrentWindowDialogId=lambda: rt.dialog)
        self.clock = types.SimpleNamespace(monotonic=lambda: rt.now, sleep=self.sleep)
        class Thread:
            def __init__(self, target, **kwargs): rt.workers.append(target)
            def start(self): pass  # run explicitly under fake clock in test
        self.threading = types.SimpleNamespace(Thread=Thread)
    def sleep(self, seconds): self.now += seconds


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ORIGINAL or FOLDER))
        cls.resume = importlib.import_module('ads_resume')
        media.ORIGINAL = ORIGINAL

    def test_native_subtitle_dialogs_close_without_turning_subtitles_off(self):
        for dialog in (10153, 10159):
            with self.subTest(dialog=dialog):
                rt = MenuRuntime(dialog)
                self.assertTrue(self.resume.close_transition_menu(rt.kodi, rt.gui, rt.file))
                self.assertEqual(rt.commands, ['Dialog.Close(%d,true)' % dialog])

    def test_player_and_captions_select_dialog_headings_close(self):
        for heading in ('Escolha o player', 'Selecionar reprodutor', 'Captions', 'Subtitles', 'Legendas', 'ESCOLHA O SERVIDOR'):
            with self.subTest(heading=heading):
                rt = MenuRuntime(heading=heading)
                self.assertTrue(self.resume.close_transition_menu(rt.kodi, rt.gui, rt.file))
                self.assertEqual(rt.commands, ['Dialog.Close(12000,true)'])

    def test_real_kodi_core_factory_context_menu_uses_player_name_buttons(self):
        rt = MenuRuntime(dialog=10106)
        self.assertTrue(self.resume.close_transition_menu(rt.kodi, rt.gui, rt.file))
        self.assertEqual(rt.commands, ['Dialog.Close(10106,true)'])

    def test_generic_heading_with_player_names_in_list_is_recognized(self):
        rt = MenuRuntime(heading='Selecione uma opção')
        self.assertTrue(self.resume.close_transition_menu(rt.kodi, rt.gui, rt.file))

    def test_unrelated_pin_payment_library_and_language_menus_stay_open(self):
        for dialog, heading, labels in ((12000, 'Código VIP', ['Ativar', 'Cancelar']),
                                        (12000, 'Selecione idioma', ['Português', 'English']),
                                        (10106, '', ['Atualizar biblioteca', 'Informações']),
                                        (10100, 'Pagar', ['Confirmar'])):
            with self.subTest(dialog=dialog, heading=heading):
                rt = MenuRuntime(dialog, heading, labels)
                self.assertFalse(self.resume.close_transition_menu(rt.kodi, rt.gui, rt.file))
                self.assertEqual(rt.commands, [])

    def test_menu_for_new_user_selected_content_is_never_closed(self):
        rt = MenuRuntime()
        self.assertFalse(self.resume.close_transition_menu(rt.kodi, rt.gui, 'https://media.invalid/older-film.mp4'))
        rt.playing = False
        self.assertFalse(self.resume.close_transition_menu(rt.kodi, rt.gui, rt.file))
        self.assertEqual(rt.commands, [])

    def test_guard_is_nonblocking_bounded_and_catches_delayed_menu(self):
        rt = MenuRuntime(dialog=0)
        def sleep(seconds):
            rt.sleep(seconds)
            if rt.now >= 1 and not rt.commands:
                rt.dialog = 10159
        clock = types.SimpleNamespace(monotonic=lambda: rt.now, sleep=sleep)
        with patch.dict(sys.modules, {'xbmcgui': rt.gui, 'threading': rt.threading}), patch.object(self.resume, 'time', clock):
            self.assertTrue(self.resume.guard_transition(rt.kodi, rt.file))
            self.assertEqual(rt.now, 0)  # no startup/decoder watchdog wait changed
            self.assertEqual(len(rt.workers), 1)
            rt.workers[0]()
        self.assertLessEqual(rt.now, 5.1)
        self.assertGreaterEqual(rt.now, 5.0)
        self.assertEqual(rt.commands, ['Dialog.Close(10159,true)'])

    def test_guard_exits_when_another_movie_starts(self):
        rt = MenuRuntime(dialog=0)
        expected = rt.file
        def sleep(seconds):
            rt.sleep(seconds)
            rt.file = 'https://media.invalid/new-choice.mp4'
            rt.dialog = 10153
        with patch.dict(sys.modules, {'xbmcgui': rt.gui, 'threading': rt.threading}), patch.object(self.resume, 'time', types.SimpleNamespace(monotonic=lambda: rt.now, sleep=sleep)):
            self.resume.guard_transition(rt.kodi, expected)
            rt.workers[0]()
        self.assertLessEqual(rt.now, .2)
        self.assertEqual(rt.commands, [])

    def test_completion_skip_abort_guard_only_real_ad_start_and_direct_resume(self):
        for mode in ('ended', 'stopped', 'mid-stall', 'error-playing'):
            with self.subTest(mode=mode):
                rt = media.Runtime(mode)
                env = rt.env()
                seen = []
                env['exibir'] = lambda **kw: env['reproduzir']({'url': 'ad', 'duracao': 21}, tocar=kw['tocar'], dormir=rt.sleep)
                with patch.object(self.resume, 'guard_transition', side_effect=lambda kodi, path: seen.append((path, rt.now))):
                    receipt = env['exibir_e_devolver'](tocar=rt.play_ad, dormir=rt.sleep,
                                   estado={'caminho': rt.file, 'posicao': 42.125})
                self.assertTrue(receipt['retomada_confirmada'])
                self.assertEqual([path for path, _ in seen], ['ad', 'https://media.invalid/movie.mp4'])
                self.assertGreater(seen[0][1], 1000.)  # not before actual progress
                self.assertIn(('https://media.invalid/movie.mp4', 42.125), rt.seek_calls)
                self.assertEqual(rt.restores, ['https://media.invalid/movie.mp4'])

    def test_refusal_or_no_fill_does_not_touch_any_menu(self):
        rt = media.Runtime('refused')
        env = rt.env()
        with patch.object(self.resume, 'guard_transition') as guard:
            env['reproduzir']({'url': 'ad', 'duracao': 21}, tocar=rt.play_ad, dormir=rt.sleep)
            env['exibir'] = lambda **kwargs: {'exibido': False, 'motivo': 'no-fill'}
            env['exibir_e_devolver'](estado={'caminho': rt.file, 'posicao': 42.125})
        guard.assert_not_called()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path)
    args, rest = parser.parse_known_args()
    ORIGINAL = args.original
    result = unittest.main(argv=[__file__] + rest, exit=False).result
    for test, detail in result.failures + result.errors:
        print('::error title=VAST transition menu regression::' + str(test) + ': ' + detail.strip().splitlines()[-1], flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
