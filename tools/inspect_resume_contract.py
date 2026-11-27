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
    for path in ('assets/smarted/profile/addons/plugin.video.BrazucaPlay.Matrix/default.py',
                 'assets/smarted/profile/addons/plugin.video.BrazucaPlay.Matrix/database.py'):
        import hashlib
        data = archive.read(path)
        tree = ast.parse(data.decode('utf-8-sig'))
        functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        selected[path] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
                          'functions': [n.name for n in functions],
                          'selected': {n.name: ast.unparse(Redact().visit(n)) for n in functions
                                       if any(word in n.name.lower() for word in ('servid', 'server', 'playvideo', 'play_video', 'resolver')) and n.end_lineno - n.lineno < 180},
                          'dynamic_execution': any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'exec' for n in ast.walk(tree))}
    emit('brazuca', selected)
