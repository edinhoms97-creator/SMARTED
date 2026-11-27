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
    import zlib, base64, hashlib
    path = 'assets/smarted/profile/addons/plugin.video.BrazucaPlay.Matrix/default.py'
    tree = ast.parse(archive.read(path).decode('utf-8-sig'))
    # The audited wrapper is exactly base64(reverse(bytes)) then zlib. Decode
    # data only; NEVER eval/exec/import the provider or its decrypted source.
    raw = archive.read(path)
    layers = 0
    for _ in range(128):
        if any(isinstance(n, ast.FunctionDef) for n in ast.walk(tree)):
            break
        calls = [n.value for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == 'exec']
        if not calls:
            break
        payload = ast.literal_eval(calls[0].args[0].args[0])
        raw = zlib.decompress(base64.b64decode(payload[::-1]))
        if len(raw) > 4000000:
            raise ValueError('Provider inspection size limit')
        tree = ast.parse(raw.decode('utf-8-sig'))
        layers += 1
    decoded = tree
    functions = [n for n in ast.walk(decoded) if isinstance(n, ast.FunctionDef)]
    emit('decoded', {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'layers': layers,
                     'functions': [{'name': n.name, 'lines': n.end_lineno - n.lineno} for n in functions],
                     'selected': {n.name: ast.unparse(Redact().visit(n)) for n in functions if any(word in n.name.lower() for word in ('servid', 'server', 'playvideo', 'play_video', 'resolver')) and n.end_lineno - n.lineno < 180}})
