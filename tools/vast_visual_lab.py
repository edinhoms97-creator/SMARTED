#!/usr/bin/env python3
"""Isolated visual VAST lab. Reads APK Python; never modifies app/profile/player.
Live runs are bounded to THREE new-tag root calls. Pixels are NEVER sent here.
"""
import argparse
import ast
import base64
import datetime
import gzip
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import re
import shutil
import ssl
import sys
import time
import types
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
from unittest.mock import patch
import zipfile

TAG = 'https://vast.yomeno.xyz/vast?spot_id=1508249'
PREFIX = 'assets/addons/service.smarted.bootstrap/'
BASE_SHA = '2b64c443f42902cb07031db1106137a59d852ae39bb8fbd8b9379b8a6d2682bc'
INLINE = '''<VAST version="3.0"><Ad id="lab-fixture"><InLine><AdSystem>ISOLATED FIXTURE NOT CLICKADILLA</AdSystem><AdTitle>Public test clip</AdTitle><Impression>https://pixels.invalid/impression?token=secret</Impression><Creatives><Creative><Linear><Duration>00:00:05</Duration><TrackingEvents><Tracking event="complete">https://pixels.invalid/complete?token=secret</Tracking></TrackingEvents><MediaFiles><MediaFile type="video/mp4" delivery="progressive" width="640" height="360">https://fixture.invalid/creative.mp4?token=secret</MediaFile></MediaFiles></Linear></Creative></Creatives></InLine></Ad></VAST>'''


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')


def safe_url(url):
    try:
        p = urlsplit(str(url))
        if p.scheme not in ('http', 'https'): return '<non-http-url>'
        host = p.hostname or ''
        if p.port: host += ':'+str(p.port)
        query = urlencode([(k, v if k.lower() in ('spot_id', 'v', 'version') else '[REDACTED]') for k,v in parse_qsl(p.query, keep_blank_values=True)])
        path = re.sub(r'(?i)(/(?:token|auth|signature|key)/)[^/]+', r'\1[REDACTED]', p.path)
        return urlunsplit((p.scheme, host, path, query, ''))
    except Exception:
        return '<redacted-url>'


def sanitize(text):
    text = re.sub(r'https?://[^\s<>"\']+', lambda m: safe_url(html.unescape(m.group(0))).replace('&','&amp;'), str(text))
    text = re.sub(r'(?i)(bearer\s+)[\w.\-]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:token|password|authorization|cookie|api_key)\s*[=:]\s*)[^\s<>"\']+', r'\1[REDACTED]', text)
    return text


def read_module(apk, work):
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        for name in archive.namelist():
            if name.startswith(PREFIX) and name.endswith('.py'):
                (work/Path(name).name).write_bytes(archive.read(name))
    sys.path.insert(0,str(work))
    kodi = types.SimpleNamespace(Player=object, LOGINFO=1, LOGWARNING=2,
        log=lambda *a: None, getInfoLabel=lambda *a:'', getCondVisibility=lambda *a:False,
        getUserAgent=lambda:'Kodi lab: native API stub; not an Android playback claim')
    stubs = {'xbmc':kodi, 'xbmcgui':types.SimpleNamespace(), 'xbmcvfs':types.SimpleNamespace()}
    with patch.dict(sys.modules,stubs):
        env = {'__name__':'isolated_vast_module','__file__':str(work/'ads_vast.py')}
        exec(compile((work/'ads_vast.py').read_text(),env['__file__'],'exec'),env)
    return env, kodi


