#!/usr/bin/env python3
"""VAST wrapper pixels/macros/device UA with intercepted HTTP, no real beacons."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET
import test_ads_regressions as media

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = None
UA = 'Kodi/21.3 (Linux; Android 14; Actual-Test-Device)'
PIXEL = 'https://pixels.invalid/i-%s?a=[CACHEBUSTING]&amp;b=%%5Bcachebuster%%5D&amp;c=[RANDOM]&amp;u=[DEVICEUA]&amp;t=[TIMESTAMP]'


def wrapper(next_url, name):
    return ('<VAST><Ad><Wrapper><Impression>'+PIXEL%name+'</Impression><Impression>'+PIXEL%'duplicate'+
        '</Impression><Error>https://pixels.invalid/error?e=[ERRORCODE]</Error><VASTAdTagURI>'+next_url+
        '</VASTAdTagURI><Creatives><Creative><Linear><TrackingEvents><Tracking event="start">https://pixels.invalid/start-'+name+
        '</Tracking></TrackingEvents></Linear></Creative></Creatives></Wrapper></Ad></VAST>')


INLINE = ('<VAST><Ad><InLine><Impression>'+PIXEL%'inline-one'+'</Impression><Impression>'+PIXEL%'inline-two'+
    '</Impression><Creatives><Creative><Linear><Duration>00:00:21</Duration><MediaFiles><MediaFile type="video/mp4">'+
    'https://media.invalid/ad.mp4</MediaFile></MediaFiles></Linear></Creative></Creatives></InLine></Ad></VAST>')


class Tracking(unittest.TestCase):
    def env(self, mode='ended'):
        media.ORIGINAL = ORIGINAL
        self.runtime = media.Runtime(mode)
        env = self.runtime.env()
        env['xbmc'].getUserAgent = lambda:UA
        env['PROFUNDIDADE_WRAPPER'] = 5
        def strip(xml):
            root=ET.fromstring(xml)
            for node in root.iter(): node.tag=node.tag.rsplit('}',1)[-1]
            return ET.tostring(root, encoding='unicode')
        def choose(xml, height=0):
            inline=ET.fromstring(strip(xml)).find('.//InLine')
            if inline is None:return None
            selected=env['_media_escolhido'](inline,height)
            if not selected:return None
            return {'url':selected['url'],'duracao':21,'tipo':'video/mp4',
                    'impressao':[(n.text or '').strip() for n in inline.iter('Impression')], 'eventos':{}, 'errors':[]}
        env.update(sem_namespace=strip,escolher_anuncio=choose,
            tag_do_wrapper=lambda xml: ET.fromstring(strip(xml)).findtext('.//VASTAdTagURI') or '',
            tag_do_vmap=lambda xml:'')
        if ORIGINAL:
            from test_original_ad_patch import load_functions
            original=load_functions(ORIGINAL/'ads_vast.py')
            for name in ('sem_namespace','escolher_anuncio','tag_do_wrapper','tag_do_vmap'):
                env[name]=original[name]
        return env

    def pages(self):
        return {'https://tag.invalid/one':wrapper('https://tag.invalid/two','outer'),
                'https://tag.invalid/two':wrapper('https://tag.invalid/inline','inner'),
                'https://tag.invalid/inline':INLINE}

    def test_nested_wrappers_keep_every_impression_and_duplicate_xml_node(self):
        env=self.env();pages=self.pages()
        result=env['exibir'](tag='https://tag.invalid/one',baixar_tag=pages.get,tocar=self.runtime.play_ad,dormir=self.runtime.sleep)
        self.assertTrue(result['exibido'])
        impressions=[url for url in self.runtime.events if '/i-' in url]
        self.assertEqual(len(impressions),6)
        self.assertEqual(sum('/i-duplicate?' in url for url in impressions),2)
        self.assertEqual(sum('/start-' in url for url in self.runtime.events),2)
        # Send actual Python Requests through an intercepted urlopen. Every
        # XML node must produce a GET with the real Kodi runtime UA.
        requests=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,size):return b''
        def open_url(request,**kwargs):
            requests.append(request);return Response()
        with patch('urllib.request.urlopen',side_effect=open_url):
            self.assertEqual(env['disparar'](impressions),6)
        for request in requests:
            self.assertEqual(request.get_header('User-agent'),UA)
            query=parse_qs(urlsplit(request.full_url).query)
            self.assertRegex(query['a'][0],r'^\d{8}$')
            self.assertEqual(query['a'],query['b']);self.assertEqual(query['a'],query['c'])
            self.assertEqual(query['u'],[UA]);self.assertNotIn('[',request.full_url)

    def test_duplicate_inline_nodes_survive_with_selected_wrappers_only(self):
        env=self.env();pages=self.pages()
        pages['https://tag.invalid/inline']=INLINE.replace('i-inline-two','i-inline-one')
        env['exibir'](tag='https://tag.invalid/one',baixar_tag=pages.get,tocar=self.runtime.play_ad,dormir=self.runtime.sleep)
        self.assertEqual(sum('/i-inline-one?' in url for url in self.runtime.events),2)
        self.assertEqual(sum('/i-' in url for url in self.runtime.events),6)

    def test_no_fill_or_refused_player_never_sends_wrapper_impressions(self):
        for refused in (False,True):
            env=self.env('refused' if refused else 'ended');pages=self.pages()
            if not refused:pages['https://tag.invalid/inline']='<VAST/>'
            result=env['exibir'](tag='https://tag.invalid/one',baixar_tag=pages.get,tocar=self.runtime.play_ad,dormir=self.runtime.sleep)
            self.assertFalse(result['exibido'])
            self.assertFalse(any('/i-' in url for url in self.runtime.events))
            self.assertEqual(sum('/error?e=' in url for url in self.runtime.events),2)

    def test_wrapper_cycle_sends_error_not_impression(self):
        env=self.env();pages=self.pages();pages['https://tag.invalid/two']=wrapper('https://tag.invalid/one','cycle')
        result=env['exibir'](tag='https://tag.invalid/one',baixar_tag=pages.get,tocar=self.runtime.play_ad,dormir=self.runtime.sleep)
        self.assertEqual(result['motivo'],'wrapper-ciclico')
        self.assertEqual(sum('/error?e=302' in url for url in self.runtime.events),2)
        self.assertFalse(any('/i-' in url for url in self.runtime.events))

    def test_macro_aliases_encoded_error_and_real_ua_no_fabricated_model(self):
        import ads_tracking
        query=parse_qs(urlsplit(ads_tracking.expand('https://p.invalid/?a=[CACHEBUSTING]&b=%%CACHEBUSTER%%&e=%5BERRORCODE%5D&ua=[DEVICEUA]',405,UA)).query)
        self.assertEqual(query['a'],query['b']);self.assertEqual(query['e'],['405']);self.assertEqual(query['ua'],[UA])
        self.assertEqual(ads_tracking.device_user_agent(types.SimpleNamespace(getUserAgent=lambda:UA)),UA)
        fallback=ads_tracking.device_user_agent(types.SimpleNamespace(getCondVisibility=lambda key:True))
        self.assertEqual(fallback,'Kodi (Android)');self.assertNotIn('Pixel',fallback)

    def test_reference_python_follows_wrappers_with_identical_macro_helper(self):
        reference=ROOT/'kodi-addon/script.smartedtv.welcome'
        self.assertEqual((reference/'ads_tracking.py').read_bytes(), (ROOT/'android-build/ads-patches/ads_tracking.py').read_bytes())
        spec=importlib.util.spec_from_file_location('reference_vast_tracking_test',reference/'vast.py')
        vast=importlib.util.module_from_spec(spec);spec.loader.exec_module(vast)
        pages=self.pages();vast.fetch_vast=lambda url,**kw:pages[url]
        result=vast.play_preroll_or_fallback('https://tag.invalid/one')
        self.assertEqual(result['outcome'],'ad');self.assertEqual(len(result['ad']['impressions']),6)
        captured=[]
        class Response:
            def close(self):pass
        def open_url(request,**kwargs):captured.append(request);return Response()
        with patch.dict(sys.modules,{'xbmc':types.SimpleNamespace(getUserAgent=lambda:UA)}), patch('urllib.request.urlopen',side_effect=open_url):
            for url in result['ad']['impressions']:vast.fire(url)
        self.assertEqual(len(captured),6)
        self.assertTrue(all(req.get_header('User-agent')==UA for req in captured))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--original',type=Path)
    args,rest=parser.parse_known_args();ORIGINAL=args.original
    sys.path.insert(0,str(ORIGINAL or ROOT/'android-build/ads-patches'))
    result=unittest.main(argv=[__file__]+rest,exit=False).result
    for test,detail in result.failures+result.errors:
        safe=(str(test)+': '+detail.strip().splitlines()[-1]).replace('%','%25')
        print('::error title=VAST pixel regression::'+safe,flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
