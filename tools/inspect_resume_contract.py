#!/usr/bin/env python3
"""Read-only player/resolver contracts; network literals redacted, no user data."""
import ast
import json
import sys
import zipfile
from inspect_ad_contract import Redact


def emit(group, data):
    # ASCII transport avoids annotation Unicode escaping ambiguity.
    import base64
    payload = base64.b64encode(json.dumps(data).encode()).decode()
    for i in range(0, len(payload), 3600):
        text = json.dumps({'group': group, 'part': i // 3600, 'data': payload[i:i+3600]})
        print('::notice title=SMARTED resume contract::' + text)


with zipfile.ZipFile(sys.argv[1]) as archive:
    selected = {}
    inventory = []
    for path in archive.namelist():
        if not path.endswith('.py') or not path.startswith('assets/'):
            continue
        if '/service.smarted.bootstrap/' in path:
            names = {'ads_vast.py': ('_candidatos_restauracao', '_iniciar_em_tela_cheia', 'extrair_url_real_do_proxy'),
                     'ao_vivo.py': ('_tocar_de_novo',), 'retomar.py': ()}.get(path.rsplit('/',1)[-1])
            if names:
                tree = ast.parse(archive.read(path).decode('utf-8-sig'))
                selected[path] = {n.name: ast.unparse(Redact().visit(n)) for n in tree.body
                                  if isinstance(n, ast.FunctionDef) and n.name in names}
        if any(word in path.lower() for word in ('brazuca', 'proxy', 'resolver', 'smarted')) and not any(word in path for word in ('/site-packages/', '/script.module.', '/lib/python')):
            data = archive.read(path)
            if len(data) > 250000:
                continue
            try:
                tree = ast.parse(data.decode('utf-8-sig'))
            except Exception:
                continue
            funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and any(word in n.name.lower() for word in ('resolv', 'server', 'servid', 'play', 'tocar', 'stream'))]
            if funcs:
                inventory.append({'path': path, 'functions': funcs[:45]})
    emit('helpers', selected)
    emit('inventory', inventory[:50])
