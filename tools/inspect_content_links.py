#!/usr/bin/env python3
"""Read-only exact delivery content resolver forensics. No addon execution."""
import argparse,base64,gzip,hashlib,json,re,zipfile
from pathlib import Path
BASE_SHA='6510b917a159e2b8ab216289ada2e4b2015aa4b29fa81809caa120fc7fe8f0a2'

def transfer(title,data):
    data=base64.b64encode(gzip.compress(json.dumps(data,ensure_ascii=False).encode())).decode()
    if len(data)>9*3400:raise ValueError('Oversized annotation payload: '+title)
    for i in range(0,len(data),3400):
        print('::notice title='+title+'::'+json.dumps(dict(part=i//3400,total=(len(data)+3399)//3400,data=data[i:i+3400])))

def main():
    p=argparse.ArgumentParser();p.add_argument('apk',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    assert hashlib.sha256(a.apk.read_bytes()).hexdigest()==BASE_SHA,'Wrong base APK'
    a.out.mkdir(parents=True,exist_ok=True);hits=[];sources={};inventory=[]
    with zipfile.ZipFile(a.apk) as z:
        for name in z.namelist():
            if not name.endswith(('.py','.xml','.json','.txt','.po')):continue
            b=z.read(name)
            s=b.decode('utf-8',errors='replace')
            if any(term in s.lower() for term in ('operadoras bloqueando','warp','possível obter o link','possivel obter o link')):
                lines=s.splitlines();indices=set()
                for i,line in enumerate(lines):
                    if any(t in line.lower() for t in ('operadoras bloqueando','warp','obter o link')):indices.update(range(max(0,i-35),min(len(lines),i+20)))
                hits.append(dict(path=name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),excerpt='\n'.join(f'{i+1}: {lines[i]}' for i in sorted(indices))))
                sources[name]=s
            if name.endswith('.py') and any(t in name.lower() for t in ('brazuca','resolver','resolveurl','dns','source','client','cloudflare')):
                inventory.append(dict(path=name,bytes=len(b)))
        report=dict(base_sha256=BASE_SHA,hits=hits,related_inventory=inventory)
        (a.out/'inspection.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        transfer('Content resolver inspection',report)
        for index,(name,s) in enumerate(sources.items()):
            (a.out/('source-'+str(index)+'.json')).write_text(json.dumps(dict(path=name,source=s),ensure_ascii=False))
            # Split source by line boundaries, retaining exact string reconstruction.
            for part in range(0,len(s),18000):transfer('Content source '+str(index)+' segment '+str(part//18000),dict(path=name,offset=part,source=s[part:part+18000]))
if __name__=='__main__':main()
