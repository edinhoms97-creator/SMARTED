#!/usr/bin/env python3
"""Audited lifecycle layer over EXACT 9436b5e + already restored tracking.

No later player overlays are used. Each modified AST scope is listed and all
other functions/constants/classes are compared before writing the APK.
"""
import argparse
import ast
import copy
import hashlib
from pathlib import Path
import textwrap

from apk_pipeline import ROOT, verify_base, write_json
from apk_preservation import patch, compare
import restore_confirmed_tracking as reference

FOLDER = ROOT / 'android-build/stabilize-9436'
PREFIX = 'assets/addons/service.smarted.bootstrap/'
SCOPES = {
    'smart_ads.py': {'abrir_anuncio', 'iniciar_monitor', 'tocar_anuncio_de_video',
                     'MonitorPreRoll._talvez_mostrar', 'MonitorPreRoll._disparar',
                     'MonitorPreRoll._ciclo_vast', 'MonitorPreRoll.onPlayBackStopped',
                     'MonitorPreRoll.onPlayBackEnded'},
    'ads_vast.py': {'exibir', 'reproduzir', 'restaurar', 'exibir_e_devolver',
                    'disparar', '_disparar_eventos'},
}
ALIASES = {'iniciar_monitor': '_smarted_iniciar_monitor_original',
           'MonitorPreRoll._talvez_mostrar': '_smarted_talvez_mostrar_original',
           'MonitorPreRoll.onPlayBackStopped': '_smarted_stop_original',
           'MonitorPreRoll.onPlayBackEnded': '_smarted_end_original'}


def nodes(source):
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            result[node.name] = node
        if isinstance(node, ast.ClassDef):
            for method in node.body:
                if isinstance(method, ast.FunctionDef):
                    result[node.name + '.' + method.name] = method
    return result


def replace(source, replacements, aliases=None):
    """Preserve untouched bytes, including constants/imports and native helpers."""
    found = nodes(source)
    lines = source.splitlines(keepends=True)
    edits = []
    for key, body in replacements.items():
        node = found[key]
        indent = ' ' * node.col_offset
        fragment = ''.join(lines[node.lineno - 1:node.end_lineno])
        text = textwrap.indent(body.rstrip() + '\n', indent)
        alias = (aliases or {}).get(key)
        if alias:
            if any(n.name == alias for n in found.values()):
                raise ValueError('Alias collision: ' + alias)
            text = fragment.replace('def ' + node.name + '(', 'def ' + alias + '(', 1).rstrip() + '\n\n' + text
        edits.append((node.lineno - 1, node.end_lineno, text))
    for start, end, text in sorted(edits, reverse=True):
        lines[start:end] = [text]
    updated = ''.join(lines)
    compile(updated, '<stabilized-9436>', 'exec')
    return updated


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Reference snippet mismatch: ' + old[:100])
    return text.replace(old, new, 1)


def function(source, name):
    return ast.get_source_segment(source, nodes(source)[name])


def audit(old, new, name):
    allowed = SCOPES[name]
    alias_keys = {key.rsplit('.', 1)[0] + '.' + alias if '.' in key else alias
                  for key, alias in ALIASES.items() if key in allowed}
    before, after = nodes(old), nodes(new)
    if set(after) - set(before) != alias_keys:
        raise ValueError('Unexpected added scopes: ' + name)
    if set(before) - set(after):
        raise ValueError('Removed scopes: ' + name)
    for key in before.keys() - allowed:
        if ast.dump(before[key]) != ast.dump(after[key]):
            raise ValueError('Changed outside lifecycle allowlist: ' + key)
    # Remove reviewed functions/methods plus aliases; all remaining AST must match.
    def unmodified(source):
        tree = ast.parse(source)
        body = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in allowed | alias_keys:
                continue
            if isinstance(node, ast.ClassDef):
                node = copy.deepcopy(node)
                node.body = [child for child in node.body if not isinstance(child, ast.FunctionDef)
                             or node.name + '.' + child.name not in allowed | alias_keys]
            body.append(ast.dump(node))
        return body
    if unmodified(old) != unmodified(new):
        raise ValueError('Unreviewed constants/imports/classes changed: ' + name)


