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
    for path in archive.namelist():
        if path == 'assets/addons/plugin.video.smarted/navigation.py':
            import hashlib
            tree = ast.parse(archive.read(path).decode('utf-8-sig'))
            selected[path] = {'sha256': hashlib.sha256(archive.read(path)).hexdigest(),
                              'functions': [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)],
                              'selected': {n.name: ast.unparse(Redact().visit(n)) for n in tree.body
                                           if isinstance(n, ast.FunctionDef) and n.name == 'resolve'},
                              'imports': [ast.unparse(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]}
    selected['resolver_paths'] = [name for name in archive.namelist() if any(word in name.lower() for word in ('brazuca', 'resolveurl', 'urlresolver', 'streamtape', 'mixdrop', 'doodstream'))][:60]
    emit('resolver', selected)
