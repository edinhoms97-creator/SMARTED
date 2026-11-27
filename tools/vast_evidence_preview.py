#!/usr/bin/env python3
"""Transfer one bounded REAL screenshot per Actions step (10 notice limit)."""
import base64
import io
import json
from pathlib import Path
import sys
from PIL import Image
root=Path(sys.argv[1]);attempt=sys.argv[2]
evidence=root/('after' if (root/'after').exists() else 'baseline')/'evidence'
im=Image.open(evidence/attempt/'04-playback-result.jpg')
im.thumbnail((660,492));out=io.BytesIO();im.save(out,format='JPEG',quality=25,optimize=True)
data=base64.b64encode(out.getvalue()).decode()
if len(data)>9*3500:raise ValueError('Bounded preview exceeded annotation budget; full PNG retained')
for i in range(0,len(data),3500):
    print('::notice title=VAST visual preview::'+json.dumps(dict(attempt=attempt,part=i//3500,total=(len(data)+3499)//3500,data=data[i:i+3500])))
