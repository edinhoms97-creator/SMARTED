#!/usr/bin/env python3
"""Exact original/patched content functions with REAL HTTP; no player/ad calls.
Native DNS on runner != user's cellular DNS. Fault-injected DNS is separate.
"""
import argparse,ast,base64,hashlib,json,re,socket,sys,time,types,zipfile
from pathlib import Path
from urllib.parse import urlparse,urljoin
import urllib.parse as urllib
import requests
from unittest.mock import patch
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from patch_content_links import unpack,ENTRY,ROOT
from inspect_content_links import transfer

class EmptyCache:
    def get_cache(self,*a):return None
    def save_cache(self,*a):pass


def environment(source,folder):
    trace=[];dialogs=[]
    class Dialog:
        def select(self,title,options):
            dialogs.append(dict(title=title,options=options));return 0 if options else -1
        def ok(self,*args):dialogs.append(dict(error=args))
    tree=ast.parse(source);env=dict(json=json,re=re,base64=base64,urllib=urllib,urlparse=urlparse,
        requests=requests,time=time,HTTPAdapter=HTTPAdapter,Retry=Retry,cache_manager=EmptyCache(),
        hash_url=lambda url:hashlib.sha256(url.encode()).hexdigest(),TIMEOUT_DEFAULT=(5,10),
        sec_ch_ua='"Chromium";v="148"',useragent='Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
        OVERFLIXTV_HOST='www.overflix.download',xbmcgui=types.SimpleNamespace(Dialog=Dialog),notify=lambda *a:None)
    # Execute definitions only; no addon initialization, router or player execution.
    wanted={'getMovieData','create_retry_session','update_dict','overflix_domain','overflix_resolver'}
    definitions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    exec(compile(ast.Module(body=definitions,type_ignores=[]),'<exact-content-functions>','exec'),env)
    original=env['getMovieData']
    def get(url,*args,**kwargs):
        start=time.monotonic();result=original(url,*args,**kwargs)
        row=dict(host=urlparse(url).hostname,path=urlparse(url).path,elapsed=round(time.monotonic()-start,3),nonempty=bool(result))
        if isinstance(result,str):
            row['bytes']=len(result.encode());row['sha256']=hashlib.sha256(result.encode()).hexdigest()
            if 'do=playerData' in url:
                try:
                    data=json.loads(result);row['json_keys']=list(data);row['server_fields_present']='servers_dub' in data
                except ValueError:row['invalid_json']=True
        trace.append(row);return result
    env['getMovieData']=get
    return env,trace,dialogs


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    # Test new module from the actual output APK, not an unrelated source copy.
    module_dir=a.out.parent/'modules';module_dir.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.after) as z:
        from patch_content_links import NEW
        (module_dir/'content_network.py').write_bytes(z.read(NEW))
    sys.path.insert(0,str(module_dir))
    report=dict(kind='real-HTTP-exact-function-extraction-not-Android-playback',native_plays=0,versions={})
    discovered=None
    for role,apk in (('before',a.base),('after',a.after)):
        with zipfile.ZipFile(apk) as z:source,_=unpack(z.read(ENTRY).decode())
        env,trace,dialogs=environment(source,a.out.parent)
        if discovered is None:
            home=env['getMovieData']('https://'+env['OVERFLIXTV_HOST'])
            links=list(dict.fromkeys(urljoin('https://www.overflix.download/',x) for x in re.findall(r'href=["\x27]([^"\x27]+)',home)))
            movies=[x for x in links if '/filmes/online/' in x]
            series=[x for x in links if '/series/online/' in x]
            discovered=[]
            if movies:discovered.extend(('movie',x) for x in movies[:2])
            if series:
                page=env['getMovieData'](series[0]);episodes=list(dict.fromkeys(urljoin(series[0],x) for x in re.findall(r'href=["\x27]([^"\x27]+)',page) if '/episodios/online/' in x))
                discovered.extend(('episode',x) for x in episodes[:2])
        rows=[]
        for kind,url in discovered or []:
            reference=('movie2='+url.rstrip('/').split('/')[-1]) if kind=='movie' else 'serie3='+url
            start=time.monotonic();value=env['overflix_resolver'](reference)
            row=dict(kind=kind,catalog_url=url,resolver_selected=bool(value and value!='stop'),elapsed=round(time.monotonic()-start,3),embed_host=urlparse(value).hostname if value and value!='stop' else None)
            # Only metadata/embed availability. Never call Kodi or count a play.
            if row['resolver_selected']:
                try:
                    r=requests.get(value,timeout=(5,10),headers={'User-Agent':env['useragent']})
                    row.update(embed_http_status=r.status_code,embed_bytes=len(r.content),embed_final_host=urlparse(r.url).hostname)
                except requests.RequestException as e:row['embed_error']=type(e).__name__
            rows.append(row)
        report['versions'][role]=dict(cases=rows,trace=trace,dialogs=dialogs,selected=sum(x['resolver_selected'] for x in rows))
    import content_network
    # DNS fault injection only; the fallback DNS HTTPS, content TLS and provider
    # JSON requests below are REAL network requests, not fixture responses.
    content_network._CACHE.clear()
    env,trace,dialogs=environment(source,a.out.parent)
    rows=[]
    def unavailable():
        def fail(*args):raise socket.gaierror(socket.EAI_NONAME,'simulated Android resolver unavailable')
        return fail
    with patch.object(content_network,'_native_resolver',side_effect=unavailable), patch.object(content_network,'_https_dns',wraps=content_network._https_dns) as actual_doh:
        for kind,url in discovered or []:
            reference=('movie2='+url.rstrip('/').split('/')[-1]) if kind=='movie' else 'serie3='+url
            start=time.monotonic();value=env['overflix_resolver'](reference)
            rows.append(dict(kind=kind,native_dns_failure_injected=True,real_https_dns_and_provider=True,selected=bool(value and value!='stop'),elapsed=round(time.monotonic()-start,3)))
    report['after_forced_dns_failure']=dict(cases=rows,trace=trace,dialogs=dialogs,https_dns_calls=actual_doh.call_count,hosts=[call.args[0] for call in actual_doh.call_args_list])
    if not actual_doh.called:raise RuntimeError('DNS fallback was not exercised; do not label this a recovery test')
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
    transfer('Content actual before after requests',report)
    if not discovered:raise RuntimeError('No live catalog samples discovered; cannot claim link tests passed')
    if not all(x['selected'] for x in rows):raise RuntimeError('Real HTTPS DNS recovery failed; publication blocked')
    if not all(x['resolver_selected'] for x in report['versions']['after']['cases']):
        raise RuntimeError('Content link selection failed; publication blocked')
if __name__=='__main__':main()
