#!/usr/bin/env python3
"""Actual delayed loopback HTTP with native baixar/exibir; NOT live provider fill.
Only destination routing is intercepted. No downloader/clock/player simulation:
clock and HTTP timeout behavior are real; native player is replaced by capture.
"""
import argparse,functools,hashlib,json,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urlencode
from urllib.request import Request,urlopen
from unittest.mock import patch
from vast_visual_lab import read_module,TAG,now
from vast_selection_cases import wrapper,VALID,NEXT


def run(apk,work):
    env,kodi=read_module(apk,work);events=[];requests=[];selected=[]
    kodi.log=lambda line,*a:events.append(dict(utc=now(),native_log=line))
    pages={TAG:wrapper(NEXT),NEXT:wrapper(NEXT+'2'),NEXT+'2':VALID}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url=parse_qs(urlsplit(self.path).query).get('url',[''])[0]
            time.sleep(3.0)
            body=pages.get(url,'<VAST/>').encode()
            self.send_response(200);self.send_header('Content-Type','application/xml');self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def routed(request,**kwargs):
        row=dict(utc=now(),requested_url=request.full_url,timeout=kwargs.get('timeout'),headers=dict(request.header_items()))
        requests.append(row)
        local='http://127.0.0.1:'+str(server.server_port)+'/?'+urlencode(dict(url=request.full_url))
        try:
            response=urlopen(Request(local,headers=dict(request.header_items())),**kwargs)
            row.update(http_status=response.status,utc_response=now())
            return response
        except Exception as e:
            row.update(error=type(e).__name__,utc_response=now());raise
    def player(ad,**kw):
        selected.append(ad);return dict(exibido=False,motivo='selected-native-player-not-run')
    env['_disparar_eventos']=lambda urls:0;env['reproduzir']=player
    start=time.monotonic()
    try:
        with patch('urllib.request.urlopen',side_effect=routed):receipt=env['exibir'](tag=TAG)
        return dict(kind='controlled-real-loopback-HTTP-not-provider',seconds_per_hop=3.0,
            elapsed_seconds=round(time.monotonic()-start,3),requests=requests,selected=bool(selected),
            native_ads_played=0,receipt=receipt,events=events,
            pages={url:dict(xml=xml,sha256=hashlib.sha256(xml.encode()).hexdigest()) for url,xml in pages.items()})
    finally:server.shutdown();server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--historical',type=Path,required=True);p.add_argument('--current',type=Path,required=True);p.add_argument('--after',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result={name:run(apk,a.out.parent/(name+'-http-modules')) for name,apk in [('historical',a.historical),('current',a.current)]+([('after',a.after)] if a.after else [])}
    assert result['historical']['selected'];assert not result['current']['selected']
    if a.after:assert result['after']['selected']
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    from inspect_vast_history_startup import transfer
    transfer('VAST HTTP budget chunks',result)
    print('::notice title=VAST HTTP budget summary::'+json.dumps({role:dict(selected=case['selected'],elapsed=case['elapsed_seconds'],requests=len(case['requests']),timeouts=[r.get('timeout') for r in case['requests']]) for role,case in result.items()}))
