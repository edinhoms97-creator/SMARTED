#!/usr/bin/env python3
"""Read-only DNS/TLS/HTTP content-source diagnostics, no player or ad requests."""
import ast,base64,datetime,gzip,json,re,socket,ssl,struct,time
from pathlib import Path
from urllib.parse import urlsplit,urljoin
import requests
from inspect_content_links import transfer
OUT=Path('.cache/content-links/inspection')

def main():
    source=(OUT/'plugin.video.BrazucaPlay.Matrix-default.py.decoded').read_text()
    tree=ast.parse(source)
    constants={}
    for n in tree.body:
        if isinstance(n,ast.Assign):
            try:v=ast.literal_eval(n.value)
            except Exception:continue
            for t in n.targets:
                if isinstance(t,ast.Name):constants[t.id]=v
    report=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),kind='real-runner-network-not-user-mobile',constants={k:v for k,v in constants.items() if k in ('OVERFLIXTV_HOST','TIMEOUT_DEFAULT','sec_ch_ua','useragent')},hosts={},http=[])
    hosts=[constants['OVERFLIXTV_HOST'],'api.geekantenado.online','geekantenado.fly.dev']
    session=requests.Session();session.headers['User-Agent']=constants.get('useragent','Mozilla/5.0')
    session.headers['Accept-Encoding']='gzip, deflate'
    def fetch(url,kind,headers=None):
        start=time.monotonic();row=dict(url=url,kind=kind)
        try:
            r=session.get(url,timeout=(8,15),headers=headers);row.update(status=r.status_code,final_url=r.url,elapsed=round(time.monotonic()-start,3),content_type=r.headers.get('Content-Type'),bytes=len(r.content),body_prefix=r.text[:1400],redirects=[dict(status=x.status_code,url=x.url) for x in r.history])
            (OUT/('http-'+str(len(report['http']))+'.txt')).write_text(r.text)
            report['http'].append(row);return r
        except Exception as e:row.update(error=type(e).__name__,details=str(e)[:800],elapsed=round(time.monotonic()-start,3));report['http'].append(row)
    for host in hosts:
        row={};report['hosts'][host]=row
        start=time.monotonic()
        try:row['system_dns']=sorted(set(x[4][0] for x in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
        except Exception as e:row['system_dns_error']=str(e)
        row['dns_seconds']=round(time.monotonic()-start,3)
        try:
            r=session.get('https://cloudflare-dns.com/dns-query',params={'name':host,'type':'A'},headers={'Accept':'application/dns-json'},timeout=8)
            row['doh']=r.json()
        except Exception as e:row['doh_error']=str(e)[:300]
        fetch('https://'+host+'/', 'configured-source')
    home=report['http'][0]
    if home.get('status')==200:
        text=(OUT/'http-0.txt').read_text()
        links=list(dict.fromkeys(urljoin(home['final_url'],x) for x in re.findall(r'href=[\"\x27]([^\"\x27]+)',text)))
        report['catalog_samples']=[x for x in links if re.search(r'/filmes/|/series/',x)][:12]
        # Existing source metadata only. No media download or alternate inventory.
        samples=[]
        for marker in ('/filmes/','/series/'):
            candidates=[x for x in links if marker in x and x.rstrip('/').split('/')[-1].split('-')[-1].isdigit()]
            if candidates:samples.append(candidates[0])
        for url in samples:
            r=fetch(url,'existing-catalog-detail')
            video_id=url.rstrip('/').split('-')[-1]
            endpoint='https://'+urlsplit(url).netloc+'/index.php?app=videobox&module=video&controller=view&do=playerData&id='+video_id
            fetch(endpoint,'playerData-without-ajax-headers')
            fetch(endpoint.replace(urlsplit(url).netloc,constants['OVERFLIXTV_HOST']), 'original-configured-host-ajax', headers={'X-Requested-With':'XMLHttpRequest','Referer':url.replace(urlsplit(url).netloc,constants['OVERFLIXTV_HOST'])})
            result=fetch(endpoint,'original-ajax-playerData',headers={'X-Requested-With':'XMLHttpRequest','Referer':url})
            if result is not None:
                try:report['http'][-1]['json_keys']=list(result.json())
                except ValueError:report['http'][-1]['json_error']=True
            if r is not None:
                report['http'].append(dict(kind='detail-parser-hints',url=url,snippets=[r.text[max(0,m.start()-100):m.end()+400] for m in list(re.finditer(r'playerData|servers_dub|servers_leg|csrfKey|player_data|videobox',r.text,re.I))[:12]],episode_links=list(dict.fromkeys(urljoin(url,x) for x in re.findall(r'href=[\"\x27]([^\"\x27]+)',r.text) if re.search(r'/episod|/episode',x)))[:5],scripts=re.findall(r'<script[^>]+src=[\"\x27]([^\"\x27]+)',r.text)[-12:]))
    import logging,random
    codec=(OUT/'plugin.video.BrazucaPlay.Matrix-codec.py.decoded').read_text()
    dns_cls=next(n for n in ast.parse(codec).body if isinstance(n,ast.ClassDef) and n.name=='DNSOverride')
    env=dict(socket=socket,time=time,logging=logging,random=random,struct=struct,re=re)
    exec(compile(ast.Module(body=[dns_cls],type_ignores=[]),'<actual-addon-dns-class>','exec'),env)
    dns=env['DNSOverride'].__new__(env['DNSOverride']);dns.PY2=False;dns.cache={};dns.dns_servers=['1.1.1.1','8.8.8.8','9.9.9.9']
    start=time.monotonic();ip=dns.resolve(hosts[0])
    report['actual_addon_udp_dns']=dict(host=hosts[0],ip=ip,elapsed=round(time.monotonic()-start,3),system_dns_still=report['hosts'][hosts[0]].get('system_dns'))
    (OUT/'network-before.json').write_text(json.dumps(report,indent=2)+'\n')
    transfer('Content real network diagnosis',report)
if __name__=='__main__':main()
