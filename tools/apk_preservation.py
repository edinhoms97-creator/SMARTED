#!/usr/bin/env python3
"""Ads-only ZIP patching primitives. No apktool resource/manifest rebuild.

Every non-signature ZIP entry outside an explicit ad-code allowlist must
remain byte-identical to the exact original. This is NOT a UI replacement.
A reviewed plan with original hashes is required before building anything.
"""
import hashlib
from pathlib import PurePosixPath
import re
import zipfile


SIGNATURE = re.compile(r"^META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))$", re.I)
# The existing bootstrap entry point and all UI/resources are immutable.
PROTECTED = {"AndroidManifest.xml", "resources.arsc", "assets/system/addon-manifest.xml",
             "assets/addons/service.smarted.bootstrap/service.py",
             "assets/addons/service.smarted.bootstrap/default.py"}


def check_ad_path(path):
    parts = PurePosixPath(path).parts
    if (path in PROTECTED or not path.startswith("assets/addons/service.smarted.bootstrap/")
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
        if not re.fullmatch(r"[0-9a-f]{64}", entry.get("original_sha256", "")):
            raise ValueError("An original source SHA256 is required for " + path)


def patch(base, output, replacements, plan):
    validate_plan(plan)
    if set(replacements) != set(plan["changes"]):
        raise ValueError("Replacements differ from reviewed plan")
    with zipfile.ZipFile(base) as source:
        for path, entry in plan["changes"].items():
            original = source.read(path)
            if hashlib.sha256(original).hexdigest() != entry["original_sha256"]:
                raise ValueError("Original ad source hash mismatch: " + path)
        # Only existing ad modules can be replaced. No new startup service,
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
    return compare(base, output, set(replacements))
