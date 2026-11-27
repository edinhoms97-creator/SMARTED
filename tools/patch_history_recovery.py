#!/usr/bin/env python3
"""Pin latest APK. Only VAST.exibir budget and welcome startup dispatcher may differ."""
import argparse,ast,difflib,hashlib,json
from pathlib import Path
import zipfile
from apk_preservation import patch,compare

BASE_SHA='919e97db0929ab90f189c9503722f4a5139feda573a28c96d79973a8e70e6087'
AD='assets/addons/service.smarted.bootstrap/ads_vast.py'
WELCOME='assets/addons/script.smartedtv.welcome/default.py'
SCOPES={AD:'exibir',WELCOME:'abrir_tela_entrada'}

def function(source,name):
    return next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)

def audit(before,after,name):
    a,b=function(before,name),function(after,name)
    def surrounding(text,n):
        lines=text.splitlines(keepends=True)
        return ''.join(lines[:n.lineno-1]),''.join(lines[n.end_lineno:])
    if surrounding(before,a)!=surrounding(after,b):raise ValueError('Bytes outside '+name+' changed')
    compile(after,'<audited-'+name+'>','exec')

def replace(source,name,new):
    fn=function(source,name);lines=source.splitlines(keepends=True)
    result=''.join(lines[:fn.lineno-1])+new.rstrip()+'\n'+''.join(lines[fn.end_lineno:])
    audit(source,result,name)
    return result

def welcome(source):
    fn=function(source,'abrir_tela_entrada');lines=source.splitlines(keepends=True)
    branches=[n for n in fn.body if isinstance(n,ast.If) and isinstance(n.test,ast.Call) and isinstance(n.test.func,ast.Name) and n.test.func.id in ('ativacao_concluida','_veio_de_uma_saida')]
    if len(branches)!=2:raise ValueError('Unexpected startup dispatcher; do not guess')
    for branch in reversed(branches):
        lines[branch.lineno-1:branch.end_lineno]=[]
    result=''.join(lines)
    audit(source,result,'abrir_tela_entrada')
    return result

def vast(source):
    overlay=(Path(__file__).resolve().parent.parent/'android-build/vast-function-only/ads_vast.py').read_text()
    result=replace(source,'exibir',ast.get_source_segment(overlay,function(overlay,'exibir')))
    # Selector recovery must remain byte-identical, apart from the budget policy.
    expected=source.replace('    deadline = _agora() + 8.0', '''    # Historical corrected-skin build budgets each HTTP hop independently.
    # Preserve that 8s transport budget, plus a bounded whole traversal; no sleep,
    # no root retries and no cooldown/state shared with another opening.
    request_budget = 8.0
    deadline = _agora() + request_budget * (PROFUNDIDADE_WRAPPER + 1)''',1).replace('baixar(url, timeout=remaining)','baixar(url, timeout=min(request_budget, remaining))',1)
    if result!=expected:raise ValueError('Unexpected VAST change beyond recovered request budget')
    return result

def preservation(base,result):
    report=compare(base,result,set(SCOPES))
    report.pop('skin_manifest_resources_startup_unchanged',None)
    report.update(skin_manifest_resources_player_tracking_vip_admob_resume_unchanged=True,
        changed_production_functions=SCOPES,all_bytes_outside_allowed_functions_unchanged=True)
    return report

def build(base,out,report_path):
    if hashlib.sha256(base.read_bytes()).hexdigest()!=BASE_SHA:raise ValueError('Unpinned current APK')
    with zipfile.ZipFile(base) as z:
        originals={name:z.read(name) for name in SCOPES}
    changes={AD:vast(originals[AD].decode()).encode(),WELCOME:welcome(originals[WELCOME].decode()).encode()}
    plan=dict(reviewed=True,changes={n:dict(original_sha256=hashlib.sha256(v).hexdigest()) for n,v in originals.items()})
    out.parent.mkdir(parents=True,exist_ok=True);report_path.parent.mkdir(parents=True,exist_ok=True)
    patch(base,out,changes,plan)
    report=preservation(base,out)
    report.update(base_sha256=BASE_SHA,tag='https://vast.yomeno.xyz/vast?spot_id=1508249',no_old_tag_fallback=True,
        before_after_module_sha256={n:dict(before=hashlib.sha256(originals[n]).hexdigest(),after=hashlib.sha256(changes[n]).hexdigest()) for n in SCOPES})
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    (report_path.parent/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    for n in SCOPES:
        (report_path.parent/(Path(n).stem+'-recovery.diff')).write_text(''.join(difflib.unified_diff(originals[n].decode().splitlines(True),changes[n].decode().splitlines(True),fromfile='before/'+n,tofile='after/'+n)))
    print('::notice title=Recovery exact scope audit::'+json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('out',type=Path);p.add_argument('--report',type=Path,required=True);a=p.parse_args();build(a.base,a.out,a.report)
