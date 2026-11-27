#!/usr/bin/env python3
"""APK actions with browser/Android doubles; never download/install in tests."""
import argparse
import ast
import json
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL = json.loads((ROOT / 'android-build/base-apk.json').read_text())['url']
ORIGINAL = None


class Links(unittest.TestCase):
    def env(self):
        source = ROOT / 'android-build/ads-patches/vip.py'
        names = {n.name for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef)}
        if ORIGINAL:
            source = ORIGINAL / 'vip.py'
        functions = [n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.calls = []
        self.texts = []
        env = {'APK': OFFICIAL, 'abrir_url': lambda *args: self.calls.append(args) or True,
               '_compartilhar_texto': lambda message: self.texts.append(message) or True,
               'xbmcgui': types.SimpleNamespace(Dialog=lambda: types.SimpleNamespace(
                   textviewer=lambda *args: self.calls.append(args)))}
        if ORIGINAL:
            # Validate the actual patched constants, not only the function stubs.
            tree = ast.parse(source.read_text())
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in ('APK', 'DROPBOX_URL'):
                            self.assertEqual(ast.literal_eval(node.value), OFFICIAL)
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), env)
        return env

    def test_download_update_and_resolver_use_only_official_universal_apk(self):
        env = self.env()
        for device in ('mobile', 'tvbox', 'projetor'):
            env['eh_tv'] = lambda: device != 'mobile'
            self.assertEqual(env['resolver_apk_publicado'](), (OFFICIAL, 'dropbox-oficial'))
            self.assertTrue(env['open_apk_download']())
            self.assertTrue(env['procurar_atualizacao']())
        self.assertEqual(len(self.calls), 6)
        self.assertTrue(all(call[0] == OFFICIAL for call in self.calls))

    def test_original_welcome_share_button_and_long_press_share_official_link(self):
        env = self.env()
        self.assertTrue(env['abrir_dropbox']())  # existing welcome control 121
        self.assertTrue(env['compartilhar']())
        self.assertTrue(all(OFFICIAL in message for message in self.texts))
        self.assertEqual(self.calls, [])

    def test_share_without_android_target_displays_link_without_recursive_fallback(self):
        env = self.env()
        env['_compartilhar_texto'] = lambda *args: False
        self.assertTrue(env['abrir_dropbox']())
        self.assertEqual(len(self.calls), 1)
        self.assertIn(OFFICIAL, self.calls[0][1])

    def test_reference_native_controls_delegate_to_shared_apk_actions(self):
        import sys
        from unittest.mock import patch
        path = ROOT / 'kodi-addon/script.smartedtv.welcome/default.py'
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        calls = []
        vip = types.SimpleNamespace(compartilhar=lambda: calls.append('share'),
                                    open_apk_download=lambda: calls.append('download'))
        env = {'xbmcgui': types.SimpleNamespace(WindowXMLDialog=object)}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), env)
        dialog = env['WelcomeDialog']()
        with patch.dict(sys.modules, {'vip': vip}):
            for control in (121, 122, 123):
                dialog.onClick(control)
        self.assertEqual(calls, ['share', 'download', 'download'])

    def test_only_apk_actions_are_replaced_not_vip_validation_or_payment(self):
        nodes = ast.parse((ROOT / 'android-build/ads-patches/vip.py').read_text()).body
        self.assertEqual({n.name for n in nodes if isinstance(n, ast.FunctionDef)},
            {'resolver_apk_publicado', 'open_apk_download', 'procurar_atualizacao', 'compartilhar', 'abrir_dropbox'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path)
    args, rest = parser.parse_known_args()
    ORIGINAL = args.original
    unittest.main(argv=[__file__] + rest)
