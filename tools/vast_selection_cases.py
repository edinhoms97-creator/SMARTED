"""Controlled selection fixtures. No live inventory or real pixel endpoints."""
TAG='https://vast.yomeno.xyz/vast?spot_id=1508249'
MEDIA='https://fixture.invalid/creative.mp4'
NEXT='https://fixture.invalid/next'

def inline(media=MEDIA, mime='video/mp4', duration='00:00:05', attrs='', ident='chosen'):
    return f'<VAST version="3.0"><Ad id="{ident}"><InLine><AdSystem>ISOLATED FIXTURE</AdSystem><AdTitle>TEST PATTERN NOT AD</AdTitle><Impression>https://pixels.invalid/{ident}</Impression><Creatives><Creative id="{ident}"><Linear><Duration>{duration}</Duration><TrackingEvents><Tracking event="start">https://pixels.invalid/start-{ident}</Tracking></TrackingEvents><MediaFiles><MediaFile type="{mime}" {attrs}><![CDATA[{media}]]></MediaFile></MediaFiles></Linear></Creative></Creatives></InLine></Ad></VAST>'

def wrapper(url, ident='outer', legacy=False):
    name='VASTAdTagURL' if legacy else 'VASTAdTagURI'
    return f'<VAST version="3.0"><Ad><Wrapper><Impression>https://pixels.invalid/{ident}</Impression><Error>https://pixels.invalid/error-{ident}</Error><{name}><![CDATA[{url}]]></{name}><Creatives><Creative><Linear><TrackingEvents><Tracking event="start">https://pixels.invalid/start-{ident}</Tracking></TrackingEvents></Linear></Creative></Creatives></Wrapper></Ad></VAST>'

def ads(*xml):
    import xml.etree.ElementTree as ET
    r=ET.Element('VAST',version='3.0')
    for text in xml:
        for ad in ET.fromstring(text):r.append(ad)
    return ET.tostring(r,encoding='unicode')

def vmap(source, offset='start'):
    return f'<vmap:VMAP xmlns:vmap="http://www.iab.net/videosuite/vmap" version="1.0"><vmap:AdBreak timeOffset="{offset}" breakType="linear"><vmap:AdSource>{source}</vmap:AdSource></vmap:AdBreak></vmap:VMAP>'

