"""Idempotent content-transport delivery to the existing Brazuca profile only.
No settings, cache purge, addon replacement, navigation, player or UI actions.
"""
import ast,base64,hashlib,json,os,zlib
from pathlib import Path

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
        assignments=[n for n in ast.walk(node) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='session' for t in n.targets) and isinstance(n.value,ast.IfExp) and 'create_retry_session' in ast.get_source_segment(source,n)]
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

def install(addon_path, log):
    """Patch only two known content functions in place; leave all other bytes."""
    target=Path(addon_path)/'default.py'
    module=Path(addon_path)/'content_network.py'
    try:
        payload=Path(__file__).with_name('content_network.py').read_bytes()
        if target.parent.name!='plugin.video.BrazucaPlay.Matrix' or not target.is_file():
            raise ValueError('Unexpected content addon path')
        before=target.read_bytes();decoded,layers=unpack(before.decode('utf-8'))
        marker='from content_network import prepare_session'
        already=decoded.count(marker)==2
        if marker in decoded and not already:raise ValueError('Partial or unknown content hook')
        # Existing modules with an unrelated name collision are never overwritten.
        if module.exists() and module.read_bytes()!=payload:
            raise ValueError('Unknown existing content_network module')
        after=before if already else repack(transform(decoded),layers).encode('utf-8')
        audit=dict(kind='content-only-profile-delivery',before_sha256=hashlib.sha256(before).hexdigest(),
            after_sha256=hashlib.sha256(after).hexdigest(),module_sha256=hashlib.sha256(payload).hexdigest(),
            functions=['getMovieData','valide_v2'],all_other_decoded_bytes_preserved=True,
            status='already-current' if already and module.exists() else 'updated')
        if not module.exists():
            temporary=module.with_suffix('.py.content-tmp');temporary.write_bytes(payload);os.replace(temporary,module)
        if after!=before:
            temporary=target.with_suffix('.py.content-tmp');temporary.write_bytes(after);os.replace(temporary,target)
        # Audit is scoped inside this content addon, never modifies user settings.
        record=target.parent/'smarted-content-delivery.json'
        if not already or not record.is_file():record.write_text(json.dumps(audit,indent=2)+'\n')
        log.append('content-links: '+json.dumps(audit,sort_keys=True))
        return True
    except Exception as error:
        log.append('content-links: FAILED '+type(error).__name__+' '+str(error))
        return False
