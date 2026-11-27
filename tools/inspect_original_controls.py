#!/usr/bin/env python3
"""Read-only contracts for APK link actions and ad decoder helpers; no settings."""
import ast
import hashlib
import json
import sys
import zipfile
from inspect_ad_contract import Redact


def emit(result):
    text = json.dumps(result)
    chunks = [text[i:i+2600] for i in range(0, len(text), 2600)]
    for i, data in enumerate(chunks):
        payload = json.dumps({'part': i, 'parts': len(chunks), 'data': data})
        print('::notice title=SMARTED controls contract::' + payload.replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D'))


with zipfile.ZipFile(sys.argv[1]) as archive:
    matches = []
    for info in archive.infolist():
        path = info.filename
        if not (path.startswith('assets/addons/service.smarted.bootstrap/') and path.endswith('.py')):
            continue
        text = archive.read(path).decode('utf-8-sig')
        tree = ast.parse(text)
        if path.endswith('/ads_vast.py'):
            selected = {n.name: ast.unparse(Redact().visit(n)) for n in tree.body
                        if isinstance(n, ast.FunctionDef) and n.name in ('_media_escolhido', '_tocar', '_aguardar_anuncio_tocar', '_posicao_e_duracao', '_agora')}
            emit({'path': path, 'helpers': selected})
        if any(word in text.lower() for word in ('compartilh', 'atualizar aplicativo', 'smartedtv.apk', 'dialogwelcome')):
            functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            selected = {}
            for n in ast.walk(tree):
                if isinstance(n, ast.FunctionDef) and any(s in n.name.lower() for s in ('compart', 'baixar', 'atualiz', 'download', 'onclick')):
                    selected[n.name] = ast.unparse(Redact().visit(n))
            constants = [ast.unparse(Redact().visit(n)) for n in tree.body if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and any(s in t.id.lower() for s in ('apk', 'share', 'download')) for t in n.targets)]
            matches.append({'path': path, 'sha256': hashlib.sha256(archive.read(path)).hexdigest(), 'functions': functions, 'selected': selected, 'constants': constants})
    emit({'controls': matches})
