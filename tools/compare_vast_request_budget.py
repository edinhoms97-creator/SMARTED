#!/usr/bin/env python3
"""Virtual-clock replay of identical Wrapper XML. No network/pixels/player."""
import argparse,json
from pathlib import Path
from vast_visual_lab import read_module,TAG
from vast_selection_cases import wrapper,VALID,NEXT

def run(apk,work):
    env,kodi=read_module(apk,work)
    report={}
    for name,delays in [('chain-fast',[.1,.1,.1]),('chain-6s-valid',[2,2,2]),('chain-9s-valid',[3,3,3]),('chain-12s-valid',[4,4,4])]:
        now=[0.0];requests=[];selected=[]
        env['_agora']=lambda:now[0]
        env['_disparar_eventos']=lambda urls:0
        def player(ad,**kw):
            selected.append(ad)
            return dict(exibido=False,motivo='controlled-handoff-native-player-not-run')
        env['reproduzir']=player
        pages={TAG:wrapper(NEXT),NEXT:wrapper(NEXT+'2'),NEXT+'2':VALID}
        def fetch(url):
            now[0]+=delays[min(len(requests),len(delays)-1)]
            requests.append(dict(url=url,virtual_elapsed_seconds=now[0]))
            return pages.get(url)
        receipt=env['exibir'](tag=TAG,baixar_tag=fetch)
        report[name]=dict(virtual_clock_not_real_network=True,requests=requests,root_requests=sum(x['url']==TAG for x in requests),
            selected=bool(selected),receipt=receipt,native_ads_played=0,virtual_elapsed_seconds=now[0])
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--historical',type=Path,required=True);p.add_argument('--current',type=Path,required=True);p.add_argument('--after',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    r={name:run(apk,a.out.parent/(name+'-timing-modules')) for name,apk in [('historical',a.historical),('current',a.current)]+([('after',a.after)] if a.after else [])}
    assert r['historical']['chain-12s-valid']['selected']
    assert not r['current']['chain-12s-valid']['selected']
    if a.after:assert r['after']['chain-12s-valid']['selected']
    assert all(case['root_requests']==1 for cases in r.values() for case in cases.values())
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,indent=2)+'\n')
    print('::notice title=VAST request budget comparison::'+json.dumps(r))
