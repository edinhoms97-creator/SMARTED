#!/usr/bin/env python3
"""Preserve actual before/after lab artifacts and narrow function diffs, not APKs."""
import hashlib,json
from pathlib import Path
import sys,zipfile
root=Path(sys.argv[1]);release=root/'release';out=release/'history-recovery-evidence.zip'
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('history-recovery/README.md',
        '# Comparacao SMARTEDTV, leitura offline\n\n'
        'comparison-before/historical/evidence e current/evidence: APKs publicados anteriores. '
        'after/evidence: APK novo. Abra cada index.html; pastas 001-036 tem quatro PNG reais por tentativa, XML sanitizado, JSON e logs. '
        '001-003 sao chamadas ao provedor, demais sao fixtures; nenhuma impressao enviada. '
        'budget-before e audit/*budget*: HTTP LOCAL com atrasos reais / relogio virtual, NAO inventario do provedor. '
        'startup-before-after.json e teste com doubles, nao captura da UI Android. '
        'Browser toca padrao local de teste, nao anuncio real. Ver auditoria e diferencas exatas de duas funcoes.\n')
    for folder in (root/'comparison-before',root/'budget-before',root/'after/evidence'):
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.suffix not in ('.apk','.py'):
                z.write(p,'history-recovery/'+str(p.relative_to(root)))
    for p in sorted(release.iterdir()):
        if p.is_file() and p.suffix in ('.json','.diff','.txt'):
            z.write(p,'history-recovery/audit/'+p.name)
    for p in sorted(root.glob('*.log')):
        z.write(p,'history-recovery/'+p.name)
digest=hashlib.sha256(out.read_bytes()).hexdigest()
(out.parent/(out.name+'.sha256')).write_text(digest+'  '+out.name+'\n')
print('::notice title=Recovery durable evidence::'+json.dumps(dict(name=out.name,bytes=out.stat().st_size,sha256=digest)))
