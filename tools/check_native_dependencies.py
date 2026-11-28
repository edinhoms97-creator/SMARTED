#!/usr/bin/env python3
"""Check DT_NEEDED against packaged ABI libraries and public Android sonames.

ABI-specific optional Kodi addons need not have identical library lists.
They DO need the player core and all non-platform link dependencies.
Does not claim to validate lazy dlopen, codecs or device execution.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

# Public Android NDK native libraries. Notably excludes private libssl,
# libcrypto, libutils, libbinder, and the app-supplied libc++_shared.so.
ANDROID_LIBRARIES = frozenset({
    "libaaudio.so", "libamidi.so", "libandroid.so", "libbinder_ndk.so",
    "libc.so", "libcamera2ndk.so", "libdl.so", "libEGL.so", "libGLESv1_CM.so",
    "libGLESv2.so", "libGLESv3.so", "libjnigraphics.so", "liblog.so", "libm.so",
    "libmediandk.so", "libnativewindow.so", "libneuralnetworks.so", "libOpenMAXAL.so",
    "libOpenSLES.so", "libstdc++.so", "libsync.so", "libvulkan.so", "libz.so",
})


def needed_from_output(output):
    return re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", output)


def unresolved(needed, packaged):
    return sorted(set(needed) - set(packaged) - ANDROID_LIBRARIES)


def validate(folder):
    folder = Path(folder)
    result = {}
    for abi in ("armeabi-v7a", "arm64-v8a"):
        libraries = sorted((folder / abi).glob("*.so"))
        names = {library.name for library in libraries}
        if not names.intersection({"libkodi.so", "libxbmc.so"}):
            raise ValueError("Missing Kodi native core for " + abi)
        result[abi] = {}
        for library in libraries:
            process = subprocess.run(["readelf", "--dynamic", "--wide", str(library)],
                                     capture_output=True, text=True, timeout=20, check=True)
            needed = needed_from_output(process.stdout)
            missing = unresolved(needed, names)
            if missing:
                raise ValueError(f"Unresolved native dependencies in {abi}/{library.name}: {', '.join(missing)}")
            result[abi][library.name] = needed
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate(args.folder)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print("ARM32/ARM64 Kodi core and DT_NEEDED dependencies verified")
    except Exception as exc:
        message = str(exc).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::error title=SMARTEDTV native dependency gate::" + message, flush=True)
        raise
