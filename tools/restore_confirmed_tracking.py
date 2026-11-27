#!/usr/bin/env python3
"""Restore user-confirmed build 45996397116 / 9436b5e; change tracking only."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import textwrap
import zipfile

from apk_pipeline import ROOT, verify_base, write_json
from apk_preservation import patch, compare
from patch_original_ads import replace_functions

REFERENCE = '9436b5ef63fe1e4d569328990c92ab1514ce9b0b'
AD = 'assets/addons/service.smarted.bootstrap/ads_vast.py'
HELPER = 'assets/addons/service.smarted.bootstrap/ads_tracking.py'
TAG = 'https://vast.yomeno.xyz/vast?spot_id=1508180'
OVERLAY = ROOT / 'android-build/confirmed-tracking/ads_vast.py'
HELPER_SOURCE = ROOT / 'android-build/ads-patches/ads_tracking.py'


def historical(path):
    return subprocess.check_output(['git', 'show', REFERENCE + ':' + path], cwd=ROOT).decode('utf-8')


def reference_replace():
    # Use the exact historical text/AST patcher, not the later expanded one.
    tree = ast.parse(historical('tools/patch_original_ads.py'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'replace_functions')
    env = dict(ast=ast, copy=copy, textwrap=textwrap)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<trusted-historical-patcher>', 'exec'), env)
    return env['replace_functions']


def reference_payload(base):
    plan = json.loads(historical('android-build/ads-only-plan.json'))
    replace = reference_replace()
    result = {}
    with zipfile.ZipFile(base) as archive:
        for path, entry in plan['changes'].items():
            name = Path(path).name
            code = historical('android-build/ads-patches/' + name)
            if entry.get('new_file'):
                updated = code
            else:
                constants = ({'TIMEOUT_HTTP': 8, 'VAST_TAG_PADRAO': TAG} if name == 'ads_vast.py'
                             else {'INTERVALO': 0} if name == 'ads_regra.py' else {})
                updated = replace(archive.read(path).decode('utf-8'), code, constants)
            result[path] = updated.encode('utf-8')
    return plan, result


def player_without_error(source):
    fn = copy.deepcopy(next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'reproduzir'))
    for node in ast.walk(fn):
        if isinstance(node, ast.FunctionDef) and node.name == 'error':
            node.body = [ast.Pass()]
    return ast.dump(fn, include_attributes=False)


def update_tracking(reference):
    fn = next(n for n in ast.parse(reference).body if isinstance(n, ast.FunctionDef) and n.name == 'reproduzir')
    playback = ast.get_source_segment(reference, fn)
    old = "        _disparar_eventos([url.replace('[ERRORCODE]', '405') for url in urls])"
    new = "        from ads_tracking import expand, device_user_agent\n        _disparar_eventos([expand(url, error_code=405, user_agent=device_user_agent(xbmc)) for url in urls])"
    if playback.count(old) != 1:
        raise ValueError('Confirmed reference Error pixel contract changed')
    playback = playback.replace(old, new, 1)
    updated = replace_functions(reference, OVERLAY.read_text() + '\n\n' + playback + '\n')
    if player_without_error(reference) != player_without_error(updated):
        raise ValueError('Tracking-only patch changed playback flow')
    before = {n.name: n for n in ast.parse(reference).body if isinstance(n, ast.FunctionDef)}
    after = {n.name: n for n in ast.parse(updated).body if isinstance(n, ast.FunctionDef)}
    allowed = {'disparar', 'exibir', 'reproduzir'}
    for name in before.keys() | after.keys():
        if name not in allowed and ast.dump(before[name]) != ast.dump(after[name]):
            raise ValueError('Change outside tracking: ' + name)
    # No constant changes: URL, zone, budgets and all other settings stay reference.
    constants = lambda source: [ast.dump(n) for n in ast.parse(source).body if not isinstance(n, ast.FunctionDef)]
    if constants(reference) != constants(updated):
        raise ValueError('Tracking changed reference constants/non-function code')
    return updated


def build(base, output, work, report):
    verify_base(base)
    plan, reference = reference_payload(base)
    work.mkdir(parents=True, exist_ok=True)
    reference_apk = work / 'reference-9436b5e.apk'
    patch(base, reference_apk, reference, plan)
    updated = dict(reference)
    updated[AD] = update_tracking(reference[AD].decode()).encode()
    updated[HELPER] = HELPER_SOURCE.read_bytes()
    plan['changes'][HELPER] = {'new_file': True, 'original_sha256': None}
    plan['policy'] = 'User-confirmed 9436b5e restored exactly; only ads_vast tracking and new ads_tracking helper differ from that reference.'
    write_json(work / 'plan.json', plan)
    for path, code in updated.items():
        compile(code, path, 'exec')
        (work / Path(path).name).write_bytes(code)
    (work / 'reference_tests.py').write_text(historical('tools/test_original_ad_patch.py'))
    result = patch(base, output, updated, plan)
    reference_diff = compare(reference_apk, output, {AD, HELPER})
    result.update(reference_commit=REFERENCE, reference_build=45996397116,
                  comparison_with_confirmed_reference=reference_diff,
                  player_control_ast_identical=True, nontracking_modules_identical=True,
                  tag=TAG, tag_transport_identical=True, frequency='one-attempt-per-opening-no-cooldown',
                  source_module_hashes={path: hashlib.sha256(code).hexdigest() for path, code in reference.items()})
    write_json(report, result)
    print('::notice title=Confirmed reference tracking-only audit::' + json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    build(args.base, args.output, args.work, args.report)
