#!/usr/bin/env python3
"""Fail-closed repackaging helpers. Standard library only; no fake APK fallback.

The base supplies ALL native Android/Kodi code. Never rename a single-ABI
APK to 'universal', combine unrelated Kodi builds or replace the player
with a WebView. A successful build must retain every native/Dex byte.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import struct
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "android-build/base-apk.json").read_text())
ANDROID = "{http://schemas.android.com/apk/res/android}"
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
ABIS = {"armeabi-v7a": (1, 40), "arm64-v8a": (2, 183),
        "x86": (1, 3), "x86_64": (2, 62)}
ADDONS = ("script.smartedtv.welcome", "service.smartedtv.startup", "skin.estilo.personalizado")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def hashes(path):
    """Dropbox = SHA256(concatenated SHA256(4 MiB blocks)), NOT file SHA256."""
    file_hash, dropbox = hashlib.sha256(), hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            file_hash.update(block)
            dropbox.update(hashlib.sha256(block).digest())
    return {"sha256": file_hash.hexdigest(), "dropbox_content_hash": dropbox.hexdigest()}


def verify_base(path, override_sha=""):
    digests = hashes(path)
    if override_sha:
        require(bool(re.fullmatch(r"[0-9a-fA-F]{64}", override_sha)), "Expected SHA256 must be 64 hex characters")
        require(digests["sha256"] == override_sha.lower(), "Custom base SHA256 mismatch")
    else:
        require(Path(path).stat().st_size == CONFIG["size"], "Dropbox base size changed; review/pin a new base")
        require(digests["dropbox_content_hash"] == CONFIG["dropbox_content_hash"], "Dropbox base content hash mismatch")
    return digests


def download_base(destination):
    override_url = os.environ.get("INPUT_BASE_URL", "").strip()
    override_sha = os.environ.get("INPUT_BASE_SHA256", "").strip()
    require(bool(override_url) == bool(override_sha), "Custom base_url and base_sha256 must be supplied together")
    url = override_url or CONFIG["url"]
    require(url.startswith("https://"), "Only HTTPS base downloads are accepted")
    destination = Path(destination)
    if destination.exists():
        verify_base(destination, override_sha)
        print("Cached base hash verified")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".part")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    request = urllib.request.Request(url, headers={"User-Agent": "SMARTEDTV-test-build/1.0"})
    deadline = time.monotonic() + 180
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response, partial.open("wb") as output:
            require(response.url.startswith("https://"), "Refusing a non-HTTPS download redirect")
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                require(size <= 1024 ** 3, "Base exceeds 1 GiB download limit")
                require(time.monotonic() <= deadline, "Base download exceeded 180 seconds")
                output.write(block)
        verify_base(partial, override_sha)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def inspect_apk(path):
    """CRC, duplicate/path safety, native ELF architecture, Dex/lib inventory."""
    result = {"size": Path(path).stat().st_size, **hashes(path), "abis": {}, "code_hashes": {}}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "APK has duplicate ZIP entries")
        require("AndroidManifest.xml" in names and "classes.dex" in names, "Not a complete Android APK")
        require(not any(name.startswith("/") or ".." in name.split("/") or "\\" in name for name in names), "Unsafe APK ZIP paths")
        require(sum(item.file_size for item in archive.infolist()) <= 4 * 1024 ** 3, "APK expands above the 4 GiB safety limit")
        require(archive.testzip() is None, "APK failed ZIP/CRC verification")
        for name in names:
            if re.fullmatch(r"classes\d*\.dex", name) or re.fullmatch(r"lib/[^/]+/[^/]+\.so", name):
                with archive.open(name) as stream:
                    header = stream.read(20)
                    digest = hashlib.sha256(header)
                    while block := stream.read(1024 * 1024):
                        digest.update(block)
                result["code_hashes"][name] = digest.hexdigest()
                if name.startswith("lib/"):
                    _, abi, library = name.split("/")
                    require(abi in ABIS, "Unknown native ABI: " + abi)
                    require(len(header) == 20 and header[:4] == b"\x7fELF" and header[5] == 1,
                            "Invalid/little-endian ELF missing: " + name)
                    require((header[4], struct.unpack_from("<H", header, 18)[0]) == ABIS[abi],
                            "ELF architecture does not match ABI directory: " + name)
                    result["abis"].setdefault(abi, []).append(library)
        for libraries in result["abis"].values():
            libraries.sort()
    return result


def require_universal(inventory):
    abis = inventory["abis"]
    require(all(abi in abis for abi in CONFIG["required_abis"]),
            "Base is NOT ARM-universal. Required: armeabi-v7a + arm64-v8a; found: "
            + ", ".join(sorted(abis)) + ". Supply a genuine multi-ABI base/native source; renaming is not a conversion.")
    for abi in CONFIG["required_abis"]:
        require(set(abis[abi]).intersection({"libkodi.so", "libxbmc.so"}),
                "Missing Kodi native core for " + abi + "; found: " + ", ".join(abis[abi]))
    # Optional per-ABI addons may differ. Their actual DT_NEEDED resolution
    # is checked after decode, before building/signing, not by list equality.


def launcher(root):
    app = root.find("application")
    require(app is not None, "Missing Android application")
    matches = []
    for activity in list(app.findall("activity")) + list(app.findall("activity-alias")):
        for intent in activity.findall("intent-filter"):
            actions = {el.get(ANDROID + "name") for el in intent.findall("action")}
            categories = {el.get(ANDROID + "name") for el in intent.findall("category")}
            if "android.intent.action.MAIN" in actions and "android.intent.category.LAUNCHER" in categories:
                matches.append((activity, intent))
    require(len(matches) == 1, "Expected one MAIN/LAUNCHER route; cannot safely unify ambiguous entry points")
    return app, *matches[0]


def patch_manifest(path):
    tree = ET.parse(path)
    root = tree.getroot()
    app, activity, intent = launcher(root)
    require(root.get(ANDROID + "sharedUserId") is None, "Shared UID cannot safely use an unrelated debug certificate")
    uses_sdk = root.find("uses-sdk")
    require(uses_sdk is not None, "Missing SDK declarations")
    require(int(uses_sdk.get(ANDROID + "targetSdkVersion", "0")) >= 23,
            "Base targets an obsolete SDK blocked by recent Android installers")
    app.attrib.pop(ANDROID + "testOnly", None)  # allow normal sideload (no adb -t)
    app.set(ANDROID + "debuggable", "false")
    app.set(ANDROID + "banner", "@drawable/smartedtv_test_banner")
    activity.set(ANDROID + "exported", "true")
    tv_category = "android.intent.category.LEANBACK_LAUNCHER"
    # Remove divergent TV entry points; every device must reach the SAME
    # existing Android/Kodi Activity, not a separate ad/player path.
    for component in list(app.findall("activity")) + list(app.findall("activity-alias")):
        for other_intent in component.findall("intent-filter"):
            if other_intent is intent:
                continue
            for category in list(other_intent.findall("category")):
                if category.get(ANDROID + "name") == tv_category:
                    other_intent.remove(category)
    if not any(el.get(ANDROID + "name") == tv_category for el in intent.findall("category")):
        ET.SubElement(intent, "category", {ANDROID + "name": tv_category})
    optional_features = ("android.hardware.touchscreen", "android.hardware.faketouch",
                         "android.software.leanback", "android.hardware.type.television")
    for name in optional_features:
        feature = next((el for el in root.findall("uses-feature") if el.get(ANDROID + "name") == name), None)
        if feature is None:
            feature = ET.SubElement(root, "uses-feature", {ANDROID + "name": name})
        feature.set(ANDROID + "required", "false")
    if not any(el.get(ANDROID + "name") == "android.permission.INTERNET" for el in root.findall("uses-permission")):
        ET.SubElement(root, "uses-permission", {ANDROID + "name": "android.permission.INTERNET"})
    tree.write(path, encoding="utf-8", xml_declaration=True)


def validate_manifest(path):
    root = ET.parse(path).getroot()
    app, activity, intent = launcher(root)
    require(activity.get(ANDROID + "exported") == "true", "Launcher must be exported")
    require(any(el.get(ANDROID + "name") == "android.intent.category.LEANBACK_LAUNCHER" for el in intent.findall("category")),
            "Mobile and TV must share the same MAIN entry point")
    require(app.get(ANDROID + "testOnly") != "true", "testOnly blocks ordinary installation")
    require(app.get(ANDROID + "banner"), "TV launcher banner missing")
    tv_routes = [el for component in list(app.findall("activity")) + list(app.findall("activity-alias"))
                 for el in component.findall("intent-filter")
                 if any(cat.get(ANDROID + "name") == "android.intent.category.LEANBACK_LAUNCHER" for cat in el.findall("category"))]
    require(len(tv_routes) == 1, "Divergent/duplicate TV launch routes")
    for name in ("android.hardware.touchscreen", "android.hardware.faketouch", "android.software.leanback", "android.hardware.type.television"):
        features = [el for el in root.findall("uses-feature") if el.get(ANDROID + "name") == name]
        require(features and all(el.get(ANDROID + "required") == "false" for el in features), "Required device feature blocks installation: " + name)
    require(any(el.get(ANDROID + "name") == "android.permission.INTERNET" for el in root.findall("uses-permission")), "Missing Internet permission")
    return {"package": root.get("package"), "launcher": activity.get(ANDROID + "name"),
            "sdk": {key.removeprefix(ANDROID): value for key, value in root.find("uses-sdk").attrib.items()}}


def prepare(decoded, revision, source_manifest=None):
    decoded = Path(decoded)
    assets = decoded / "assets"
    addon_manifest = assets / "system/addon-manifest.xml"
    require((assets / "addons/xbmc.python/addon.xml").exists(), "Base lacks the expected Kodi Python addon layout")
    require(addon_manifest.exists(), "Base lacks Kodi's system/addon-manifest.xml; manual integration required")
    require(re.fullmatch(r"[0-9a-f]{40}", revision), "Build revision must be a full Git commit SHA")
    config_text = (ROOT / "smartedtv/js/config.js").read_text()
    require(re.search(r"admob:\s*\{\s*enabled:\s*false", config_text), "AdMob must remain disabled")
    require("https://vast.yomeno.xyz/vast?spot_id=1508180" in config_text, "Expected VAST tag missing")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    for addon in ADDONS:
        source = ROOT / ("skin" if addon.startswith("skin.") else "kodi-addon") / addon
        require(source.is_dir(), "Source addon missing: " + addon)
        target = assets / "addons" / addon
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=ignore)
    web = assets / "smartedtv"
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(ROOT / "smartedtv", web, ignore=ignore)
    tree = ET.parse(addon_manifest)
    require(tree.getroot().tag == "addons", "Unexpected Kodi addon manifest root")
    for addon in ADDONS:
        existing = next((el for el in tree.getroot() if (el.text or "").strip() == addon), None)
        if existing is None:
            existing = ET.SubElement(tree.getroot(), "addon")
            existing.text = addon
        existing.attrib.pop("optional", None)  # enabled system addon, not inert ZIP data
    tree.write(addon_manifest, encoding="utf-8", xml_declaration=True)
    if source_manifest:
        # Apktool may move <uses-sdk> out of XML into apktool.yml. Restore
        # its original declarations before patching; do not invent SDKs.
        manifest = decoded / "AndroidManifest.xml"
        decoded_tree = ET.parse(manifest)
        original_root = ET.parse(source_manifest).getroot()
        require(decoded_tree.getroot().get("package") == original_root.get("package"), "Decoded package differs from base")
        if decoded_tree.getroot().find("uses-sdk") is None:
            sdk = original_root.find("uses-sdk")
            require(sdk is not None, "Original APK lacks SDK declarations")
            decoded_tree.getroot().insert(0, sdk)
            decoded_tree.write(manifest, encoding="utf-8", xml_declaration=True)
    patch_manifest(decoded / "AndroidManifest.xml")
    drawable = decoded / "res/drawable/smartedtv_test_banner.xml"
    drawable.parent.mkdir(parents=True, exist_ok=True)
    drawable.write_text('''<vector xmlns:android="http://schemas.android.com/apk/res/android"
 android:width="320dp" android:height="180dp" android:viewportWidth="320" android:viewportHeight="180">
 <path android:fillColor="#101318" android:pathData="M0,0h320v180h-320z"/>
 <path android:fillColor="#FFFFFF" android:pathData="M136,54L196,90L136,126z"/>
</vector>\n''')
    build_info = {"revision": revision, "admob_enabled": False, "vast_spot": 1508180,
                  "mode": "debug-signed-kodi-repackage", "device_route": "single-android-kodi-launcher"}
    write_json(assets / "smartedtv-build.json", build_info)
    return {**build_info, "manifest": validate_manifest(decoded / "AndroidManifest.xml")}


def verify_content(apk, base_inventory, revision):
    final = inspect_apk(apk)
    require_universal(final)
    require(final["code_hashes"] == base_inventory["code_hashes"], "Native/Dex bytes changed during repackaging")
    with zipfile.ZipFile(apk) as archive:
        info = json.loads(archive.read("assets/smartedtv-build.json"))
        require(info["revision"] == revision, "Wrong source revision packaged")
        require(info["admob_enabled"] is False and info["vast_spot"] == 1508180, "Incorrect ads configuration")
        for source_dir, target_dir in (("smartedtv", "assets/smartedtv"),
                                       ("kodi-addon/script.smartedtv.welcome", "assets/addons/script.smartedtv.welcome"),
                                       ("kodi-addon/service.smartedtv.startup", "assets/addons/service.smartedtv.startup"),
                                       ("skin/skin.estilo.personalizado", "assets/addons/skin.estilo.personalizado")):
            for file in (ROOT / source_dir).rglob("*"):
                if not file.is_file() or "__pycache__" in file.parts or file.suffix == ".pyc" or file.name == ".DS_Store":
                    continue
                target = target_dir + "/" + file.relative_to(ROOT / source_dir).as_posix()
                require(archive.read(target) == file.read_bytes(), "Packaged source differs: " + target)
        addon_root = ET.fromstring(archive.read("assets/system/addon-manifest.xml"))
        for addon in ADDONS:
            require(any((el.text or "").strip() == addon and el.get("optional") != "true" for el in addon_root),
                    "Packaged addon is not registered: " + addon)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("download", "inspect", "prepare", "verify", "manifest", "hash"):
        part = sub.add_parser(command)
        part.add_argument("path", type=Path)
        part.add_argument("--report", type=Path)
        if command in ("prepare", "verify"):
            part.add_argument("--revision", required=True)
        if command == "prepare":
            part.add_argument("--source-manifest", type=Path)
        if command == "verify":
            part.add_argument("--base-inventory", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "download":
        download_base(args.path)
        data = hashes(args.path)
    elif args.command == "hash":
        data = hashes(args.path)
    elif args.command == "inspect":
        data = inspect_apk(args.path)
        # Retain the ABI report even if the universal gate fails.
        if args.report:
            write_json(args.report, data)
        require_universal(data)
    elif args.command == "prepare":
        data = prepare(args.path, args.revision, args.source_manifest)
    elif args.command == "manifest":
        data = validate_manifest(args.path)
    else:
        data = verify_content(args.path, json.loads(args.base_inventory.read_text()), args.revision)
    if args.report:
        write_json(args.report, data)
    print(json.dumps({key: value for key, value in data.items() if key != "code_hashes"}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Surface actionable gates via Checks API too (log/artifact CDNs may
        # be unreachable from restricted clients). Never replace failure
        # with success or publish an unverified APK.
        message = str(exc).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::error title=SMARTEDTV APK gate::" + message, flush=True)
        raise
