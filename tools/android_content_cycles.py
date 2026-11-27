#!/usr/bin/env python3
"""Real ADB/Kodi cycles with public media samples, never mock ads or pixels.

No app/ABI/license/profile patch. Uses the original free-with-ads welcome
button and Android's existing VIEW intent. Three root opportunities maximum;
if the first content cannot be opened/observed, report the blocker, not success.
"""
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.request import Request, urlopen

SAMPLES = ('big_buck_bunny.mp4', 'echo-hereweare.mp4')


def run_cycles(adb, evidence, apk=None):
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    def command(*args, timeout=30):
        try:
            result = subprocess.run([adb, '-s', 'emulator-5554', *args], capture_output=True, timeout=timeout)
            return result.returncode, (result.stdout + result.stderr).decode(errors='replace')
        except subprocess.TimeoutExpired:
            return None, 'timeout'
    def stages():
        _, logs = command('logcat', '-d', '-v', 'brief')
        parsed = []
        for line in logs.splitlines():
            if '[SmartAdsOpening] ' not in line:
                continue
            try:
                parsed.append(json.loads(line.split('[SmartAdsOpening] ', 1)[1]))
            except (ValueError, TypeError):
                pass
        return parsed
    rows = [dict(cycle=i, content=label, status='not-run', reason='earlier-cycle-not-executed',
                 vast_requests=None, ads_played=None, no_fill=None)
            for i, label in enumerate(('Big Buck Bunny public sample', 'same Big Buck Bunny sample reopened',
                                       'Echo Here We Are different public sample'), 1)]
    result = {'cycles': rows, 'cycle_method': 'real-Android-VIEW-public-samples-not-catalog-movies',
              'sample_repository': 'https://github.com/mediaelement/mediaelement-files',
              'sample_downloads': [], 'cycle_blocker': None}
    try:
        if apk:
            import zipfile
            import xml.etree.ElementTree as ET
            controls = []
            with zipfile.ZipFile(apk) as archive:
                for name in archive.namelist():
                    if not (name.startswith('assets/addons/script.smartedtv.welcome/') and name.endswith('.xml')):
                        continue
                    try:
                        root = ET.fromstring(archive.read(name))
                    except ET.ParseError:
                        continue
                    for node in root.iter('control'):
                        if node.get('id') in ('312', '905', '906'):
                            controls.append(dict(file=name, id=node.get('id'), type=node.get('type'),
                                                 values={child.tag: child.text for child in node if child.tag in ('label', 'left', 'top', 'posx', 'posy', 'width', 'height', 'onleft', 'onright')}))
            result['welcome_control_layout'] = controls
        # Cold ARM translation can finish startup AFTER the initial wait. Wait
        # for a real bootstrap milestone AND the original two QR cards before
        # tapping; a successful ADB tap alone never proves the welcome was ready.
        import io
        from PIL import Image
        ready = False
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            _, startup = command('logcat', '-d', '-v', 'brief')
            if 'sem pop-up de abertura em video na Home' in startup:
                frame = subprocess.run([adb, '-s', 'emulator-5554', 'exec-out', 'screencap', '-p'], capture_output=True, timeout=20)
                image = Image.open(io.BytesIO(frame.stdout)).convert('L')
                w, h = image.size
                fractions = []
                for left, top, right, bottom in ((.43, .32, .56, .58), (.75, .31, .90, .57)):
                    crop = image.crop((int(left*w), int(top*h), int(right*w), int(bottom*h)))
                    hist = crop.histogram()
                    fractions.append(sum(hist[180:]) / (crop.width*crop.height))
                if all(value > .12 for value in fractions):
                    ready = True
                    break
            time.sleep(2)
        result['welcome_ready_observed'] = ready
        if not ready:
            result['cycle_blocker'] = 'original-welcome-not-ready-for-free-choice'
            return result
        # Original welcome control 312, "Assistir com anuncios", left card.
        # Fixed AVD resolution 960x540; never tap QR/VIP/payment/activation controls.
        result['welcome_free_tap'] = command('shell', 'input', 'tap', '148', '420')[0]
        time.sleep(8)
        _, welcome_log = command('logcat', '-d', '-v', 'brief')
        if 'Botao 312 (Assistir com anuncios) acionado.' not in welcome_log:
            result['cycle_blocker'] = 'original-free-welcome-button-not-confirmed'
            return result
        # Original onClick(312) opens the ads notice and explicitly focuses 905
        # (Back); its adjacent control 906 is Continue with ads. Confirm through
        # native DPAD, never license/profile settings or a Python eval shortcut.
        command('shell', 'input', 'keyevent', 'KEYCODE_DPAD_RIGHT')
        command('shell', 'input', 'keyevent', 'KEYCODE_DPAD_CENTER')
        time.sleep(3)
        _, welcome_log = command('logcat', '-d', '-v', 'brief')
        result['welcome_continue_906_observed'] = 'control_id=906' in welcome_log
        if not result['welcome_continue_906_observed']:
            result['cycle_blocker'] = 'original-continue-with-ads-not-confirmed'
            return result
        command('shell', 'mkdir', '-p', '/sdcard/Movies/SmartedValidation')
        for name in SAMPLES:
            url = 'https://api.github.com/repos/mediaelement/mediaelement-files/contents/' + name
            request = Request(url, headers={'Accept': 'application/vnd.github.raw+json', 'User-Agent': 'SMARTED-Android-validation'})
            with urlopen(request, timeout=40) as response:
                data = response.read(10 * 1024 * 1024)
            if b'ftyp' not in data[:40]:
                raise ValueError('sample-is-not-MP4')
            local = evidence / name
            local.write_bytes(data)
            code, output = command('push', str(local), '/sdcard/Movies/SmartedValidation/' + name, timeout=45)
            result['sample_downloads'].append(dict(name=name, bytes=len(data), adb_push=code))
            if code != 0:
                raise RuntimeError('sample-push-failed')
        files = (SAMPLES[0], SAMPLES[0], SAMPLES[1])
        for row, name in zip(rows, files):
            command('shell', 'input', 'keyevent', 'KEYCODE_MEDIA_STOP')
            time.sleep(1)
            previous = {entry.get('opening') for entry in stages() if entry.get('stage') == 'opening-claimed'}
            code, output = command('shell', 'am', 'start', '-W', '-a', 'android.intent.action.VIEW',
                                   '-d', 'file:///sdcard/Movies/SmartedValidation/' + name,
                                   '-t', 'video/mp4', '-p', 'smartedtv.full', timeout=45)
            row['intent'] = dict(code=code, output=output[-1200:])
            if code != 0 or 'Error:' in output or 'unable to resolve' in output:
                row.update(status='blocked', reason='original-app-VIEW-intent-not-resolved')
                result['cycle_blocker'] = row['reason']
                break
            deadline = time.monotonic() + 85
            selected = []
            while time.monotonic() < deadline:
                all_stages = stages()
                new = {entry.get('opening') for entry in all_stages
                       if entry.get('stage') == 'opening-claimed'} - previous
                selected = [entry for entry in all_stages if entry.get('opening') in new]
                if any(entry.get('stage') == 'cycle-finished' for entry in selected):
                    break
                time.sleep(1)
            if not selected:
                row.update(status='blocked', reason='no-native-opening-observed-after-VIEW')
                result['cycle_blocker'] = row['reason']
                break
            if any(entry.get('stage') == 'cycle-finished' for entry in selected):
                # Native pause/resume of content, not new intent or ad requests.
                command('shell', 'input', 'keyevent', 'KEYCODE_MEDIA_PLAY_PAUSE')
                time.sleep(.5)
                command('shell', 'input', 'keyevent', 'KEYCODE_MEDIA_PLAY_PAUSE')
                time.sleep(1)
                selected = [entry for entry in stages() if entry.get('opening') in new]
            counts = lambda stage: sum(entry.get('stage') == stage for entry in selected)
            requests = sum(entry.get('stage') == 'vast-request' and entry.get('hop') == 1 for entry in selected)
            reasons = [entry.get('reason') for entry in selected if entry.get('stage') == 'vast-result']
            finished = [entry for entry in selected if entry.get('stage') == 'cycle-finished']
            nofill = sum(reason in ('no-fill', 'no-fill-ou-sem-midia') for reason in reasons)
            code, media = command('shell', 'dumpsys', 'media_session')
            (evidence / ('cycle-%s-media-session.txt' % row['cycle'])).write_text(media)
            media_states = re.findall(r'PlaybackState\s*\{[^}]+\}', media)
            row.update(status='observed' if finished else 'timeout', reason=reasons or None,
                       opening_ids=sorted(new), vast_requests=requests,
                       wrapper_requests=counts('vast-request')-requests,
                       creative_selected=counts('creative-selected'), ads_played=counts('ad-start-observed'),
                       impression_signals_queued=counts('impression-queued'),
                       impression_pixels_queued=sum(entry.get('pixels', 0) for entry in selected if entry.get('stage') == 'impression-queued'),
                       ad_exit_reasons=[entry.get('reason') for entry in selected if entry.get('stage') == 'ad-player-released'],
                       complete_queued=sum(entry.get('stage') == 'tracking-event-queued' and entry.get('event') == 'complete' for entry in selected),
                       no_fill=nofill, content_resume_confirmed=counts('content-released') > 0,
                       ad_and_resume_confirmed=bool(finished and finished[-1].get('ad_and_resume_confirmed')),
                       tracking_http_statuses=[entry.get('status') for entry in selected if entry.get('stage') == 'tracking-http-response'],
                       tracking_http_failures=counts('tracking-http-failure'),
                       media_session_package_seen='smartedtv.full' in media,
                       media_session_states=media_states[:4])
            (evidence / ('cycle-%s-stages.json' % row['cycle'])).write_text(json.dumps(selected, indent=2))
            frame = subprocess.run([adb, '-s', 'emulator-5554', 'exec-out', 'screencap', '-p'], capture_output=True, timeout=20)
            (evidence / ('cycle-%s.png' % row['cycle'])).write_bytes(frame.stdout)
            if requests != 1 or not finished:
                result['cycle_blocker'] = 'opening-or-request-count-not-as-expected'
                break
    except Exception as exc:
        result['cycle_blocker'] = type(exc).__name__ + ': ' + str(exc)[:180]
    finally:
        command('shell', 'input', 'keyevent', 'KEYCODE_MEDIA_STOP')
        # Input samples are environment-only; do not upload or commit video data.
        for name in SAMPLES:
            (evidence / name).unlink(missing_ok=True)
    return result