def transform_smart(source):
    overlay = (FOLDER / 'smart_ads.py').read_text()
    changes = {key: textwrap.dedent(ast.get_source_segment(overlay, node))
               for key, node in nodes(overlay).items()}
    dispatch = function(source, 'tocar_anuncio_de_video')
    dispatch = once(dispatch, "        success = bool(receipt.get('exibido'))", "        globals()['_smarted_last_receipt'] = receipt\n        success = bool(receipt.get('exibido'))")
    changes['tocar_anuncio_de_video'] = dispatch
    updated = replace(source, changes, ALIASES)
    audit(source, updated, 'smart_ads.py')
    return updated


def transform_vast(source):
    changes = {}
    exibir = function(source, 'exibir')
    exibir = once(exibir, '    import xml.etree.ElementTree as _ET', '    from ads_openings import emit\n    import xml.etree.ElementTree as _ET')
    exibir = once(exibir, '    def failure(reason, code):', "    def failure(reason, code):\n        emit(xbmc, 'vast-result', reason=reason)")
    exibir = once(exibir, '        try:\n            # Exact reference', "        emit(xbmc, 'vast-request', hop=len(visited), wrapper=current != tag)\n        try:\n            # Exact reference")
    exibir = once(exibir, '        if data is None:', "        emit(xbmc, 'vast-response', received=data is not None, size=len(data or b''))\n        if data is None:")
    exibir = once(exibir, '            ad = dict(ad)', "            emit(xbmc, 'creative-selected')\n            ad = dict(ad)")
    changes['exibir'] = exibir

    playback = function(source, 'reproduzir')
    playback = once(playback, '    tocar = tocar or _tocar', '    from ads_openings import emit\n    tocar = tocar or _tocar')
    playback = once(playback, '                                started = True', "                                started = True\n                                emit(xbmc, 'ad-start-observed', position=position)")
    playback = once(playback, "                                _disparar_eventos(anuncio.get('impressao') or [])", "                                emit(xbmc, 'impression-queued', pixels=len(anuncio.get('impressao') or []))\n                                _disparar_eventos(anuncio.get('impressao') or [])")
    playback = once(playback, "                                fired.add('start')", "                                fired.add('start')\n                                emit(xbmc, 'tracking-event-queued', event='start')")
    playback = playback.replace('                                        fired.add(name)', "                                        fired.add(name)\n                                        emit(xbmc, 'tracking-event-queued', event=name)")
    # Exact completion block, not the inner quartile loop.
    playback = once(playback, "                fired.add(name)\n    elif reason == 'pulado'", "                fired.add(name)\n                emit(xbmc, 'tracking-event-queued', event=name)\n    elif reason == 'pulado'")
    playback = once(playback, '    eligible = started', "    emit(xbmc, 'ad-player-released', reason=reason, started=started)\n    eligible = started")
    changes['reproduzir'] = playback

    restore = function(source, 'restaurar')
    restore = once(restore, '    if not estado', "    from ads_openings import emit\n    emit(xbmc, 'resume-begin')\n    if not estado")
    restore = once(restore, '    for route in candidates:', "    for route_index, route in enumerate(candidates):\n        if agora() >= deadline:\n            break\n        emit(xbmc, 'resume-route', index=route_index, plugin=route.startswith('plugin://'))")
    # Do not reset an already-positioned decoder, especially time zero. Original
    # candidate order, fallback, native seek and positive-target confirmation stay.
    restore = once(restore, '            if not live:\n                player.seekTime(target)', "            if not live and target > 0 and abs(float(player.getTime()) - target) > .25:\n                player.seekTime(target)")
    restore = once(restore, '            return True', "            emit(xbmc, 'content-released', live=live)\n            return True")
    changes['restaurar'] = restore

    flow = function(source, 'exibir_e_devolver')
    flow = once(flow, '    def start_ad(url, logger):', "    changed = [False]\n    def start_ad(url, logger):")
    flow = once(flow, '            return False  # user changed', '            changed[0] = True\n            return False  # user changed')
    flow = once(flow, '    # A user selecting another film', "    if changed[0]:\n        receipt['motivo'] = 'conteudo-alterado'\n    # A user selecting another film")
    changes['exibir_e_devolver'] = flow

    pixels = function(source, 'disparar')
    pixels = once(pixels, '    import ssl', '    from ads_openings import emit, batch_id\n    batch = batch_id()\n    emit(xbmc, \'tracking-http-batch\', batch=batch, pixels=len(urls or []))\n    import ssl')
    pixels = once(pixels, '            response.close()', "            emit(xbmc, 'tracking-http-response', batch=batch, status=response.getcode())\n            response.close()")
    pixels = once(pixels, '        except Exception:\n            pass', "        except Exception as exc:\n            emit(xbmc, 'tracking-http-failure', batch=batch, error=type(exc).__name__)\n            pass")
    changes['disparar'] = pixels
    # Capture the opening before crossing into the pixel background thread.
    changes['_disparar_eventos'] = '''def _disparar_eventos(urls):
    if not urls:
        return 0
    if disparar is not _DISPARAR_PADRAO:
        return disparar(urls)
    from ads_openings import current, context
    opening = current()
    copy_urls = list(urls)
    def send():
        context(opening)
        disparar(copy_urls)
    threading.Thread(target=send, name='vast-tracking', daemon=True).start()
    return len(copy_urls)
'''
    updated = replace(source, changes)
    audit(source, updated, 'ads_vast.py')
    return updated


