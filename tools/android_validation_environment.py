#!/usr/bin/env python3
"""Inspect/prepare a real Android AVD, then test install/launch compatibility.

No mocks, ABI substitution, fake cycles or ad pixels. Content cycles require
actual selectable content and are reported NOT RUN by this environment probe.
"""
import argparse
import base64
import gzip
import hashlib
import xml.etree.ElementTree as ET
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time


def tool(name, sdk):
    found = shutil.which(name)
    if found: return found
    for sub in ('platform-tools', 'emulator', 'cmdline-tools/latest/bin'):
        candidate = sdk / sub / name
        if candidate.is_file(): return str(candidate)
    return None


def execute(args, timeout=30, input=None):
    try:
        run = subprocess.run(args, input=input, text=True, capture_output=True, timeout=timeout)
        return {'code': run.returncode, 'output': (run.stdout + run.stderr)[-1600:]}
    except subprocess.TimeoutExpired:
        return {'code': None, 'output': 'timeout'}
    except OSError as exc:
        return {'code': None, 'output': type(exc).__name__}


def inspect(sdk):
    tools = {name: tool(name, sdk) for name in ('adb', 'emulator', 'avdmanager', 'sdkmanager', 'java', 'javac')}
    cpu = Path('/proc/cpuinfo').read_text() if Path('/proc/cpuinfo').exists() else ''
    return {'host': platform.machine(), 'kvm_device': Path('/dev/kvm').exists(),
            'virtualization_flag': any(word in cpu.split() for word in ('vmx', 'svm')),
            'tools': tools, 'android_executed': False,
            'cycles': [{'cycle': i, 'status': 'not-run', 'reason': 'environment-probe-not-content-validation',
                        'vast_requests': None, 'ads_played': None, 'no_fill': None} for i in (1, 2, 3)]}


