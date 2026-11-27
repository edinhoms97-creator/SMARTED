#!/usr/bin/env python3
"""Offline regression of the single-function patch; optional exact APK input."""
import argparse
import ast
from pathlib import Path
import sys
import types
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import patch
from patch_vast_single_function import transform, audit, AD
from vast_visual_lab import TAG, INLINE

p=argparse.ArgumentParser();p.add_argument('--apk',type=Path);args,rest=p.parse_known_args()
if args.apk:
    with zipfile.ZipFile(args.apk) as z: ORIGINAL=z.read(AD).decode()
else:
    # Derive the baseline entry from its reviewed historical overlay.
    ORIGINAL=Path('android-build/confirmed-tracking/ads_vast.py').read_text()
    ORIGINAL=ORIGINAL.replace('    import xml.etree.ElementTree as _ET','    from ads_openings import emit\n    import xml.etree.ElementTree as _ET')
UPDATED=transform(ORIGINAL)

class EntryTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.requests=[];self.played=[];self.pixels=[]
        fn=next(n for n in ast.parse(UPDATED).body if isinstance(n,ast.FunctionDef) and n.name=='exibir')
        code=ast.Module(body=[fn],type_ignores=[])
        self.env=dict(TEMPO_MAXIMO_ANUNCIO=45,PROFUNDIDADE_WRAPPER=5,xbmc=object(),_agora=lambda:0,
            sem_namespace=lambda d:d,escolher_anuncio=self.select,tag_do_wrapper=self.wrapper,
            tag_do_vmap=lambda d:None,_disparar_eventos=lambda urls:self.pixels.extend(urls),reproduzir=self.play)
        exec(compile(code,'<actual-patched-entry>','exec'),self.env)
        self.mods=patch.dict(sys.modules,{'ads_openings':types.SimpleNamespace(emit=lambda kodi,stage,**fields:self.events.append(dict(stage=stage,**fields))),
            'ads_tracking':types.SimpleNamespace(expand=lambda u,**k:u,device_user_agent=lambda k:'Kodi')})
        self.mods.start();self.addCleanup(self.mods.stop)
    def select(self,data,height):
        media=ET.fromstring(data).find('.//MediaFile')
        if media is not None and media.get('type')=='video/mp4':return dict(url=media.text,tipo='video/mp4',duracao=5)
    def wrapper(self,data):return ET.fromstring(data).findtext('.//VASTAdTagURI')
    def play(self,ad,**kw):self.played.append(ad);return dict(exibido=True,motivo='mock-only')
    def call(self,data=INLINE,tag='https://old.invalid/old-spot'):
        def fetch(url):
            self.requests.append(url)
            if isinstance(data,Exception):raise data
            return data
        return self.env['exibir'](tag=tag,baixar_tag=fetch)
    def test_only_function_bytes_change(self):audit(ORIGINAL,UPDATED)
    def test_first_second_third_fresh_request_and_attempt_id(self):
        receipts=[self.call() for _ in range(3)]
        self.assertEqual(self.requests,[TAG]*3)
        self.assertEqual(len({r['vast_attempt_id'] for r in receipts}),3)
        self.assertEqual(len(self.played),3)
    def test_empty_error_timeout_do_not_block_next(self):
        for data in ('<VAST/>','',ConnectionError(),TimeoutError(),'<bad'):
            with self.subTest(data=str(data)):
                self.assertFalse(self.call(data)['exibido'])
                self.assertTrue(self.call()['exibido'])
        self.assertEqual(len(self.requests),10)
    def test_no_automatic_old_tag_fallback_even_empty_input(self):
        self.call('<VAST/>',tag='');self.assertEqual(self.requests,[TAG])
    def test_distinguish_empty_from_unusable_media_without_changing_pixels(self):
        self.call('<VAST/>')
        bad=INLINE.replace('video/mp4','application/unsupported')
        self.call(bad)
        rows=[e for e in self.events if e['stage']=='vast-selection-diagnostic']
        self.assertEqual([r['reason'] for r in rows],['empty-vast','ad-without-supported-media'])
        self.assertFalse(self.played);self.assertFalse(self.pixels)
    def test_repeated_creative_is_not_discarded(self):
        self.assertTrue(self.call()['exibido']);self.assertTrue(self.call()['exibido'])
        self.assertEqual(len(self.played),2)
    def test_cycle_guard_is_per_invocation_not_session(self):
        wrapper='<VAST><Ad><Wrapper><VASTAdTagURI>'+TAG+'</VASTAdTagURI></Wrapper></Ad></VAST>'
        self.assertEqual(self.call(wrapper)['motivo'],'wrapper-ciclico')
        self.assertTrue(self.call()['exibido'])
    def test_wrapper_tracking_and_player_arguments_preserved(self):
        outer='<VAST><Ad><Wrapper><VASTAdTagURI>https://fixture.invalid/next</VASTAdTagURI><Impression>https://pixels.invalid/imp</Impression><Error>https://pixels.invalid/error</Error><TrackingEvents><Tracking event="complete">https://pixels.invalid/complete</Tracking></TrackingEvents></Wrapper></Ad></VAST>'
        responses=iter((outer,INLINE))
        result=self.env['exibir'](baixar_tag=lambda url:next(responses))
        self.assertTrue(result['exibido']);ad=self.played[0]
        self.assertIn('https://pixels.invalid/imp',ad['impressao'])
        self.assertIn('https://pixels.invalid/error',ad['errors'])
        self.assertIn('https://pixels.invalid/complete',ad['eventos']['complete'])

if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+rest)
