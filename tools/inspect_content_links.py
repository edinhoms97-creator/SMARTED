#!/usr/bin/env python3
"""Read-only exact delivery content resolver forensics. No addon execution."""
import argparse,ast,base64,gzip,hashlib,json,re,sys,zipfile,zlib
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
    a.out.mkdir(parents=True,exist_ok=True);hits=[];sources={};inventory=[];decoded=[]
    with zipfile.ZipFile(a.apk) as z:
        for name in z.namelist():
            if not name.endswith(('.py','.xml','.json','.txt','.po')):continue
            b=z.read(name)
            s=b.decode('utf-8',errors='replace')
            if name.endswith('.py') and s.startswith('#encoded by Kodi'):
                for _ in range(50):
                    if not (s.startswith('#encoded by Kodi') or s.startswith("exec((_)(b'")):break
                    tree=ast.parse(s)
                    values=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,bytes)]
                    if len(values)!=1:break
                    s=zlib.decompress(base64.b64decode(values[0][::-1])).decode('utf-8')
                (a.out/(Path(name).parent.name+'-'+Path(name).name+'.decoded')).write_text(s)
                decoded.append(dict(path=name,bytes=len(s),head=s[:2000],tail=s[-500:],matching_lines=[line[:1000] for line in s.splitlines() if re.search(r'operadora|warp|DNS|obter|nao.*link|poss.vel',line,re.I)][:30]))

            if any(term in s.lower() for term in ('operadoras bloqueando','1.1.1.1 + warp','possível obter o link','possivel obter o link')):
                lines=s.splitlines();indices=set()
                for i,line in enumerate(lines):
                    if any(t in line.lower() for t in ('operadoras bloqueando','1.1.1.1 + warp','obter o link')):indices.update(range(max(0,i-35),min(len(lines),i+20)))
                hits.append(dict(path=name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),excerpt='\n'.join(f'{i+1}: {lines[i]}' for i in sorted(indices))))
                tree=ast.parse(s) if name.endswith('.py') else None
                contexts={}
                if tree:
                    for n in tree.body:
                        if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and any(t in ast.get_source_segment(s,n).lower() for t in ('operadoras bloqueando','obter o link','warp')):
                            contexts[n.name]=ast.get_source_segment(s,n)
                sources[name]=json.dumps(dict(path=name,imports=[ast.unparse(n) for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))] if tree else [],contexts=contexts,functions=[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))] if tree else []),ensure_ascii=False)
            if name.endswith('.py') and any(t in name.lower() for t in ('brazuca','resolver','resolveurl','dns','source','client','cloudflare')):
                inventory.append(dict(path=name,bytes=len(b)))
        packed=[]
        for name in z.namelist():
            if 'BrazucaPlay' in name and name.endswith('.py'):
                text=z.read(name).decode(errors='replace')
                packed.append(dict(path=name,bytes=len(text)))
        report=dict(base_sha256=BASE_SHA,hits=hits,related_inventory=inventory,packed_candidates=packed,decoded=decoded)
        (a.out/'inspection.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        transfer('Content resolver inspection',report)
        for index,(name,s) in enumerate(sources.items()):
            (a.out/('source-'+str(index)+'.json')).write_text(json.dumps(dict(path=name,source=s),ensure_ascii=False))
            # Split source by line boundaries, retaining exact string reconstruction.
            for part in range(0,min(len(s),18000),18000):transfer('Content source '+str(index)+' segment '+str(part//18000),dict(path=name,offset=part,source=s[part:part+18000]))
def delivery():
    with zipfile.ZipFile('.cache/content-links/base/SMARTEDTV-universal.apk') as z:
        result={'addon_xml':z.read('assets/smarted/profile/addons/plugin.video.BrazucaPlay.Matrix/addon.xml').decode(),'sources':{}}
        for name in ('assets/addons/service.smarted.bootstrap/menu_smarted.py','assets/addons/service.smarted.bootstrap/service.py'):
            source=z.read(name).decode();tree=ast.parse(source)
            result['sources'][name]={n.name:ast.get_source_segment(source,n) for n in tree.body if isinstance(n,ast.FunctionDef) and any(t in ast.get_source_segment(source,n) for t in ('BrazucaPlay','brazuca','smarted/profile')) and len(ast.get_source_segment(source,n))<18000}
        result['payload_inventory']=[dict(path=n,bytes=z.getinfo(n).file_size) for n in z.namelist() if '/payload/' in n]
        service=z.read('assets/addons/service.smarted.bootstrap/service.py').decode()
        result['repair_sources']={n.name:ast.get_source_segment(service,n) for n in ast.parse(service).body if isinstance(n,ast.FunctionDef) and n.name in ('run_repair','repair_until_ready')}
        result['service_imports']=[ast.unparse(n) for n in ast.parse(service).body if isinstance(n,(ast.Import,ast.ImportFrom))]
        transfer('Content addon deployment',result)

def emit(kind):
    folder=Path('.cache/content-links/inspection')
    filename='plugin.video.BrazucaPlay.Matrix-'+('codec.py' if kind=='dns' else 'default.py')+'.decoded'
    source=(folder/filename).read_text();tree=ast.parse(source)
    wanted={'transport':{'getMovieData','resolver_api','overflix_domain','valide_v2'},'dns':{'DNSOverride'},'domains':set()}[kind]
    result={'kind':kind,'functions':{n.name:ast.get_source_segment(source,n) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in wanted}}
    if kind=='domains':
        result['assignments']=[ast.unparse(n)[:2000] for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and any(k in t.id.upper() for k in ('HOST','DOMAIN','API','URL')) for t in n.targets)]
        result['functions']={n.name:ast.get_source_segment(source,n) for n in tree.body if isinstance(n,ast.FunctionDef) and any(k in n.name.lower() for k in ('domain','api')) and len(ast.get_source_segment(source,n))<12000}
    (folder/(kind+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    transfer('Content '+kind,result)
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='delivery':delivery()
    elif len(sys.argv)>1 and sys.argv[1]=='emit':emit(sys.argv[2])
    else:main()
