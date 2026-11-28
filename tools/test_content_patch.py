#!/usr/bin/env python3
"""Content-only patch contract tests; no network and no APK needed."""
import ast,base64,importlib.util,json,tempfile,unittest,zlib
from pathlib import Path
from patch_content_links import unpack,repack,transform

FIXTURE='''# Preserve every unrelated byte, including activation/player placeholders.
def license_unchanged():
    return 'unchanged'
def getMovieData(use_cloudrequest=False):
    try:
        if not use_cloudrequest:
            session = create_retry_session() if retry else requests
        elif use_cloudrequest:
            session = cloudrequest.create_scraper(sess=create_retry_session())
        return session
    except Exception:
        return ''
def valide_v2():
    try:
        session = create_retry_session() if retry else requests
        return session
    except Exception:
        return False
def player_unchanged():
    return 'unchanged'
'''

class Patch(unittest.TestCase):
    def test_existing_profile_upgrade_is_local_idempotent_and_preserves_settings(self):
        spec=importlib.util.spec_from_file_location('content_link_patch',Path(__file__).resolve().parent.parent/'android-build/content-links/content_link_patch.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as folder:
            addon=Path(folder)/'plugin.video.BrazucaPlay.Matrix';addon.mkdir()
            (addon/'default.py').write_text(FIXTURE);(addon/'settings.xml').write_text('user state untouched')
            log=[];self.assertTrue(installer.install(addon,log))
            updated=(addon/'default.py').read_bytes();audit=(addon/'smarted-content-delivery.json').read_bytes()
            self.assertTrue(installer.install(addon,log))
            self.assertEqual(updated,(addon/'default.py').read_bytes())
            self.assertEqual(audit,(addon/'smarted-content-delivery.json').read_bytes())
            self.assertEqual((addon/'settings.xml').read_text(),'user state untouched')
            self.assertEqual(installer.unpack(updated.decode())[0],transform(FIXTURE))
            self.assertTrue((addon/'content_network.py').is_file())

    def test_two_scoped_insertions_only(self):
        after=transform(FIXTURE)
        self.assertEqual(after.count('from content_network import prepare_session'),2)
        old=[ast.dump(n) for n in ast.parse(FIXTURE).body if isinstance(n,ast.FunctionDef) and n.name not in ('getMovieData','valide_v2')]
        new=[ast.dump(n) for n in ast.parse(after).body if isinstance(n,ast.FunctionDef) and n.name not in ('getMovieData','valide_v2')]
        self.assertEqual(old,new)
    def test_unknown_session_contract_fails_closed(self):
        with self.assertRaises(ValueError):transform(FIXTURE.replace('create_retry_session() if retry else requests','requests.Session()'))
    def test_nested_wrapper_repack_keeps_original_headers_and_trailers(self):
        source=FIXTURE
        for _ in range(3):source='exec((_)(%r))'%base64.b64encode(zlib.compress(source.encode()))[::-1]
        source='#encoded by Kodi\n_ = lambda __ : __import__(\'zlib\').decompress(__import__(\'base64\').b64decode(__[::-1]))\n'+source+'\n# integrity comment unchanged\n'
        decoded,layers=unpack(source);self.assertEqual(decoded,FIXTURE)
        updated=repack(transform(decoded),layers)
        self.assertTrue(updated.startswith('#encoded by Kodi\n_ = lambda'))
        self.assertTrue(updated.endswith('# integrity comment unchanged\n'))
        self.assertEqual(unpack(updated)[0],transform(FIXTURE))
if __name__=='__main__':unittest.main()
