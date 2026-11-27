#!/usr/bin/env python3
"""Read-only exact-APK forensics: historical 120s build versus current delivery."""
import ast,base64,copy,difflib,gzip,hashlib,json
from pathlib import Path
import sys,zipfile
from inspect_ad_contract import Redact
from report_vast_apk_diff import inspect,scopes,PREFIX
ROOT=Path('.cache/history-startup');ROOT.mkdir(parents=True,exist_ok=True)
VERSIONS={'historical':('smarted-original-ads-45992589750-1','f6ecfb6059bd1afbfadb9bd81065f45887781c1223e2d85b3bf19f748c7f44c6'),
          'current':('smarted-vast-only-46079704676-1','919e97db0929ab90f189c9503722f4a5139feda573a28c96d79973a8e70e6087')}

def transfer(title,data):
    text=base64.b64encode(gzip.compress(json.dumps(data).encode())).decode()
    if len(text)>9*3500:raise ValueError('Split evidence into separate steps: '+title)
    for i in range(0,len(text),3500):
        print('::notice title='+title+'::'+json.dumps(dict(part=i//3500,total=(len(text)+3499)//3500,data=text[i:i+3500])))

def sanitized(text):return ast.unparse(Redact().visit(ast.parse(text)))

def compare():
    data={};payload={}
    for label,(tag,expected) in VERSIONS.items():
        apk=ROOT/label/'SMARTEDTV-universal.apk'
        if hashlib.sha256(apk.read_bytes()).hexdigest()!=expected:raise ValueError('APK hash mismatch')
        data[label]=inspect(apk)
        payload[label]={'release':tag,'sha256':expected,'bytes':apk.stat().st_size,'selected_sources':{}}
        for name in ('ads_vast.py','smart_ads.py','ads_regra.py'):
            s=data[label][2][PREFIX+name];tree=ast.parse(s)
            wanted={'exibir','baixar','tag_configurada','escolher_anuncio','_media_escolhido','tag_do_wrapper','tag_do_vmap','mostrar_preroll','tocar_anuncio_de_video','intervalo_configurado','pode_anunciar','MonitorPreRoll'}
            selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in wanted]
            payload[label]['selected_sources'][name]=ast.unparse(Redact().visit(ast.Module(body=selected,type_ignores=[])))
        payload[label]['rule_constants']=[ast.unparse(n) for n in ast.parse(data[label][2][PREFIX+'ads_regra.py']).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='INTERVALO' for t in n.targets)]
    old,now=data['historical'],data['current']
    changed=sorted(p for p in old[0].keys()|now[0].keys() if old[0].get(p)!=now[0].get(p))
    payload['comparison']={'changed_entries':changed,'unchanged_entries':sum(old[0].get(p)==now[0].get(p) for p in old[0].keys()&now[0].keys()),'scopes':{}}
    for p in changed:
        if p in old[2] and p in now[2]:
            a,b=scopes(old[2][p]),scopes(now[2][p])
            payload['comparison']['scopes'][p]=[n for n in a.keys()|b.keys() if a.get(n)!=b.get(n)]
    (ROOT/'history-comparison.json').write_text(json.dumps(payload,indent=2)+'\n')
    transfer('VAST historical comparison',payload)

def startup():
    apk=ROOT/'current/SMARTEDTV-universal.apk';result={}
    names=[PREFIX+n for n in ('service.py','default.py','skin_setup.py','check.py')]+['assets/addons/script.smartedtv.welcome/default.py']
    with zipfile.ZipFile(apk) as z:
        for name in names:
            if name not in z.namelist():continue
            source=z.read(name).decode('utf-8-sig')
            result[name]={'sha256':hashlib.sha256(z.read(name)).hexdigest(),'source':sanitized(source)}
    (ROOT/'startup-python.json').write_text(json.dumps(result,indent=2)+'\n')
    transfer('SMARTED startup Python',result)

def dex():
    from loguru import logger
    logger.disable('androguard')
    from androguard.core.apk import APK
    from androguard.core.dex import DEX
    apk=APK(str(ROOT/'current/SMARTEDTV-universal.apk'))
    from lxml import etree
    manifest=etree.tostring(apk.get_android_manifest_xml(),pretty_print=True).decode()
    result={'manifest':manifest,'classes':{}}
    for raw in apk.get_all_dex():
        for cls in DEX(raw).get_classes():
            if cls.get_name() in ('Lsmartedtv/full/Splash;','Lsmartedtv/full/MainActivity;'):
                methods={}
                for m in cls.get_methods():
                    methods[m.get_name()+m.get_descriptor()]=[i.get_name()+' '+i.get_output() for i in m.get_instructions()]
                result['classes'][cls.get_name()]=methods
    (ROOT/'startup-native.json').write_text(json.dumps(result,indent=2)+'\n')
    transfer('SMARTED startup native',result)

if __name__=='__main__':{'compare':compare,'startup':startup,'dex':dex}[sys.argv[1]]()
