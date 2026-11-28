#!/usr/bin/env python3
"""Two bounded comparative delivery probes; never fires impression/tracking.

Reads the exact original tag from the pinned APK. Decodes selected video with
FFmpeg if available: CPU decode is NOT Kodi/Android display/audio validation.
No retries. No tag query strings, media URLs, raw XML or network tokens logged.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, parse_qs
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

from apk_pipeline import verify_base
from patch_minimal_clickadilla import TAG, BASE, FOLDER
from test_original_ad_patch import load_functions

UA = 'Mozilla/5.0 (Linux; Android 11; Android TV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


def original_tag(source):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VAST_TAG_PADRAO' for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and urlsplit(value).scheme in ('https', 'http'):
                return value
    raise ValueError('Original VAST tag is not a literal HTTP(S) URL')


def ffmpeg_executable():
    found = shutil.which('ffmpeg')
    if not found:
        try:
            import imageio_ffmpeg
            found = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            pass
    return found


def decode_media(url, declared):
    executable = ffmpeg_executable()
    if not executable:
        return {'status': 'decoder-unavailable', 'android_validated': False}
    if urlsplit(url).scheme not in ('http', 'https'):
        return {'status': 'unsupported-media-scheme', 'android_validated': False}
    # Bound both network reads and wall time; no persistent media downloads.
    command = [executable, '-nostdin', '-hide_banner', '-nostats', '-loglevel', 'info',
               '-xerror', '-protocol_whitelist', 'http,https,tcp,tls,crypto',
               '-rw_timeout', '12000000', '-user_agent', UA, '-i', url,
               '-map', '0:v:0', '-map', '0:a:0?', '-t', '60', '-progress', 'pipe:1',
               '-f', 'null', '-']
    try:
        process = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=90)
    except subprocess.TimeoutExpired:
        return {'status': 'decode-wall-timeout', 'android_validated': False}
    except OSError as exc:
        return {'status': type(exc).__name__, 'android_validated': False}
    progress = dict(re.findall(r'^([a-z_]+)=(.*)$', process.stdout, re.M))
    try:
        frames = int(progress.get('frame', '0').strip() or 0)
        seconds = max(0, int(progress.get('out_time_us', '0') or 0)) / 1000000
    except ValueError:
        return {'status': 'decode-progress-unavailable', 'android_validated': False}
    # FFmpeg reports duration from the actual input, independently of VAST.
    match = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', process.stderr)
    measured = (3600 * int(match[1]) + 60 * int(match[2]) + float(match[3])) if match else None
    expected = measured or declared
    full = bool(process.returncode == 0 and frames > 0 and progress.get('progress') == 'end'
                and expected and expected < 59.5 and seconds >= expected - .25)
    return {'status': 'cpu-decoded-to-end' if full else 'decode-incomplete-or-failed',
            'returncode': process.returncode, 'frames': frames, 'decoded_seconds': round(seconds, 3),
            'container_duration': measured, 'vast_duration': declared,
            'audio_stream_present': 'Audio:' in process.stderr, 'android_validated': False}


def probe(label, tag, parser):
    sys.path.insert(0, str(FOLDER))
    from ads_tracking import expand
    result = {'source': label, 'tag_host': urlsplit(tag).hostname,
              'tag_scheme': urlsplit(tag).scheme,
              'tag_fingerprint': hashlib.sha256(tag.encode()).hexdigest(),
              'parameter_names': sorted(parse_qs(urlsplit(tag).query, keep_blank_values=True)),
              'requests': [], 'tracking_fired': False, 'android_validated': False}
    current, visited = tag, set()
    for depth in range(6):
        current = expand(current, user_agent=UA)
        if current in visited:
            result['status'] = 'wrapper-cycle'
            return result
        visited.add(current)
        request_info = {'depth': depth, 'host': urlsplit(current).hostname}
        result['requests'].append(request_info)
        if urlsplit(current).scheme not in ('http', 'https'):
            result['status'] = 'unsupported-tag-scheme'
            return result
        try:
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            request = Request(current, headers={'User-Agent': UA, 'Accept': 'application/xml, text/xml, */*'})
            with urlopen(request, context=context, timeout=12) as response:
                request_info.update(http_status=response.status, final_host=urlsplit(response.url).hostname)
                data = response.read(2 * 1024 * 1024 + 1)
        except HTTPError as exc:
            request_info.update(http_status=exc.code, error_type='HTTPError')
            result['status'] = 'tag-http-error'
            return result
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            request_info.update(error_type=type(exc).__name__,
                                cause_type=type(getattr(exc, 'reason', None)).__name__)
            result['status'] = 'tag-network-error'
            return result
        request_info['bytes'] = len(data)
        if len(data) > 2 * 1024 * 1024:
            result['status'] = 'xml-too-large'
            return result
        if not data.strip():
            result['status'] = 'empty-or-no-fill'
            return result
        try:
            root = ET.fromstring(data)
            for node in root.iter():
                node.tag = node.tag.rsplit('}', 1)[-1]
            normalized = ET.tostring(root, encoding='unicode')
        except ET.ParseError:
            result['status'] = 'not-vast-xml'
            return result
        request_info.update(root=root.tag, ads=len(list(root.iter('Ad'))),
                            wrappers=len(list(root.iter('Wrapper'))),
                            inlines=len(list(root.iter('InLine'))),
                            media_files=len(list(root.iter('MediaFile'))))
        try:
            ad = parser['escolher_anuncio'](normalized, 720)
        except Exception as exc:
            result.update(status='base-parser-error', parser_error=type(exc).__name__)
            return result
        if ad:
            media_url = urljoin(current, ad['url'])
            result.update(status='creative-selected', media_host=urlsplit(media_url).hostname,
                          media_type=ad.get('tipo'), vast_duration=ad.get('duracao'),
                          inline_impression_nodes=len(ad.get('impressao') or []))
            result['decode'] = decode_media(media_url, ad.get('duracao'))
            return result
        target = parser['tag_do_wrapper'](normalized) or parser['tag_do_vmap'](normalized)
        if not target:
            result['status'] = 'media-rejected-by-base-selector' if request_info['media_files'] else 'no-linear-creative'
            result['media_types'] = sorted({node.get('type', '') for node in root.iter('MediaFile')})
            return result
        current = urljoin(current, target)
    result['status'] = 'wrapper-depth-limit'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    verify_base(args.base)
    with zipfile.ZipFile(args.base) as archive:
        source = archive.read(BASE + 'ads_vast.py').decode()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'ads_vast.py'
        path.write_text(source)
        env = load_functions(path)
        # Exactly two source attempts. Wrapper hops and video decode belong to
        # their source attempt. Never retry an empty response to farm fill.
        results = []
        for label, tag in (('original-apk-source', original_tag(source)), ('clickadilla-1508180', TAG)):
            try:
                results.append(probe(label, tag, env))
            except Exception as exc:
                results.append({'source': label, 'status': 'probe-exception',
                                'error_type': type(exc).__name__, 'tracking_fired': False,
                                'android_validated': False})
    report = {'attempts': results, 'attempt_count': 2, 'tracking_fired': False,
              'note': 'Network/CPU decode only. No Kodi/Android display or physical audio test.'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    for index, item in enumerate(results, start=2):
        print('::notice title=Ad delivery probe %d::' % index + json.dumps(item))


if __name__ == '__main__':
    main()