VALID=inline()
# All root fetches target the authorized tag. Extra URLs exist only inside fixtures.
CASES=[
 dict(name='vast30-cdata',pages={TAG:VALID},selected=True),
 dict(name='vast30-namespace',pages={TAG:VALID.replace('<VAST ','<VAST xmlns="urn:iab:vast:3.0" ',1)},selected=True),
 dict(name='mediafile-later-valid',pages={TAG:VALID.replace('<MediaFiles>','<MediaFiles><MediaFile type="application/unsupported">https://fixture.invalid/bad.bin</MediaFile>')},selected=True),
 dict(name='second-ad-valid',pages={TAG:ads(inline(mime='application/unsupported'),VALID)},selected=True),
 dict(name='wrapper-one',pages={TAG:wrapper(NEXT),NEXT:VALID},selected=True,impressions=['https://pixels.invalid/outer','https://pixels.invalid/chosen']),
 dict(name='wrapper-chain',pages={TAG:wrapper(NEXT),NEXT:wrapper(NEXT+'2','middle'),NEXT+'2':VALID},selected=True,impressions=['https://pixels.invalid/outer','https://pixels.invalid/middle','https://pixels.invalid/chosen']),
 dict(name='wrapper-legacy-url',pages={TAG:wrapper(NEXT,legacy=True),NEXT:VALID},selected=True),
 dict(name='vmap-external',pages={TAG:vmap(f'<vmap:AdTagURI><![CDATA[{NEXT}]]></vmap:AdTagURI>'),NEXT:VALID},selected=True),
 dict(name='vmap-embedded',pages={TAG:vmap('<vmap:VASTAdData>'+VALID+'</vmap:VASTAdData>')},selected=True),
 dict(name='vmap-wrapper-chain',pages={TAG:vmap(f'<vmap:AdTagURI>{NEXT}</vmap:AdTagURI>'),NEXT:wrapper(NEXT+'2'),NEXT+'2':VALID},selected=True),
 dict(name='sibling-wrapper-after-empty',pages={TAG:ads(wrapper(NEXT,'discarded'),wrapper(NEXT+'2','selected')),NEXT:'<VAST/>',NEXT+'2':VALID},selected=True,impressions=['https://pixels.invalid/selected','https://pixels.invalid/chosen'],forbidden_impression='https://pixels.invalid/discarded'),
 dict(name='sibling-wrapper-after-malformed',pages={TAG:ads(wrapper(NEXT),wrapper(NEXT+'2','selected')),NEXT:'<invalid',NEXT+'2':VALID},selected=True),
 dict(name='sibling-wrapper-after-cycle',pages={TAG:ads(wrapper(TAG),wrapper(NEXT,'selected')),NEXT:VALID},selected=True),
 dict(name='vmap-next-preroll-after-empty',pages={TAG:vmap(f'<vmap:AdTagURI>{NEXT}</vmap:AdTagURI>').replace('</vmap:VMAP>',vmap(f'<vmap:AdTagURI>{NEXT}2</vmap:AdTagURI>')[vmap('').index('<vmap:AdBreak'):].replace('</vmap:VMAP>','')+'</vmap:VMAP>'),NEXT:'<VAST/>',NEXT+'2':VALID},selected=True),
 dict(name='linear-pairing',pages={TAG:VALID.replace('<Creative id="chosen">','<Creative id="wrong"><Linear><Duration>00:00:29</Duration><MediaFiles><MediaFile type="application/unsupported">https://fixture.invalid/bad</MediaFile></MediaFiles></Linear></Creative><Creative id="chosen">')},selected=True,duration=5.0),
 dict(name='relative-wrapper',pages={TAG:wrapper('/next'), 'https://vast.yomeno.xyz/next':VALID},selected=True),
 dict(name='namespace-single-quote',pages={TAG:VALID.replace('<VAST ',"<VAST xmlns='urn:iab:vast:3.0' ",1)},selected=True),
 dict(name='protocol-relative-media',pages={TAG:inline(media='//fixture.invalid/creative.mp4')},selected=True),
 dict(name='blank-media-before-valid',pages={TAG:VALID.replace('<MediaFiles>','<MediaFiles><MediaFile type="video/mp4"/>')},selected=True),
 dict(name='webm-native-policy',pages={TAG:inline(media='https://fixture.invalid/creative.webm',mime='video/webm')},selected=True),
 dict(name='hls-native-policy',pages={TAG:inline(media='https://fixture.invalid/creative.m3u8',mime='application/x-mpegURL')},selected=True),
 dict(name='no-new-codec-resolution-filter',pages={TAG:inline(attrs='width="3840" height="2160" codec="hvc1"')},selected=True),
 dict(name='vmap-embedded-cdata',pages={TAG:vmap('<vmap:VASTAdData><![CDATA['+VALID.replace('<![CDATA[','').replace(']]>','')+']]></vmap:VASTAdData>')},selected=True),
 dict(name='vmap-midroll-not-preroll',pages={TAG:vmap('<vmap:VASTAdData>'+VALID+'</vmap:VASTAdData>',offset='00:10:00')},selected=False),
 dict(name='no-media-empty',pages={TAG:'<VAST/>'},selected=False),
 dict(name='nonlinear-is-not-video-ad',pages={TAG:VALID.replace('<Linear>','<NonLinearAds>').replace('</Linear>','</NonLinearAds>')},selected=False),
 dict(name='unsupported-only',pages={TAG:inline(mime='application/unsupported')},selected=False),
]
