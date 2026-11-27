#!/usr/bin/env python3
"""Static original ad lifecycle/history inventory. Never executes APK sources."""
import ast
import base64
import hashlib
import json
import re
import sys
import zipfile
from urllib.parse import urlsplit, parse_qs
from inspect_ad_contract import Redact

with zipfile.ZipFile(sys.argv[1]) as archive:
    selected, inventory = {}, []
    for filename, names in (
        ('ads_vast.py', ('_tocar', '_garantir_tela_cheia', '_disparar_eventos', 'resumo')),
        ('smart_ads.py', ('_e_video', '_ads_vast', 'iniciar_monitor', 'esquecer', '_chave_conteudo', '_normalizar_caminho_chave')),
        ('ad_return.py', ('Retomada',)),
    ):
        path = 'assets/addons/service.smarted.bootstrap/' + filename
        if path not in archive.namelist():
            continue
        raw = archive.read(path)
        tree = ast.parse(raw.decode('utf-8-sig'))
        if filename == 'ads_vast.py':
            constants = {target.id: node.value for node in tree.body if isinstance(node, ast.Assign)
                         for target in node.targets if isinstance(target, ast.Name)}
            tag = ast.literal_eval(constants['VAST_TAG_PADRAO'])
            old, new = urlsplit(tag), urlsplit('https://vast.yomeno.xyz/vast?spot_id=1508180')
            old_spot = parse_qs(old.query).get('spot_id', [''])[0]
            selected['source_comparison'] = {
                'original_host': old.hostname, 'clickadilla_host': new.hostname,
                'same_path': old.path == new.path, 'same_query': old.query == new.query,
                'same_spot_id': old_spot == '1508180',
                'original_numeric_spot_id': old_spot if old_spot.isdigit() else None,
                'original_tag_fingerprint': hashlib.sha256(tag.encode()).hexdigest(),
                'other_original_parameter_names': sorted(set(parse_qs(old.query)) - {'spot_id'}),
            }
            selected['original_player_limits'] = {name: ast.literal_eval(constants[name]) for name in
                ('FOLGA_FIM', 'TEMPO_MAXIMO_ANUNCIO', 'TEMPO_TRAVAMENTO_ANUNCIO', 'TEMPO_TELA_PRETA_AUDIO', 'PROFUNDIDADE_WRAPPER')
                if name in constants}
        if filename == 'smart_ads.py':
            selected['initial_ad_state'] = {target.id: ast.unparse(Redact().visit(node.value)) for node in tree.body if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name) and target.id in ('_ultima_sessao', '_ultimo_caminho_preroll', '_monitor')}
        selected[filename] = {node.name: ast.unparse(Redact().visit(node)) for node in tree.body
                              if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names}
    for path in archive.namelist():
        if not (path.startswith('assets/addons/service.smarted.bootstrap/') and path.endswith(('.py','.json','.xml'))):
            continue
        raw = archive.read(path)
        if b'hilltop' in raw.lower():
            hosts = sorted(set(urlsplit(url).hostname or '' for url in re.findall(r'https?://[^\s<>\x22\x27]+', raw.decode('utf-8','replace')) if 'hilltop' in url.lower()))
            inventory.append({'path': path, 'sha256': hashlib.sha256(raw).hexdigest(), 'hilltop_hosts': hosts, 'hilltop_comment_lines': [line[:220] for line in raw.decode('utf-8','replace').splitlines() if 'hilltop' in line.lower() and 'http' not in line.lower()][:8]})
    payload = base64.b64encode(json.dumps({'selected':selected,'hilltop_inventory':inventory}).encode()).decode()
    for i in range(0, len(payload), 3600):
        print('::notice title=SMARTED lifecycle inventory::' + json.dumps({'part': i // 3600, 'data': payload[i:i+3600]}))
