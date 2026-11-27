#!/usr/bin/env python3
"""Read-only contracts for APK link actions and ad decoder helpers; no settings."""
import ast
import hashlib
import json
import re
import sys
import zipfile
from inspect_ad_contract import Redact


def emit(result):
    text = json.dumps(result, ensure_ascii=False)
    chunks = [text[i:i+2600] for i in range(0, len(text), 2600)]
    for i, data in enumerate(chunks):
        payload = json.dumps({'part': i, 'parts': len(chunks), 'data': data})
        print('::notice title=SMARTED controls contract::' + payload.replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D'))


with zipfile.ZipFile(sys.argv[1]) as archive:
    matches = []
    routes = []
    for info in archive.infolist():
        path = info.filename
        if path.endswith('.xml') and ('smarted' in path or 'novatv' in path):
            text = archive.read(path).decode('utf-8', errors='replace')
            lines = sorted(set(action for action in re.findall(r'<on(?:long)?click[^>]*>(.*?)</on(?:long)?click>', text, re.S) if any(word in action.lower() for word in ('apk', 'share', 'download', 'atualiz', 'compart', 'dropbox', 'vip.'))))
            if lines:
                routes.append({'path': path, 'actions': lines})
        if not (path.startswith('assets/addons/') and path.endswith('.py') and ('smarted' in path or 'novatv' in path)):
            continue
        text = archive.read(path).decode('utf-8-sig')
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        if path == 'assets/addons/script.smartedtv.welcome/default.py':
            selected = {n.name: ast.unparse(Redact().visit(n)) for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef) and (n.name == 'onClick' or any(word in n.name for word in ('dropbox', 'compartilhar', 'baixar', 'atualizar')))}
            emit({'welcome_actions': selected})
        if not path.startswith('assets/addons/service.smarted.bootstrap/'):
            lines = [line.strip() for line in text.splitlines() if any(word in line for word in ('open_apk_download', 'share_download_link', 'procurar_atualizacao', 'install_update', 'compartilhar(', 'abrir_dropbox(', 'onClick', 'control_id ==', 'control_id in'))]
            if lines:
                routes.append({'path': path, 'actions': lines})
            continue
        if path.endswith('/ads_vast.py'):
            selected = {n.name: ast.unparse(Redact().visit(n)) for n in tree.body
                        if isinstance(n, ast.FunctionDef) and n.name in ('_media_escolhido', '_tocar', '_aguardar_anuncio_tocar', '_posicao_e_duracao', '_agora')}
            pass  # helper contracts already inspected
        if any(word in text.lower() for word in ('compartilh', 'atualizar aplicativo', 'smartedtv.apk', 'dialogwelcome')):
            functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            selected = {}
            for n in ast.walk(tree):
                if isinstance(n, ast.FunctionDef) and any(s in n.name.lower() for s in ('compart', 'baixar', 'atualiz', 'download', 'onclick', 'resolver_apk', 'instalar_apk', 'install_update', 'abrir_dropbox', '_start_android', '_abrir_navegador')):
                    selected[n.name] = ast.unparse(Redact().visit(n))
            constants = [ast.unparse(Redact().visit(n)) for n in tree.body if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and any(s in t.id.lower() for s in ('apk', 'share', 'download')) for t in n.targets)]
            matches.append({'path': path, 'sha256': hashlib.sha256(archive.read(path)).hexdigest(), 'functions': functions, 'selected': selected, 'constants': constants, 'routes': [line.strip() for line in text.splitlines() if any(s in line for s in ('vip.open_apk_download', 'vip.share_download_link', 'vip.procurar_atualizacao', 'vip.install_update', 'vip.compartilhar', 'vip.abrir_dropbox', 'control_id ==', 'control_id in'))]})
    # Prior inspections already captured installer contracts. Emit routes only
    # here so the GitHub ten-notice limit cannot truncate button evidence.
    # emit({'controls': matches})
    # Previous inspection captured the compact routing table.
    # emit({'routes': routes})
