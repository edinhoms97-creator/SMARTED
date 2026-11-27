#!/usr/bin/env python3
"""Read-only metadata for original APK-link contracts; no private config dump."""
import ast
import hashlib
import json
import sys
import zipfile
from inspect_ad_contract import Redact

TARGET = 'assets/addons/script.smartedtv.welcome/default.py'
with zipfile.ZipFile(sys.argv[1]) as archive:
    data = archive.read(TARGET)
    tree = ast.parse(data.decode('utf-8-sig'))
    constants = [ast.unparse(Redact().visit(node)) for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in ('APK_DOWNLOAD', 'DROPBOX_URL')
                         for target in node.targets)]
    text = json.dumps({'path': TARGET, 'sha256': hashlib.sha256(data).hexdigest(),
                       'apk_constants': constants})
    print('::notice title=SMARTED controls contract::' + text.replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D'))