def build(base, output, work, report):
    verify_base(base)
    plan, original = reference.reference_payload(base)
    baseline = dict(original)
    baseline[reference.AD] = reference.update_tracking(original[reference.AD].decode()).encode()
    baseline[reference.HELPER] = reference.HELPER_SOURCE.read_bytes()
    plan['changes'][reference.HELPER] = {'new_file': True, 'original_sha256': None}
    work.mkdir(parents=True, exist_ok=True)
    reference_apk = work / 'reference-9436b5e-tracking.apk'
    patch(base, reference_apk, baseline, plan)
    updated = dict(baseline)
    updated[PREFIX + 'smart_ads.py'] = transform_smart(baseline[PREFIX + 'smart_ads.py'].decode()).encode()
    updated[reference.AD] = transform_vast(baseline[reference.AD].decode()).encode()
    helper_path = PREFIX + 'ads_openings.py'
    updated[helper_path] = (FOLDER / 'ads_openings.py').read_bytes()
    plan['changes'][helper_path] = {'new_file': True, 'original_sha256': None}
    plan['policy'] = '9436b5e + restored tracking + explicitly audited opening lifecycle and transition scopes; no native helper/constants/provider/ABI/UI changes.'
    write_json(work / 'plan.json', plan)
    for path, code in updated.items():
        compile(code, path, 'exec')
        (work / Path(path).name).write_bytes(code)
    (work / 'reference_tests.py').write_text(reference.historical('tools/test_original_ad_patch.py'))
    result = patch(base, output, updated, plan)
    comparison = compare(reference_apk, output, {reference.AD, PREFIX + 'smart_ads.py', helper_path})
    result.update(reference_commit=reference.REFERENCE, reference_build=45996397116,
                  comparison_with_confirmed_reference_and_tracking=comparison,
                  audited_scopes={k: sorted(v) for k, v in SCOPES.items()},
                  tag=reference.TAG, no_new_request_parameters=True,
                  source_sha256={p: hashlib.sha256(c).hexdigest() for p, c in updated.items()})
    write_json(report, result)
    print('::notice title=Stabilized reference lifecycle audit::' + __import__('json').dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    build(args.base, args.output, args.work, args.report)
