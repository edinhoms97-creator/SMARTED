#!/usr/bin/env python3
"""Patch ONLY audited ad functions in the exact SMARTEDTV original APK."""
import argparse
import ast
import json
from pathlib import Path
import zipfile

from apk_pipeline import CONFIG, ROOT, verify_base, write_json
from apk_preservation import patch


def replace_functions(original, replacements, constants=None):
    """Textual spans preserve every untouched byte; AST checks bound scope."""
    tree = ast.parse(original)
    replacement_tree = ast.parse(replacements)
    functions = {node.name: node for node in replacement_tree.body if isinstance(node, ast.FunctionDef)}
    original_functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not set(functions).issubset(original_functions):
        raise ValueError('Original ad function contract changed')
    constants = constants or {}
    lines = original.splitlines(keepends=True)
    edits = []
    for name, replacement in functions.items():
        node = original_functions[name]
        fragment = ''.join(lines[node.lineno - 1:node.end_lineno])
        text = ast.get_source_segment(replacements, replacement) + '\n'
        if name == 'restaurar':
            if '_smarted_restaurar_original' in original_functions:
                raise ValueError('Unexpected already-patched original')
            text = fragment.replace('def restaurar(', 'def _smarted_restaurar_original(', 1).rstrip() + '\n\n' + text
        edits.append((node.lineno - 1, node.end_lineno, text))
    found_constants = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in constants:
                edits.append((node.lineno - 1, node.end_lineno, name + ' = ' + repr(constants[name]) + '\n'))
                found_constants.add(name)
    if found_constants != set(constants):
        raise ValueError('Original ad constants changed')
    for start, end, text in sorted(edits, reverse=True):
        lines[start:end] = [text]
    updated = ''.join(lines)
    compiled = ast.parse(updated)
    ignored_functions = set(functions) | {'_smarted_restaurar_original'}

    def unaffected(module):
        nodes = []
        for node in module.body:
            if isinstance(node, ast.FunctionDef) and node.name in ignored_functions:
                continue
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets):
                continue
            nodes.append(ast.dump(node, include_attributes=False))
        return nodes

    if unaffected(tree) != unaffected(compiled):
        raise ValueError('Unexpected change outside reviewed ad functions/constants')
    compile(updated, '<patched-original-ads>', 'exec')
    return updated


def build(base, output, work, report):
    verify_base(base)  # no alternative APK, even with a different custom hash
    plan = json.loads((ROOT / 'android-build/ads-only-plan.json').read_text())
    if plan['base_dropbox_content_hash'] != CONFIG['dropbox_content_hash']:
        raise ValueError('Patch plan does not identify the pinned original')
    replacements = {}
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    folder = ROOT / 'android-build/ads-patches'
    with zipfile.ZipFile(base) as archive:
        for path, entry in plan['changes'].items():
            name = Path(path).name
            code = (folder / name).read_text()
            if entry.get('new_file'):
                updated = code
            else:
                original = archive.read(path).decode('utf-8')
                constants = {'TIMEOUT_HTTP': 8, 'VAST_TAG_PADRAO': 'https://vast.yomeno.xyz/vast?spot_id=1508180'} if name == 'ads_vast.py' else {}
                updated = replace_functions(original, code, constants)
            compile(updated, name, 'exec')
            replacements[path] = updated.encode('utf-8')
            (work / name).write_bytes(replacements[path])
    result = patch(base, output, replacements, plan)
    result['base_dropbox_content_hash'] = CONFIG['dropbox_content_hash']
    result['original_package'] = plan['package']
    result['original_version_name'] = plan['version_name']
    write_json(report, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.base, args.output, args.work, args.report)))
    except Exception as exc:
        safe = str(exc).replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D')
        print('::error title=Ads-only original APK gate::' + safe, flush=True)
        raise
