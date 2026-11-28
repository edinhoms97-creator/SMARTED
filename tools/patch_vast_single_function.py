#!/usr/bin/env python3
"""Change ONLY ads_vast.exibir in exact build 46074593488; strict byte/AST audit."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import zipfile
from apk_preservation import patch
from vast_visual_lab import TAG, BASE_SHA, PREFIX

AD = PREFIX+'ads_vast.py'


def node(source):
    return next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='exibir')


def transform(source):
    fn=node(source);old=ast.get_source_segment(source,fn)
    overlay=Path(__file__).resolve().parent.parent/'android-build/vast-function-only/ads_vast.py'
    new=ast.get_source_segment(overlay.read_text(),node(overlay.read_text()))
    lines=source.splitlines(keepends=True)
    result=''.join(lines[:fn.lineno-1])+new+'\n'+''.join(lines[fn.end_lineno:])
    audit(source,result)
    return result


def audit(before,after):
    a,b=node(before),node(after)
    def rest(text,n):
        lines=text.splitlines(keepends=True)
        return ''.join(lines[:n.lineno-1]),''.join(lines[n.end_lineno:])
    if rest(before,a)!=rest(after,b):raise ValueError('Bytes outside exibir changed')
    def tree_without_entry(text):
        t=ast.parse(text);t.body=[n for n in t.body if not(isinstance(n,ast.FunctionDef) and n.name=='exibir')]
        return ast.dump(t,include_attributes=False)
    if tree_without_entry(before)!=tree_without_entry(after):raise ValueError('AST outside exibir changed')
    compile(after,'<single-function-vast>','exec')


def build(base,output,report):
    if hashlib.sha256(base.read_bytes()).hexdigest()!=BASE_SHA:raise ValueError('Not the pinned current APK')
    with zipfile.ZipFile(base) as z:source=z.read(AD)
    updated=transform(source.decode()).encode()
    report.parent.mkdir(parents=True,exist_ok=True)
    (report.parent/'exibir.diff').write_text(''.join(difflib.unified_diff(source.decode().splitlines(keepends=True),updated.decode().splitlines(keepends=True),fromfile='base/ads_vast.py',tofile='patched/ads_vast.py')))
    plan={'reviewed':True,'policy':'Only ads_vast.exibir; every other byte/function and all other entries unchanged',
          'changes':{AD:{'original_sha256':hashlib.sha256(source).hexdigest()}}}
    report.parent.mkdir(parents=True,exist_ok=True);output.parent.mkdir(parents=True,exist_ok=True)
    result=patch(base,output,{AD:updated},plan)
    result.update(base_build=46074593488,base_sha256=BASE_SHA,allowed_scope='ads_vast.exibir',
                  unchanged_outside_function_bytes=True,tag=TAG,old_tag_fallback=False,
                  source_before_sha256=hashlib.sha256(source).hexdigest(),source_after_sha256=hashlib.sha256(updated).hexdigest())
    report.write_text(json.dumps(result,indent=2)+'\n')
    (report.parent/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print('::notice title=Single VAST function audit::'+json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('output',type=Path);p.add_argument('--report',type=Path,required=True);a=p.parse_args();build(a.base,a.output,a.report)
