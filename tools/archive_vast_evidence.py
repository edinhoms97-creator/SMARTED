#!/usr/bin/env python3
"""Durable evidence only. Excludes APKs/native sources; does not contact ad URLs."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
root=Path(sys.argv[1]);release=root/'release'
output=release/'VAST-1508249-evidence.zip'
sources=[root/'baseline/evidence',root/'after/evidence',root/'previous-live',root/'selection-before']
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('VAST-1508249/README.md',
        '# Evidencia VAST, leitura offline\n\n'
        'baseline/evidence e after/evidence: abra index.html e pastas numeradas. '
        'Quatro prints REAIS por tentativa, XML sanitizado, request/response com UTC/hash, eventos e resultado. '
        '001-003 em after sao chamadas reais; 004 em diante sao fixtures. '
        'previous-live e selection-before preservam os baselines ANTERIORES ao patch. '
        'Video fixture e padrao local, nao anuncio real. Browser NAO e Kodi Android. '
        'Pixels nao enviados pelo laboratorio. Nenhuma reexecucao e necessaria para ler as evidencias.\n')
    for folder in sources:
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.suffix not in ('.apk','.py'):
                z.write(p,'VAST-1508249/'+str(p.relative_to(root)))
    for p in sorted(root.glob('*.log')):
        z.write(p,'VAST-1508249/'+p.name)
    for name in ('exibir.diff','preservation.json','source-preservation.json','signature.txt','badging.txt','INSTALLATION.txt'):
        z.write(release/name,'VAST-1508249/audit/'+name)
digest=hashlib.sha256(output.read_bytes()).hexdigest()
(output.parent/(output.name+'.sha256')).write_text(digest+'  '+output.name+'\n')
print('::notice title=VAST durable evidence::'+json.dumps(dict(name=output.name,sha256=digest,bytes=output.stat().st_size)))
