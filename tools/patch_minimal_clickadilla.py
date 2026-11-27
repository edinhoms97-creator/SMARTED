#!/usr/bin/env python3
"""Fresh pinned Dropbox APK: network + tracking only, no player-flow patches."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import zipfile

from apk_pipeline import ROOT, CONFIG, verify_base, write_json
from apk_preservation import patch
from patch_original_ads import replace_functions

PLAN = ROOT / 'android-build/clickadilla-minimal-plan.json'
FOLDER = ROOT / 'android-build/clickadilla-minimal'
TAG = 'https://vast.yomeno.xyz/vast?spot_id=1508180'
BASE = 'assets/addons/service.smarted.bootstrap/'


def tracking_only_playback(source):
    """Exact reviewed edits to pixels only; all native control calls stay put.

    The original loop prematurely sent Impression before PlayMedia and always
    sent complete even on stall. Fix event truthfulness, not playback policy.
    Near-end break, stalls, waits, focus, restore and success receipt stay base.
    """
    edits = [
        ("    _disparar_eventos(anuncio.get('impressao') or [])\n",
         "    from ads_tracking import playback_events, expand, device_user_agent\n"
         "    _tracking = playback_events(xbmc)\n"
         "    def _tracking_error():\n"
         "        _disparar_eventos([expand(url, error_code=405, user_agent=device_user_agent(xbmc)) for url in anuncio.get('errors') or []])\n"),
        ("        return {'exibido': False, 'motivo': 'player-recusou'}",
         "        _tracking.active = False\n        _tracking_error()\n        return {'exibido': False, 'motivo': 'player-recusou'}"),
        ("        return {'exibido': False, 'motivo': 'nao-iniciou'}",
         "        _tracking.active = False\n        _tracking_error()\n        return {'exibido': False, 'motivo': 'nao-iniciou'}"),
        ("    _disparar_eventos((anuncio.get('eventos') or {}).get('start') or [])\n    disparados = set(['start'])",
         "    _tracking.active = True\n    disparados = set()"),
        ("        posicao, duracao = _posicao_e_duracao()\n",
         "        posicao, duracao = _posicao_e_duracao()\n"
         "        if posicao > 0.01 and 'start' not in disparados and not _audio_sem_quadro_video():\n"
         "            _disparar_eventos(anuncio.get('impressao') or [])\n"
         "            _disparar_eventos((anuncio.get('eventos') or {}).get('start') or [])\n"
         "            disparados.add('start')\n"),
        ("                if nome in disparados:\n", "                if nome in disparados or 'start' not in disparados:\n"),
        ("                if fracao + 0.01 >= quarto:\n",
         "                if fracao + 0.01 >= quarto and (nome != 'complete' or posicao >= duracao):\n"),
        ("                disparados.add('complete')\n                break",
         "                if 'start' in disparados and posicao >= duracao and 'complete' not in disparados:\n"
         "                    _disparar_eventos((anuncio.get('eventos') or {}).get('complete') or [])\n"
         "                    disparados.add('complete')\n                break"),
        ("    if 'complete' not in disparados:\n        disparados.add('complete')\n        _disparar_eventos((anuncio.get('eventos') or {}).get('complete') or [])",
         "    if 'start' in disparados:\n"
         "        if _tracking.ended and 'complete' not in disparados:\n"
         "            _disparar_eventos((anuncio.get('eventos') or {}).get('complete') or [])\n"
         "            disparados.add('complete')\n"
         "        elif _tracking.stopped and 'complete' not in disparados:\n"
         "            _disparar_eventos((anuncio.get('eventos') or {}).get('skip') or [])\n"
         "            disparados.add('skip')\n"
         "    _tracking.active = False"),
    ]
    updated = source
    for old, new in edits:
        if updated.count(old) != 1:
            raise ValueError('Original tracking call site changed: ' + old[:70])
        updated = updated.replace(old, new, 1)
    # Deactivate the diagnostic observer even on the base's early black-frame return.
    old = "                return {'exibido': False, 'motivo': 'tela-preta-sem-quadro'"
    if updated.count(old) != 1:
        raise ValueError('Original no-frame receipt changed')
    updated = updated.replace(old, "                _tracking.active = False\n                _tracking_error()\n" + old, 1)
    return updated


def native_control_calls(source):
    names = {'tocar', '_tocar', '_aguardar_anuncio_tocar', '_player_tocando_video',
             '_garantir_tela_cheia', '_desligar_surface_tela_preta',
             '_posicao_e_duracao', '_agora', 'dormir'}
    return [ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names]


def patch_sources(originals):
    result = {}
    for name in ('ads_vast.py', 'smart_ads.py'):
        original = originals[name]
        code = (FOLDER / name).read_text()
        if name == 'ads_vast.py':
            fn = next(n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef) and n.name == 'reproduzir')
            playback = ast.unparse(fn)
            updated = tracking_only_playback(playback)
            if native_control_calls(playback) != native_control_calls(updated):
                raise ValueError('Tracking patch changed native player controls')
            code += '\n\n' + updated + '\n'
        result[name] = replace_functions(original, code, {'VAST_TAG_PADRAO': TAG})
    result['ads_tracking.py'] = (FOLDER / 'ads_tracking.py').read_text()
    return result


def build(base, output, work, report):
    verify_base(base)
    plan = json.loads(PLAN.read_text())
    if plan['base_dropbox_content_hash'] != CONFIG['dropbox_content_hash']:
        raise ValueError('Minimal plan base mismatch')
    with zipfile.ZipFile(base) as archive:
        originals = {name: archive.read(BASE + name).decode('utf-8') for name in ('ads_vast.py', 'smart_ads.py')}
    updated = patch_sources(originals)
    work.mkdir(parents=True, exist_ok=True)
    for name, code in updated.items():
        compile(code, name, 'exec')
        (work / name).write_text(code)
    result = patch(base, output, {BASE + name: code.encode('utf-8') for name, code in updated.items()}, plan)
    # Scope attestation against the actual APK, not against previous patches.
    old = {n.name: n for n in ast.parse(originals['ads_vast.py']).body if isinstance(n, ast.FunctionDef)}
    new = {n.name: n for n in ast.parse(updated['ads_vast.py']).body if isinstance(n, ast.FunctionDef)}
    protected = ('_tocar', '_media_escolhido', 'restaurar', 'exibir_e_devolver', 'estado_do_conteudo', '_disparar_eventos')
    for name in protected:
        if ast.dump(old[name]) != ast.dump(new[name]):
            raise ValueError('Original protected player/parser function changed: ' + name)
    old_smart = ast.parse(originals['smart_ads.py'])
    old_monitor = next(n for n in old_smart.body if isinstance(n, ast.ClassDef) and n.name == 'MonitorPreRoll')
    new_monitor = next(n for n in ast.parse(updated['smart_ads.py']).body if isinstance(n, ast.ClassDef) and n.name == 'MonitorPreRoll')
    if ast.dump(old_monitor) != ast.dump(new_monitor):
        raise ValueError('Original monitor changed')
    tag_value = next(n.value for n in ast.parse(originals['ads_vast.py']).body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'VAST_TAG_PADRAO' for t in n.targets))
    result.update(profile='original-tag-tracking-only', source_original_tag_host=urlsplit(ast.literal_eval(tag_value)).hostname,
                  original_native_player_and_monitor=True, original_frequency_and_resume=True,
                  protected_function_hashes={name: hashlib.sha256(ast.dump(old[name]).encode()).hexdigest() for name in protected})
    write_json(report, result)
    print('::notice title=Minimal Clickadilla source audit::' + json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    build(args.base, args.output, args.work, args.report)
