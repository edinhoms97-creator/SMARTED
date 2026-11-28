#!/usr/bin/env python3
"""Pinned 46084100325 -> content transport only. Never relax ad preservation rules."""
import argparse,ast,base64,difflib,hashlib,json,zipfile,zlib
from pathlib import Path
from apk_preservation import inventory,SIGNATURE
from inspect_content_links import BASE_SHA
ROOT=Path(__file__).resolve().parent.parent
PREFIX='assets/smarted/profile/addons/plugin.video.BrazucaPlay.Matrix/'
ENTRY=PREFIX+'default.py';NEW=PREFIX+'content_network.py'
SOURCE_SHA='f938c3848f4d95e0a131faf7b22c5263604ec92ec363d86800da2bb6d5df9b42'
ALLOWED={ENTRY,NEW}

def unpack(source):
    layers=[]
    for _ in range(50):
        if not (source.startswith('#encoded by Kodi') or source.startswith("exec((_)(b'")):break
        values=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Constant) and isinstance(n.value,bytes)]
        if len(values)!=1:raise ValueError('Unexpected encoded addon')
        node=values[0];lines=source.splitlines(keepends=True)
        start=sum(len(x) for x in lines[:node.lineno-1])+node.col_offset
        end=sum(len(x) for x in lines[:node.end_lineno-1])+node.end_col_offset
        layers.append((source[:start],source[end:]))
        source=zlib.decompress(base64.b64decode(node.value[::-1])).decode('utf-8')
    compile(source,'<decoded-addon>','exec')
    return source,layers

def repack(source,layers):
    for before,after in reversed(layers):
        source=before+repr(base64.b64encode(zlib.compress(source.encode('utf-8'),9))[::-1])+after
    return source

def fn(source,name):return next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)

def transform(source):
    lines=source.splitlines(keepends=True);edits=[]
    for name in ('getMovieData','valide_v2'):
        node=fn(source,name)
        assignments=[n for n in ast.walk(node) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='session' for t in n.targets) and 'create_retry_session' in ast.get_source_segment(source,n)]
        if len(assignments)!=1:raise ValueError('Unexpected session construction in '+name)
        target=assignments[0]
        if name=='getMovieData':
            # Finish both original session/cloudscraper branches first.
            blocks=[n for n in ast.walk(node) if isinstance(n,ast.If) and isinstance(n.test,ast.UnaryOp) and isinstance(n.test.operand,ast.Name) and n.test.operand.id=='use_cloudrequest']
            if len(blocks)!=1:raise ValueError('Unexpected HTTP session branches')
            index=blocks[0].end_lineno
            text='        if not use_cloudrequest:\n            from content_network import prepare_session\n            session = prepare_session(session)\n'
        else:
            index=target.end_lineno
            text='        from content_network import prepare_session\n        session = prepare_session(session)\n'
        edits.append((index,text))
    for index,text in sorted(edits,reverse=True):lines[index:index]=[text]
    after=''.join(lines)
    # Remove exactly those insertions: every other decoded byte must match.
    restored=after
    for _,text in edits:
        if restored.count(text)!=1:raise ValueError('Ambiguous insertion')
        restored=restored.replace(text,'',1)
    if restored!=source:raise ValueError('Unexpected unrelated addon edits')
    compile(after,'<content-only-addon>','exec')
    return after

def compare(base,result):
    with zipfile.ZipFile(base) as a,zipfile.ZipFile(result) as b:
        before,after=inventory(a),inventory(b)
        changed=sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k))
        if set(changed)!=ALLOWED:raise ValueError('Unexpected APK changes: '+repr(changed))
        old,layers=unpack(a.read(ENTRY).decode());new,_=unpack(b.read(ENTRY).decode())
        if transform(old)!=new:raise ValueError('Decoded function scope mismatch')
        if b.read(NEW)!=(ROOT/'android-build/content-links/content_network.py').read_bytes():raise ValueError('Transport module mismatch')
    return dict(changed=changed,preserved_entries=sum(before.get(k)==after.get(k) for k in before),changed_existing_functions=['getMovieData','valide_v2'],base_sha256=BASE_SHA,vast_all_entries_byte_identical=True,welcome_all_entries_byte_identical=True,admob_vip_player_skin_navigation_all_entries_byte_identical=True,decoded_original_sha256=hashlib.sha256(old.encode()).hexdigest(),decoded_after_sha256=hashlib.sha256(new.encode()).hexdigest())

def build(base,out,report):
    assert hashlib.sha256(base.read_bytes()).hexdigest()==BASE_SHA,'Wrong physical-test base'
    with zipfile.ZipFile(base) as source:
        original=source.read(ENTRY)
        assert hashlib.sha256(original).hexdigest()==SOURCE_SHA,'Unexpected addon entry'
        decoded,layers=unpack(original.decode());updated=transform(decoded)
        assert NEW not in source.namelist()
        out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(out,'w') as target:
            target.comment=source.comment
            for info in source.infolist():
                if SIGNATURE.fullmatch(info.filename):continue
                target.writestr(info,repack(updated,layers).encode() if info.filename==ENTRY else source.read(info.filename))
            target.writestr(NEW,(ROOT/'android-build/content-links/content_network.py').read_bytes(),compress_type=zipfile.ZIP_DEFLATED)
    result=compare(base,out)
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n')
    (report.parent/'content-functions.diff').write_text(''.join(difflib.unified_diff(decoded.splitlines(True),updated.splitlines(True),fromfile='46084100325/default.py decoded',tofile='content-recovery/default.py decoded')))
    print('::notice title=Content exact preservation audit::'+json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('out',type=Path);p.add_argument('--report',type=Path,required=True);args=p.parse_args();build(args.base,args.out,args.report)
