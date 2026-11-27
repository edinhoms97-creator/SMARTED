#!/usr/bin/env python3
"""Ads-only ZIP patching primitives. No apktool resource/manifest rebuild.

Every non-signature ZIP entry outside an explicit ad/link-code allowlist must
remain byte-identical to the exact original. This is NOT a UI replacement.
A reviewed plan with original hashes is required before building anything.
"""
import hashlib
from pathlib import PurePosixPath
import re
import zipfile


SIGNATURE = re.compile(r"^META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))$", re.I)
# The existing bootstrap entry point and all UI/resources are immutable.
# The reviewed plan additionally permits only APK-link actions in vip.py;
# patch_original_ads enforces unchanged AST for license/payment functions.
PROTECTED = {"AndroidManifest.xml", "resources.arsc", "assets/system/addon-manifest.xml",
             "assets/addons/service.smarted.bootstrap/service.py",
             "assets/addons/service.smarted.bootstrap/default.py"}


WELCOME_LINK_CONSTANTS = 'assets/addons/script.smartedtv.welcome/default.py'

def check_ad_path(path):
    parts = PurePosixPath(path).parts
    if (path in PROTECTED or not (path.startswith("assets/addons/service.smarted.bootstrap/") or path == WELCOME_LINK_CONSTANTS)
            or ".." in parts or "\\" in path
            or any(part.startswith("skin.") or part.lower() in {"skins", "media", "resources"} for part in parts)
            or PurePosixPath(path).suffix not in {".py", ".json"}):
        raise ValueError("Protected/non-ad path cannot be patched: " + path)


def inventory(archive):
    result = {}
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("Duplicate ZIP entries")
    for name in names:
        if SIGNATURE.fullmatch(name):
            continue
        digest = hashlib.sha256()
        with archive.open(name) as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        result[name] = digest.hexdigest()
    return result


def compare(base, result, allowed):
    for path in allowed:
        check_ad_path(path)
    with zipfile.ZipFile(base) as source, zipfile.ZipFile(result) as patched:
        before, after = inventory(source), inventory(patched)
    changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    forbidden = sorted(set(changed) - set(allowed))
    if forbidden:
        raise ValueError("Original APK changed outside ad allowlist: " + ", ".join(forbidden[:20]))
    return {"changed": changed, "preserved_entries": len(set(before) - set(changed)),
            "skin_manifest_resources_startup_unchanged": True}


def validate_plan(plan):
    if plan.get("reviewed") is not True or not plan.get("changes"):
        raise ValueError("No reviewed ads-only patch plan: build/publication blocked")
    for path, entry in plan["changes"].items():
        check_ad_path(path)
        if entry.get("new_file") is True:
            if path not in ('assets/addons/service.smarted.bootstrap/ads_admob.py', 'assets/addons/service.smarted.bootstrap/ads_resume.py', 'assets/addons/service.smarted.bootstrap/ads_tracking.py', 'assets/addons/service.smarted.bootstrap/ads_diagnostics.py') or entry.get('original_sha256') is not None:
                raise ValueError('Only reviewed AdMob config or ad resume/tracking/diagnostics modules may be added')
        elif not re.fullmatch(r"[0-9a-f]{64}", entry.get("original_sha256", "")):
            raise ValueError("An original source SHA256 is required for " + path)


def patch(base, output, replacements, plan):
    validate_plan(plan)
    if set(replacements) != set(plan["changes"]):
        raise ValueError("Replacements differ from reviewed plan")
    with zipfile.ZipFile(base) as source:
        for path, entry in plan["changes"].items():
            if entry.get('new_file'):
                if path in source.namelist():
                    raise ValueError('Expected new config module already exists: ' + path)
                continue
            original = source.read(path)
            if hashlib.sha256(original).hexdigest() != entry["original_sha256"]:
                raise ValueError("Original ad source hash mismatch: " + path)
        # Only the inert ad config may be added. No new startup service,
        # skin, welcome screen, launcher or activation workflow is injected.
        with zipfile.ZipFile(output, "w") as target:
            target.comment = source.comment
            for info in source.infolist():
                if SIGNATURE.fullmatch(info.filename):
                    continue
                data = replacements.get(info.filename)
                if data is None:
                    data = source.read(info.filename)
                target.writestr(info, data)
            for path, entry in plan['changes'].items():
                if entry.get('new_file'):
                    target.writestr(path, replacements[path], compress_type=zipfile.ZIP_DEFLATED)
    return compare(base, output, set(replacements))


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('result', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((Path(__file__).resolve().parent.parent / 'android-build/ads-only-plan.json').read_text())
    validate_plan(plan)
    try:
        report = compare(args.base, args.result, set(plan['changes']))
        if set(report['changed']) != set(plan['changes']):
            raise ValueError('Final APK must contain exactly the reviewed ad changes')
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print('::notice title=Original APK preservation::' + json.dumps(report))
    except Exception as exc:
        safe = str(exc).replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D')
        print('::error title=Original APK preservation::' + safe, flush=True)
        raise
