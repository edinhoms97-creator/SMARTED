#!/usr/bin/env python3
"""Expose bounded build/test failure details when Actions log redirects are blocked."""
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text(errors='replace')[-12000:]
for i in range(0, len(text), 2500):
    safe = text[i:i+2500].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::notice title=APK build failure detail %d::%s' % (i // 2500, safe))
