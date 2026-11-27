#!/usr/bin/env python3
"""Read only an existing Android artifact; never launch ads/content."""
import base64
import gzip
import json
from pathlib import Path
import re
import sys
result = []
for path in Path(sys.argv[1]).rglob('*'):
    if path.name not in ('logcat.txt', 'kodi.log'):
        continue
    lines = path.read_text(errors='replace').splitlines()
    keys = ('SmartAds', 'smart_ads', 'ads_openings', 'Traceback', 'Error Type:', 'Error Contents:',
            'ModuleNotFoundError', 'SyntaxError', 'onClick recebido', 'Botao 312', 'Botao 906',
            'VideoPlayer::OpenFile', 'PythonToCppException')
    capture = 0
    for line in lines:
        if any(key in line for key in keys):
            capture = 9 if any(key in line for key in ('Traceback', 'Error Type:', 'PythonToCppException')) else max(capture, 1)
        if capture:
            result.append(re.sub(r'https?://\S+', '<url>', line))
            capture -= 1
payload = base64.b64encode(gzip.compress('\n'.join(result[-180:]).encode())).decode()
for i in range(0, len(payload), 2500):
    print('::notice title=Android monitor diagnostic chunks::' + json.dumps(dict(part=i//2500, data=payload[i:i+2500])))

# Optional APK source inspection is read-only; no runtime injection or requests.
if len(sys.argv) > 2:
    import ast
    import zipfile
    with zipfile.ZipFile(sys.argv[2]) as archive:
        text = archive.read('assets/addons/service.smarted.bootstrap/smart_ads.py').decode()
    tree = ast.parse(text)
    names = {'_e_video', 'motor_anuncio', 'usar_vast'}
    selected = {node.name: ast.get_source_segment(text, node) for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names}
    print('::notice title=Read-only APK eligibility source::' + json.dumps(selected))

    with zipfile.ZipFile(sys.argv[2]) as archive:
        selected_sources = {name: archive.read('assets/addons/service.smarted.bootstrap/'+name).decode() for name in
                            ('smart_ads.py', 'variante.py', 'ads_regra.py', 'ads_vast.py', 'ad_return.py')}
    payload = base64.b64encode(gzip.compress(json.dumps(selected_sources).encode())).decode()
    parts = [payload[i:i+18000] for i in range(0, len(payload), 18000)]
    for i, part in enumerate(parts):
        print('::notice title=Read-only native source chunks::' + json.dumps(dict(part=i, total=len(parts), data=part)))
