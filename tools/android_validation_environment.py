#!/usr/bin/env python3
"""Inspect/prepare a real Android AVD, then test install/launch compatibility.

No mocks, ABI substitution, fake cycles or ad pixels. Content cycles require
actual selectable content and are reported NOT RUN by this environment probe.
"""
import argparse
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
    report['avd_create'] = execute([tools['avdmanager'], 'create', 'avd', '--force', '--name', 'SmartedValidation',
                                    '--package', image, '--device', 'pixel_2'], timeout=45, input='no\n')
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
            report['install'] = execute([tools['adb'], '-s', 'emulator-5554', 'install', '-r', str(apk)], timeout=100)
            if report['install']['code'] != 0:
                report['status'] = 'apk-install-failed'
                for row in report['cycles']: row['reason'] = 'apk-install-failed-no-abi-substitution'
                return
            report['launch'] = execute([tools['adb'], '-s', 'emulator-5554', 'shell', 'am', 'start', '-W',
                                         '-n', 'smartedtv.full/smartedtv.full.Splash'], timeout=60)
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
    print('::notice title=Android environment actual result::' + json.dumps(report))


if __name__ == '__main__': main()
