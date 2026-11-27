#!/usr/bin/env python3
"""Tiny synthetic archives: exercise build gates without SDK/emulator/network."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

SPEC = importlib.util.spec_from_file_location("apk_pipeline", Path(__file__).with_name("apk_pipeline.py"))
apk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apk)
MANIFEST = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="test.smartedtv">
<uses-sdk android:minSdkVersion="21" android:targetSdkVersion="35"/>
<uses-feature android:name="android.hardware.touchscreen" android:required="true"/>
<application android:testOnly="true"><activity android:name=".Main" android:exported="false">
<intent-filter><action android:name="android.intent.action.MAIN"/>
<category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity>
<activity android:name=".OldTv"><intent-filter><action android:name="android.intent.action.MAIN"/>
<category android:name="android.intent.category.LEANBACK_LAUNCHER"/></intent-filter></activity>
</application></manifest>'''


def elf(abi):
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4], machine = apk.ABIS[abi]
    header[5] = 1
    struct.pack_into("<H", header, 18, machine)
    return bytes(header)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, abis=("armeabi-v7a", "arm64-v8a"), extras=None):
        path = self.root / "input.apk"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AndroidManifest.xml", MANIFEST)
            archive.writestr("classes.dex", b"dex\n035\0fixture")
            for abi in abis:
                archive.writestr(f"lib/{abi}/libkodi.so", elf(abi))
            for name, content in (extras or {}).items():
                archive.writestr(name, content)
        return path

    def test_real_multiabi_inventory(self):
        data = apk.inspect_apk(self.archive())
        apk.require_universal(data)
        self.assertEqual(len(data["code_hashes"]), 3)

    def test_single_abi_cannot_be_renamed_universal(self):
        with self.assertRaisesRegex(ValueError, "NOT ARM-universal"):
            apk.require_universal(apk.inspect_apk(self.archive(("arm64-v8a",))))

    def test_fake_abi_folder_is_not_sufficient(self):
        path = self.archive(extras={"lib/arm64-v8a/libfake.so": elf("armeabi-v7a")})
        with self.assertRaisesRegex(ValueError, "architecture"):
            apk.inspect_apk(path)

    def test_incomplete_native_dependencies_rejected(self):
        path = self.archive(extras={"lib/arm64-v8a/libextra.so": elf("arm64-v8a")})
        with self.assertRaisesRegex(ValueError, "library sets differ"):
            apk.require_universal(apk.inspect_apk(path))

    def test_zip_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            apk.inspect_apk(self.archive(extras={"../payload": b"x"}))

    def test_custom_base_sha256_is_enforced(self):
        path = self.archive()
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(apk.verify_base(path, expected)["sha256"], expected)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            apk.verify_base(path, "0" * 64)

    def test_dropbox_hash_uses_four_mib_blocks(self):
        content = b"a" * (4 * 1024 * 1024) + b"tail"
        path = self.root / "blob"
        path.write_bytes(content)
        expected = hashlib.sha256(hashlib.sha256(content[:-4]).digest() + hashlib.sha256(b"tail").digest()).hexdigest()
        self.assertEqual(apk.hashes(path)["dropbox_content_hash"], expected)
        self.assertNotEqual(expected, apk.hashes(path)["sha256"])

    def test_manifest_unifies_mobile_tv_and_optional_hardware(self):
        path = self.root / "AndroidManifest.xml"
        path.write_text(MANIFEST)
        apk.patch_manifest(path)
        info = apk.validate_manifest(path)
        self.assertEqual(info["launcher"], ".Main")
        self.assertEqual(info["package"], "test.smartedtv")
        self.assertEqual(info["sdk"]["minSdkVersion"], "21")
        root = ET.parse(path).getroot()
        self.assertNotIn(apk.ANDROID + "testOnly", root.find("application").attrib)
        apk.patch_manifest(path)  # must be idempotent
        apk.validate_manifest(path)

    def test_ambiguous_mobile_launcher_rejected(self):
        path = self.root / "AndroidManifest.xml"
        path.write_text(MANIFEST.replace(".OldTv", ".Other").replace("LEANBACK_LAUNCHER", "LAUNCHER"))
        with self.assertRaisesRegex(ValueError, "one MAIN"):
            apk.patch_manifest(path)

    def test_shared_uid_rejected_for_debug_signing(self):
        path = self.root / "AndroidManifest.xml"
        path.write_text(MANIFEST.replace('package="test.smartedtv"', 'package="test.smartedtv" android:sharedUserId="system"'))
        with self.assertRaisesRegex(ValueError, "Shared UID"):
            apk.patch_manifest(path)

    def test_unsupported_kodi_layout_fails_instead_of_inert_packaging(self):
        with self.assertRaisesRegex(ValueError, "Kodi Python addon layout"):
            apk.prepare(self.root, "a" * 40)

    def test_overlay_registers_live_addons_and_verifies_source_bytes(self):
        decoded = self.root / "decoded"
        assets = decoded / "assets"
        (assets / "addons/xbmc.python").mkdir(parents=True)
        (assets / "addons/xbmc.python/addon.xml").write_text("<addon/>")
        (assets / "system").mkdir()
        (assets / "system/addon-manifest.xml").write_text("<addons><addon>xbmc.python</addon></addons>")
        (decoded / "AndroidManifest.xml").write_text(MANIFEST)
        # Apktool commonly strips uses-sdk into apktool.yml. Supply the
        # original binary-manifest dump to restore the exact SDK values.
        original = self.root / "base-AndroidManifest.xml"
        original.write_text(MANIFEST)
        stripped = ET.parse(decoded / "AndroidManifest.xml")
        stripped.getroot().remove(stripped.getroot().find("uses-sdk"))
        stripped.write(decoded / "AndroidManifest.xml")
        result = apk.prepare(decoded, "a" * 40, original)
        self.assertFalse(result["admob_enabled"])
        root = ET.parse(assets / "system/addon-manifest.xml").getroot()
        self.assertTrue(set(apk.ADDONS).issubset({el.text for el in root}))
        # Include fake native code only to test the packaging verifier.
        for abi in ("arm64-v8a", "armeabi-v7a"):
            folder = decoded / "lib" / abi
            folder.mkdir(parents=True)
            (folder / "libkodi.so").write_bytes(elf(abi))
        (decoded / "classes.dex").write_bytes(b"fixture-dex")
        built = self.root / "assembled.apk"
        with zipfile.ZipFile(built, "w") as archive:
            for file in decoded.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(decoded).as_posix())
        inventory = apk.inspect_apk(built)
        apk.verify_content(built, inventory, "a" * 40)
        inventory["code_hashes"]["classes.dex"] = "bad"
        with self.assertRaisesRegex(ValueError, "Native/Dex bytes changed"):
            apk.verify_content(built, inventory, "a" * 40)

    def test_alternate_download_requires_hash_pair(self):
        with patch.dict("os.environ", {"INPUT_BASE_URL": "https://example.invalid/base.apk", "INPUT_BASE_SHA256": ""}):
            with self.assertRaisesRegex(ValueError, "supplied together"):
                apk.download_base(self.root / "not-downloaded.apk")

    def test_workflow_is_manual_only_and_signs_before_delivery(self):
        text = (apk.ROOT / ".github/workflows/build-universal-apk.yml").read_text()
        self.assertIn("  workflow_dispatch:", text)
        for trigger in ("  push:", "  pull_request:", "  workflow_run:", "  schedule:"):
            self.assertNotIn(trigger, text)
        shell = (apk.ROOT / "tools/build-universal-apk.sh").read_text()
        self.assertLess(shell.index('apksigner" sign'), shell.index('apksigner" verify --verbose --print-certs "$OUT/SMARTEDTV-universal.apk"'))
        self.assertIn('zipalign" -P 16 -c', shell)


if __name__ == "__main__":
    unittest.main()
