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
import ssl
import struct
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "android-build/base-apk.json").read_text())
ABIS = {"armeabi-v7a": (1, 40), "arm64-v8a": (2, 183),
        "x86": (1, 3), "x86_64": (2, 62)}


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
    require(not override_url and not override_sha, "Only the exact original Dropbox APK is allowed; base overrides are disabled")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("download", "inspect", "hash"):
        part = sub.add_parser(command)
        part.add_argument("path", type=Path)
        part.add_argument("--report", type=Path)
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