class Lab:
    def __init__(self, apk, out, browser, live, selection=False, expect_selection=False):
        self.out,self.browser,self.live = out,browser,live
        self.selection,self.expect_selection=selection,expect_selection
        out.mkdir(parents=True,exist_ok=True)
        self.env,self.kodi=read_module(apk,out.parent/'native-modules')
        self.results=[]
        self.real_open=urlopen
        self.current=None
        self.kodi.log=lambda line,*args: self.event('production-native-log',message=sanitize(line)) if self.current else None
        self.env['_disparar_eventos']=lambda urls: self.event('tracking-suppressed-in-lab',pixel_count=len(urls or [])) or 0
        # Production selector/Wrapper flow, not the native player, runs in this lab.
        self.env['reproduzir']=self.selected
        self.raw_media=None

    def event(self, stage, **values):
        row={'utc':now(),'attempt':self.current['id'],'stage':stage,**values}
        self.current['events'].append(row)
        self.save()
        return row

    def save(self):
        folder=self.out/self.current['id'];folder.mkdir(exist_ok=True)
        (folder/'result.json').write_text(json.dumps(self.current,ensure_ascii=False,indent=2))
        (folder/'events.jsonl').write_text('\n'.join(json.dumps(e,ensure_ascii=False) for e in self.current['events'])+'\n')

    def snap(self, name, video=None):
        page=self.browser.new_page(viewport={'width':1100,'height':820})
        data=html.escape(json.dumps(self.current,ensure_ascii=False,indent=2))
        page.set_content('<html><meta charset="utf-8"><style>body{font:16px system-ui;background:#101826;color:#dbeafe;margin:30px}h1{color:#5eead4}pre{white-space:pre-wrap;font:13px monospace;background:#182438;padding:18px}video{width:600px;max-height:360px}</style><h1>SMARTEDTV · VAST isolated lab</h1><h2>'+html.escape(self.current['id']+' · '+name)+'</h2><p>Real network and controlled fixtures are labeled separately. Browser playback is NOT Kodi validation. No tracking pixels sent.</p><pre>'+data+'</pre></html>')
        playback=None
        if video:
            from base64 import b64encode
            # Serve clip from a short-lived loopback HTTP server in the runner.
            page.evaluate('''src=>{const v=document.createElement('video');v.controls=true;v.muted=true;v.autoplay=true;v.src=src;document.body.prepend(v);v.play().catch(()=>{});}''',video)
            page.wait_for_function("()=>{const v=document.querySelector('video');return v.currentTime>0.2||v.error}",timeout=10000)
            playback=page.evaluate('''()=>{const v=document.querySelector('video');return {current_time:v.currentTime,paused:v.paused,ready_state:v.readyState,width:v.videoWidth,height:v.videoHeight,error:v.error?{code:v.error.code}:null};}''')
            self.current['browser_playback']=playback
            self.event('browser-playback-result',**playback)
        folder=self.out/self.current['id']
        page.screenshot(path=str(folder/(name+'.png')),full_page=True)
        # Small real screenshot for workspace preview, not an AI-generated image.
        page.screenshot(path=str(folder/(name+'.jpg')),type='jpeg',quality=40)
        page.close()
        return playback

    def selected(self, ad, **kwargs):
        self.selected_ad=ad
        self.raw_media=ad.get('url')
        self.current['media']={k:sanitize(v) if isinstance(v,str) else v for k,v in ad.items() if k in ('url','tipo','duracao','id')}
        self.event('production-selector-accepted-media',media=self.current['media'])
        return {'exibido':False,'motivo':'lab-selected-native-player-not-invoked'}

    def intercepted_open(self, request, **kwargs):
        url=request.full_url if hasattr(request,'full_url') else str(request)
        folder=self.out/self.current['id']
        number=len(self.current['requests'])+1
        record={'hop':number,'utc_start':now(),'effective_requested_url':safe_url(url),
                'timeout_seconds':kwargs.get('timeout'),'headers':{k:sanitize(v) for k,v in request.header_items() if k.lower() in ('user-agent','accept','accept-language','accept-encoding')}}
        self.current['requests'].append(record)
        self.event('http-request',request=record)
        try:
            if self.current['mode']=='fixture-network-error':raise URLError(ConnectionError('controlled fixture'))
            if self.current['mode']=='fixture-timeout':raise TimeoutError('controlled fixture')
            if self.current['mode'].startswith('fixture'):
                import io
                body=self.fixture_body.get(url) if isinstance(self.fixture_body,dict) else self.fixture_body
                if body is None:raise URLError('unmapped controlled URL')
                data=body.encode()
                class Response(io.BytesIO):
                    status=200;headers={'Content-Type':'application/xml'}
                    def getcode(self):return 200
                    def geturl(self):return url
                response=Response(data)
            else:
                response=self.real_open(request,**kwargs)
            record['http_status']=response.getcode()
            record['response_effective_url']=safe_url(response.geturl())
            record['response_headers']={k:v for k,v in response.headers.items() if k.lower() in ('content-type','content-length','date','cache-control','age')}
        except Exception as exc:
            record.update(utc_end=now(),error_class=type(exc).__name__,http_status=getattr(exc,'code',None),timeout=isinstance(getattr(exc,'reason',exc),TimeoutError))
            if isinstance(exc,HTTPError):
                body=exc.read(2*1024*1024)
                record['body_sha256']=hashlib.sha256(body).hexdigest()
                (folder/f'http-{number:02d}-error.txt').write_text(sanitize(body.decode(errors='replace')))
            self.event('http-error',details=record)
            raise
        lab=self
        class Capture:
            def __init__(self):self.data=bytearray()
            def __enter__(self):response.__enter__();return self
            def __exit__(self,*args):
                raw=bytes(self.data);record.update(utc_end=now(),body_bytes=len(raw),body_sha256=hashlib.sha256(raw).hexdigest())
                (folder/f'http-{number:02d}-response.xml').write_text(sanitize(raw.decode(errors='replace')))
                lab.event('http-response',details=record)
                return response.__exit__(*args)
            def read(self,size=-1):
                data=response.read(size);self.data.extend(data);return data
        return Capture()

    def attempt(self, number, label, mode, body=None):
        self.current={'id':f'{number:03d}','label':label,'mode':mode,'content_id':f'content-{number}',
            'utc_start':now(),'requested_root_url':TAG,'requests':[],'events':[],
            'tracking_policy':'suppressed in lab; no invented impressions; native player unmodified'}
        self.raw_media=None
        self.snap('01-request-planned')
        self.fixture_body=body
        with patch('urllib.request.urlopen',side_effect=self.intercepted_open):
            receipt=self.env['exibir'](tag=TAG)
        self.current['receipt']=receipt
        reason=receipt.get('motivo')
        self.current['classification']=('media-selected' if self.raw_media else 'empty-vast' if reason in ('no-fill','no-fill-ou-sem-midia') else reason)
        self.event('production-entry-returned',classification=self.current['classification'],receipt=receipt)
        self.snap('02-http-and-xml')
        self.snap('03-media-selection')
        video=None
        if self.raw_media:
            try:
                if mode.startswith('fixture'):
                    # Local deterministic VIDEO TEST PATTERN, never provider inventory.
                    import imageio_ffmpeg, subprocess
                    fixture=self.out/'fixture-test-pattern.mp4'
                    if not fixture.exists():
                        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-f','lavfi',
                            '-i','testsrc2=size=640x360:rate=25','-t','5','-an',
                            '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(fixture)],
                            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                    data=fixture.read_bytes()
                else:
                    media_url=self.raw_media
                    headers={'User-Agent':self.current['requests'][0]['headers'].get('User-agent','Mozilla/5.0')}
                    if not media_url.startswith(('https://','http://')):raise ValueError('non-http media')
                    with self.real_open(Request(media_url,headers=headers),timeout=15) as response:
                        data=response.read(24*1024*1024+1)
                        if len(data)>24*1024*1024:raise ValueError('lab media size cap')
                if b'ftyp' not in data[:48]:raise ValueError('not a directly downloadable MP4; native Kodi capability not inferred')
                media_path=self.out/self.current['id']/'creative.mp4';media_path.write_bytes(data)
                video=f'http://127.0.0.1:{self.port}/{self.current["id"]}/creative.mp4'
                self.event('media-delivered-to-browser',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),fixture=mode.startswith('fixture'))
            except Exception as exc:
                self.event('lab-media-playback-unavailable',error_class=type(exc).__name__,http_status=getattr(exc,'code',None))
        self.snap('04-playback-result',video)
        self.current['utc_end']=now();self.save()
        self.results.append(self.current)
        return self.current

    def run(self):
        import functools
        from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
        import threading
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(self.out)))
        self.port=server.server_port
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            if self.live:
                for i in range(1,4):self.attempt(i,f'Live new tag / independent content {i}','live')
            else:
                self.attempt(1,'Offline call one','fixture-valid',INLINE)
                self.attempt(2,'Offline call two','fixture-valid',INLINE)
                self.attempt(3,'Offline call three','fixture-valid',INLINE)
            self.attempt(4,'Different content A / available ad fixture','fixture-valid',INLINE)
            self.attempt(5,'Different content B / available ad fixture','fixture-valid',INLINE)
            self.attempt(6,'Empty response fixture','fixture-empty','<VAST version="3.0"/>')
            self.attempt(7,'Connection error fixture','fixture-network-error')
            self.attempt(8,'Timeout fixture','fixture-timeout')
            self.attempt(9,'New call AFTER empty/error/timeout, same module process','fixture-valid',INLINE)
            assert all(r.get('browser_playback',{}).get('current_time',0)>0 and not r['browser_playback']['error'] for r in self.results if r['mode']=='fixture-valid'), 'Controlled test pattern did not play'
            assert self.results[-1].get('media'), 'Previous empty/failure blocked new call inside exibir'
            if self.selection:
                from vast_selection_cases import CASES
                for number,case in enumerate(CASES,10):
                    result=self.attempt(number,case['name'],'fixture-selection',case['pages'])
                    actual=bool(result.get('media'))
                    result['selection_expected']=case['selected']
                    result['selection_matches_expectation']=actual==case['selected']
                    if actual:
                        ad=self.selected_ad
                        checks={
                            'browser_test_pattern_advanced':result.get('browser_playback',{}).get('current_time',0)>0,
                            'correct_duration':case.get('duration') is None or ad.get('duracao')==case['duration'],
                            'selected_branch_impressions':not case.get('impressions') or ad.get('impressao')==case['impressions'],
                            'no_discarded_branch_impression':not case.get('forbidden_impression') or case['forbidden_impression'] not in ad.get('impressao',[])}
                        result['selection_checks']=checks
                        result['selection_matches_expectation'] &= all(checks.values())

                    self.save()
                mismatches=[r['label'] for r in self.results if r.get('selection_matches_expectation') is False]
                self.event('selection-matrix-complete',mismatches=mismatches)
                if self.expect_selection:assert not mismatches, 'Selection failures: '+str(mismatches)

            assert all(r['requests'] for r in self.results), 'A direct exibir call skipped HTTP'
            summary={'utc':now(),'tag':TAG,'real_root_calls':3 if self.live else 0,
                     'scope':'Production exibir/baixar/parser; native player not executed; browser is lab-only; tracking suppressed',
                     'attempts':self.results,'all_direct_calls_reached_transport':True}
            (self.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
            links=''.join(f'<li><a href="{r["id"]}/result.json">{r["id"]} {html.escape(r["label"])}</a> — {html.escape(r["classification"])} · <a href="{r["id"]}/04-playback-result.png">screenshot</a></li>' for r in self.results)
            (self.out/'index.html').write_text('<html><meta charset="utf-8"><h1>SMARTEDTV VAST evidence</h1><p>Open files without rerunning tests. Live and controlled fixtures are labeled. Sensitive query parameters are redacted; raw XML SHA-256 retained. No tracking sent. Browser is not Kodi.</p><ul>'+links+'</ul></html>')
            (self.out/'README.md').write_text('# VAST evidence\n\nOpen index.html and each numbered folder. Four real browser screenshots, result.json, timestamped events.jsonl and sanitized full HTTP XML are saved per attempt. \n\nOnly 001–003 are real Clickadilla root requests when real_root_calls=3. 004 and higher are CONTROLLED FIXTURES, not provider availability proof. Fixture media is a locally generated test pattern, NOT a real ad. Player is Chromium in an isolated lab, NOT Kodi. No tracking pixels are requested. URLs are sanitized and response raw SHA-256 is kept. No old-tag fallback.\n')
            # Transfer compact text evidence and a true screenshot to workspace.
            payload={'summary':summary,'responses':{str(p.relative_to(self.out)):p.read_text() for p in self.out.glob('*/*.xml')}}
            encoded=base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()
            (self.out/'transfer.txt').write_text(encoded)
            for i in range(0,len(encoded),3500):
                if i//3500>=8:break
                print('::notice title=VAST lab text chunks::'+json.dumps({'part':i//3500,'total':(len(encoded)+3499)//3500,'data':encoded[i:i+3500]}))
            return summary
        finally:server.shutdown();server.server_close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--apk',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--live',action='store_true');p.add_argument('--selection',action='store_true');p.add_argument('--expect-selection',action='store_true');args=p.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        executable=shutil.which('google-chrome') or shutil.which('chromium')
        browser=pw.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox'])
        try:Lab(args.apk,args.out,browser,args.live,args.selection,args.expect_selection).run()
        finally:browser.close()

if __name__=='__main__':main()
