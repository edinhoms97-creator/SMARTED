#!/usr/bin/env python3
"""Read-only, redacted original ad startup/gate contract; never execute APK code."""
import ast
import base64
import json
import sys
import zipfile
from inspect_ad_contract import Redact

with zipfile.ZipFile(sys.argv[1]) as archive:
    selected = {}
    for filename, names in (
        ('ads_vast.py', ('_tocar', '_arquivo_atual', '_player_tocando_video', '_audio_sem_quadro_video', '_garantir_tela_cheia')),
        ('smart_ads.py', ('tocar_anuncio', 'vast_disponivel', 'abrir_anuncio_vast', 'vip_ativo', 'iniciar_monitor')),
    ):
        tree = ast.parse(archive.read('assets/addons/service.smarted.bootstrap/' + filename).decode('utf-8-sig'))
        selected[filename] = {node.name: ast.unparse(Redact().visit(node)) for node in tree.body
                              if isinstance(node, ast.FunctionDef) and node.name in names}
    payload = base64.b64encode(json.dumps(selected).encode()).decode()
    for i in range(0, len(payload), 3600):
        print('::notice title=SMARTED startup contract::' + json.dumps({'part': i // 3600, 'data': payload[i:i+3600]}))