def prepare(report, sdk, apk):
    tools = report['tools']
    if not all(tools[name] for name in ('sdkmanager', 'avdmanager', 'java')):
        report['status'] = 'sdk-or-jdk-unavailable'
        return
    image = 'system-images;android-30;google_apis;x86_64'
    report['requested_image'] = image
    report['sdk_install'] = execute([tools['sdkmanager'], 'platform-tools', 'emulator', image], timeout=360,
                                    input='y\n' * 100)
    if report['sdk_install']['code'] != 0:
        report['status'] = 'system-image-install-failed'
        return
    tools.update({name: tool(name, sdk) for name in ('adb', 'emulator')})
    if not tools['adb'] or not tools['emulator']:
        report['status'] = 'adb-or-emulator-unavailable'
        return
    avd_home = Path('.cache/android-avd').resolve()
    avd_home.mkdir(parents=True, exist_ok=True)
    os.environ['ANDROID_AVD_HOME'] = str(avd_home)
    report['avd_home_explicit'] = True
    report['avd_create'] = execute([tools['avdmanager'], 'create', 'avd', '--force', '--name', 'SmartedValidation',
                                    '--package', image, '--device', 'pixel_2', '--path', str(avd_home / 'SmartedValidation.avd')], timeout=45, input='no\n')
    if report['avd_create']['code'] != 0:
        report['status'] = 'avd-create-failed'
        return
    log = Path('.cache/android-emulator.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [tools['emulator'], '-avd', 'SmartedValidation', '-no-window', '-no-audio',
               '-no-boot-anim', '-no-snapshot', '-gpu', 'swiftshader_indirect', '-memory', '2048', '-cores', '2']
    if not report['kvm_device']: command += ['-accel', 'off']
    process = None
    try:
        with log.open('w') as stream:
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
            end = time.monotonic() + 240
            booted = False
            while time.monotonic() < end and process.poll() is None:
                result = execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'getprop', 'sys.boot_completed'], timeout=8)
                if result['code'] == 0 and result['output'].strip() == '1':
                    booted = True
                    break
                time.sleep(3)
            if not booted:
                report.update(status='emulator-exited-or-boot-timeout', emulator_exit=process.poll(),
                              emulator_log_tail=log.read_text(errors='replace')[-1600:])
                return
            report['android_executed'] = True
            for prop in ('ro.build.version.release', 'ro.build.version.sdk', 'ro.product.cpu.abilist', 'ro.dalvik.vm.native.bridge'):
                report[prop] = execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'getprop', prop])['output'].strip()
            if not apk or not apk.is_file():
                report['status'] = 'android-booted-no-apk'
                return
            execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'wm', 'size', '540x960'])
            execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'svc', 'power', 'stayon', 'true'])
            execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'settings', 'put', 'system', 'screen_off_timeout', '1800000'])
            execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'input', 'keyevent', 'KEYCODE_WAKEUP'])
            report['install'] = execute([tools['adb'], '-s', 'emulator-5554', 'install', '-r', '-g', str(apk)], timeout=100)
            if report['install']['code'] != 0:
                report['status'] = 'apk-install-failed'
                for row in report['cycles']: row['reason'] = 'apk-install-failed-no-abi-substitution'
                return
            report['apk_sha256'] = hashlib.sha256(apk.read_bytes()).hexdigest()
            report['all_files_permission'] = execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'appops', 'set', '--uid', 'smartedtv.full', 'MANAGE_EXTERNAL_STORAGE', 'allow'])
            report['launch'] = execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'am', 'start', '-W',
                                         '-n', 'smartedtv.full/smartedtv.full.Splash'], timeout=60)
            # The original native permission explainer is shown even with -g.
            # Accept only known media/storage permission controls, never account,
            # license/payment or generic Kodi dialogs.
            report['permission_actions'] = []
            for _ in range(5):
                execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'uiautomator', 'dump', '/sdcard/smarted-permission.xml'])
                raw = subprocess.run([tools['adb'], '-s', 'emulator-5554', 'shell', 'cat', '/sdcard/smarted-permission.xml'], capture_output=True, text=True, timeout=20).stdout
                try:
                    root = ET.fromstring(raw)
                except ET.ParseError:
                    break
                selected = None
                for node in root.iter('node'):
                    label = (node.get('text') or '').lower()
                    package = node.get('package') or ''
                    if ((package == 'smartedtv.full' and label == 'continue' and 'requires access to your device media' in raw)
                        or ('permissioncontroller' in package and label in ('allow', 'allow access to media only', 'while using the app'))):
                        selected = node
                        break
                if selected is None:
                    break
                import re
                numbers = list(map(int, re.findall(r'\d+', selected.get('bounds', ''))))
                if len(numbers) != 4:
                    break
                x, y = (numbers[0]+numbers[2])//2, (numbers[1]+numbers[3])//2
                report['permission_actions'].append(selected.get('text'))
                execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'input', 'tap', str(x), str(y)])
                time.sleep(8)
            time.sleep(120)  # cold native ARM translation + original profile extraction
            evidence = Path('.cache/android-validation')
            evidence.mkdir(parents=True, exist_ok=True)
            if os.environ.get('ANDROID_CONTENT_CYCLES') == 'true':
                from android_content_cycles import run_cycles
                report.update(run_cycles(tools['adb'], evidence, apk))
            for name, args in (
                ('ui.xml', ['shell', 'uiautomator', 'dump', '/sdcard/smarted-ui.xml']),
                ('activities.txt', ['shell', 'dumpsys', 'activity', 'activities']),
                ('logcat.txt', ['logcat', '-d', '-v', 'threadtime']),
            ):
                command = [tools['adb'], '-s', 'emulator-5554'] + args
                run = subprocess.run(command, capture_output=True, timeout=45)
                (evidence / name).write_bytes(run.stdout + run.stderr)
            execute([tools['adb'], '-s', 'emulator-5554', 'pull', '/sdcard/smarted-ui.xml', str(evidence / 'hierarchy.xml')])
            screenshot = subprocess.run([tools['adb'], '-s', 'emulator-5554', 'exec-out', 'screencap', '-p'], capture_output=True, timeout=30)
            (evidence / 'screen.png').write_bytes(screenshot.stdout)
            try:
                from PIL import Image
                import io
                image = Image.open(io.BytesIO(screenshot.stdout)).convert('RGB')
                image.thumbnail((480, 270))
                for quality in (45, 30, 20, 10):
                    compressed = io.BytesIO()
                    image.save(compressed, format='JPEG', quality=quality, optimize=True)
                    if len(compressed.getvalue()) <= 6000:
                        break
                (evidence / 'screen-preview.jpg').write_bytes(compressed.getvalue())
            except Exception:
                pass
            paths = execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'find', '/sdcard/Android/data/smartedtv.full/files', '-name', '*.log'])['output'].splitlines()
            report['kodi_log_paths'] = [path for path in paths if path.endswith(('kodi.log', 'smartedtv.log'))]
            for path in report['kodi_log_paths'][:1]:
                content = subprocess.run([tools['adb'], '-s', 'emulator-5554', 'shell', 'cat', path], capture_output=True, timeout=30).stdout
                (evidence / 'kodi.log').write_bytes(content)
                report['kodi_tail'] = content.decode(errors='replace')[-2500:]
                report['opening_stages'] = [line.split('[SmartAdsOpening] ', 1)[-1] for line in content.decode(errors='replace').splitlines() if '[SmartAdsOpening]' in line]

            report['power'] = execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'dumpsys', 'power'])['output']
            report['app_pid'] = execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'pidof', 'smartedtv.full'])
            report['ui_hierarchy'] = (evidence / 'hierarchy.xml').read_text(errors='replace')[:12000] if (evidence / 'hierarchy.xml').exists() else 'unavailable'
            report['ui_labels'] = [node.get('text') or node.get('content-desc') for node in ET.fromstring(report['ui_hierarchy']).iter('node') if node.get('text') or node.get('content-desc')] if report['ui_hierarchy'] != 'unavailable' else []
            report['activity_tail'] = (evidence / 'activities.txt').read_text(errors='replace')[-2500:]
            if os.environ.get('ANDROID_CONTENT_CYCLES') == 'true':
                report['status'] = 'real-content-cycle-attempts-recorded'
            else:
                report['status'] = 'apk-launch-attempted-content-cycles-not-executed'
                for row in report['cycles']: row['reason'] = 'requires-real-content-selection-and-visual-validation'
    finally:
        if process:
            execute([tools['adb'], '-s', 'emulator-5554', 'emu', 'kill'], timeout=10)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME', '/usr/local/lib/android/sdk')))
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.sdk)
    report['status'] = 'inspection-only'
    if args.prepare: prepare(report, args.sdk, args.apk)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('::notice title=Android environment actual result::' + json.dumps({k: v for k, v in report.items() if k not in ('sdk_install', 'avd_create', 'ui_hierarchy', 'activity_tail', 'kodi_tail', 'opening_stages')}))
    payload = base64.b64encode(gzip.compress(json.dumps(report).encode())).decode()
    parts = [payload[i:i+2500] for i in range(0, len(payload), 2500)]
    for i, part in enumerate(parts):
        print('::notice title=Android result chunks::' + json.dumps(dict(part=i, total=len(parts), data=part)))
    screen = Path('.cache/android-validation/screen-preview.jpg')
    if screen.exists():
        payload = base64.b64encode(screen.read_bytes()).decode()
        parts = [payload[i:i+2500] for i in range(0, len(payload), 2500)]
        for i, part in enumerate(parts):
            print('::notice title=Android screenshot chunks::' + json.dumps(dict(part=i, total=len(parts), data=part)))
    # Log only native lifecycle/errors for remote inspection, not film/tracking URLs.
    log = Path('.cache/android-validation/logcat.txt')
    if log.exists():
        lines = [line for line in log.read_text(errors='replace').splitlines() if any(token in line for token in ('FATAL EXCEPTION', 'Kodi', 'kodi', 'python', 'SmartAds', 'SIGSEGV'))][-25:]
        payload = base64.b64encode(gzip.compress('\n'.join(lines)[-3000:].encode())).decode()
        parts = [payload[i:i+2500] for i in range(0, len(payload), 2500)]
        for i, part in enumerate(parts):
            print('::notice title=Android native log chunks::' + json.dumps(dict(part=i, total=len(parts), data=part)))


if __name__ == '__main__': main()
