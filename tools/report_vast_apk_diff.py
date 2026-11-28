#!/usr/bin/env python3
"""Read-only forensic comparison of already published APKs. Never runs app/ad code."""
import ast
import base64
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

VERSIONS = {
    'tracking_restored': ('46028834505', 'f45cad169285cf511ac51d86660176972aa6d821d59791dab40d31235135b3a3'),
    'previous_candidate': ('46035861727', '1e8ca00f71b070a909561b793966f39c67540c80204d38c792322c20348ccbfb'),
    'immediate_intermediate': ('46043711441', 'ae3dd85e0cfd4954e6774b5f854d75a0f31992407cc50eda7f8ec1f5a32153b4'),
    'current': ('46044121903', '5187f34599911310dbf60dd2181b3ceac6d306b7d0ccc61a58fc1c4c051875c9'),
}
PREFIX = 'assets/addons/service.smarted.bootstrap/'


def scopes(text):
    result = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = ast.dump(node, include_attributes=False)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result[node.name + '.' + child.name] = ast.dump(child, include_attributes=False)
    return result


def inspect(apk):
    entries, modules, sources = {}, {}, {}
    with zipfile.ZipFile(apk) as archive:
        for name in archive.namelist():
            if name.endswith('/') or name.startswith('META-INF/'):
                continue
            data = archive.read(name)
            entries[name] = hashlib.sha256(data).hexdigest()
            if name.startswith(PREFIX) and name.endswith('.py'):
                text = data.decode('utf-8-sig')
                tree = ast.parse(text)
                modules[name] = {'sha256': entries[name], 'bytes': len(data),
                                 'scopes': scopes(text),
                                 'imports': sorted({n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} |
                                                   {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names})}
                sources[name] = text
    return entries, modules, sources


def main():
    output = Path('.cache/vast-apk-comparison'); output.mkdir(parents=True, exist_ok=True)
    records, inspected = {}, {}
    for label, (run, expected) in VERSIONS.items():
        folder = output / label; folder.mkdir(exist_ok=True)
        tag = 'smarted-original-ads-' + run + '-1'
        subprocess.run(['gh', 'release', 'download', tag, '--pattern', 'SMARTEDTV-universal.apk', '--dir', str(folder), '--clobber'], check=True)
        apk = folder / 'SMARTEDTV-universal.apk'
        actual = hashlib.sha256(apk.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('APK identity mismatch: ' + label)
        inspected[label] = inspect(apk)
        records[label] = {'release': tag, 'sha256': actual, 'bytes': apk.stat().st_size,
                          'bootstrap_scripts': {p: {k: v for k, v in m.items() if k != 'scopes'} for p, m in inspected[label][1].items()}}
    comparisons, diffs = {}, []
    current_entries, current_modules, current_sources = inspected['current']
    for label in VERSIONS:
        if label == 'current': continue
        entries, modules, sources = inspected[label]
        changed = sorted(p for p in entries.keys() | current_entries.keys() if entries.get(p) != current_entries.get(p))
        methods = {}
        for path in changed:
            if path not in modules and path not in current_modules: continue
            before = modules.get(path, {}).get('scopes', {})
            after = current_modules.get(path, {}).get('scopes', {})
            methods[path] = {'added': sorted(after.keys()-before.keys()), 'removed': sorted(before.keys()-after.keys()),
                             'changed': sorted(n for n in before.keys() & after.keys() if before[n] != after[n])}
            # Source patches are restricted to the VAST subsystem, not unrelated app/profile data.
            if Path(path).name.startswith('ads_') or Path(path).name == 'smart_ads.py':
                diffs.extend(difflib.unified_diff(sources.get(path, '').splitlines(True), current_sources.get(path, '').splitlines(True),
                                                fromfile=label+'/'+path, tofile='current/'+path))
        comparisons[label+'_to_current'] = {'changed_non_signature_entries': changed,
            'unchanged_non_signature_entries': sum(entries.get(p) == current_entries.get(p) for p in entries.keys() & current_entries.keys()),
            'script_scopes': methods}
    report = {'method': 'Actual signed release ZIP entries SHA-256; META-INF and ZIP signing blocks excluded; AST scope comparison does not execute scripts.',
              'versions': records, 'comparisons': comparisons}
    (output/'comparison.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    (output/'scripts.diff').write_text(''.join(diffs))
    # Native APK downloads may be inaccessible from the workspace. Carry only
    # small report/diff outputs in annotations; never APKs or runtime profiles.
    for title, content in [('VAST APK comparison chunks', json.dumps(report)), ('VAST source diff chunks', ''.join(diffs))]:
        payload = base64.b64encode(gzip.compress(content.encode())).decode()
        parts = [payload[i:i+2500] for i in range(0, len(payload), 2500)]
        for i, data in enumerate(parts):
            print('::notice title='+title+'::'+json.dumps({'part': i, 'total': len(parts), 'data': data}))


if __name__ == '__main__':
    main()
