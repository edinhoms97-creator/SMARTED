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
    path = 'assets/smarted/profile/addons/plugin.video.BrazucaPlay.Matrix/default.py'
    tree = ast.parse(archive.read(path).decode('utf-8-sig'))
    emit('wrapper', {'wrapper': ast.unparse(Redact().visit(tree))[:10000]})
