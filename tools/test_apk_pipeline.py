#!/usr/bin/env python3
"""Fast regression tests: original APK identity and zero skin/startup changes."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import apk_pipeline as apk
import apk_preservation as preserve

AD = "assets/addons/service.smarted.bootstrap/ads_vast.py"


def elf(abi):
    data = bytearray(64)
    data[:4] = b"\x7fELF"
    data[4], machine = apk.ABIS[abi]
    data[5] = 1
    struct.pack_into("<H", data, 18, machine)
    return bytes(data)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, filename="base.apk", changes=None, abis=("armeabi-v7a", "arm64-v8a")):
        content = {
            "AndroidManifest.xml": b"original binary manifest",
            "resources.arsc": b"original compiled resources",
            "classes.dex": b"original-dex",
            "assets/system/addon-manifest.xml": b"original addon registration",
            "assets/addons/service.smarted.bootstrap/service.py": b"original startup",
            "assets/addons/skin.smartedtv.classic/xml/Home.xml": b"original skin",
            "assets/addons/skin.novatv/media/Textures.xbt": b"original textures",
            "assets/smarted/profile/userdata/guisettings.xml": b"original selected skin",
            "META-INF/OLD.RSA": b"old certificate",
            "META-INF/OLD.SF": b"old signature",
            "META-INF/MANIFEST.MF": b"old digest list",
            "META-INF/services/original": b"not a signature; must keep",
            AD: b"original ad module",
        }
        for abi in abis:
            content[f"lib/{abi}/libkodi.so"] = elf(abi)
        content.update(changes or {})
        path = self.root / filename
        with zipfile.ZipFile(path, "w") as target:
            for name, data in content.items():
                target.writestr(name, data)
        return path

    def plan(self):
        return {"reviewed": True, "changes": {AD: {
            "original_sha256": hashlib.sha256(b"original ad module").hexdigest()}}}

    def test_both_real_abis(self):
        apk.require_universal(apk.inspect_apk(self.archive()))

    def test_single_abi_rejected(self):
        with self.assertRaisesRegex(ValueError, "NOT ARM-universal"):
            apk.require_universal(apk.inspect_apk(self.archive(abis=("arm64-v8a",))))

    def test_fake_abi_rejected(self):
        with self.assertRaisesRegex(ValueError, "architecture"):
            apk.inspect_apk(self.archive(changes={"lib/arm64-v8a/fake.so": elf("armeabi-v7a")}))

    def test_zip_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            apk.inspect_apk(self.archive(changes={"../escape": b"x"}))

    def test_exact_base_hash(self):
        path = self.archive()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(apk.verify_base(path, digest)["sha256"], digest)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            apk.verify_base(path, "0" * 64)

    def test_base_override_forbidden(self):
        with patch.dict("os.environ", {"INPUT_BASE_URL": "https://example.invalid/other.apk", "INPUT_BASE_SHA256": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "exact original"):
                apk.download_base(self.root / "never.apk")

    def test_dropbox_block_hash(self):
        data = b"a" * (4 * 1024 * 1024) + b"tail"
        path = self.root / "content"
        path.write_bytes(data)
        expected = hashlib.sha256(hashlib.sha256(data[:-4]).digest() + hashlib.sha256(b"tail").digest()).hexdigest()
        self.assertEqual(apk.hashes(path)["dropbox_content_hash"], expected)

    def test_ads_only_patch_preserves_every_other_entry(self):
        base = self.archive()
        output = self.root / "result.apk"
        report = preserve.patch(base, output, {AD: b"patched VAST only"}, self.plan())
        self.assertEqual(report["changed"], [AD])
        self.assertTrue(report["skin_manifest_resources_startup_unchanged"])
        with zipfile.ZipFile(output) as archive:
            self.assertNotIn("META-INF/OLD.RSA", archive.namelist())
            self.assertEqual(archive.read("META-INF/services/original"), b"not a signature; must keep")

    def test_skin_changes_rejected_even_if_allowlisted(self):
        for path in ("assets/addons/skin.smartedtv.classic/xml/Home.xml",
                     "assets/addons/skin.novatv/default.py", "assets/smarted/profile/addons/skin.original/test.py"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Protected"):
                preserve.check_ad_path(path)

    def test_startup_manifest_and_resources_rejected(self):
        for path in preserve.PROTECTED:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Protected"):
                preserve.check_ad_path(path)

    def test_every_unrelated_change_is_rejected(self):
        base = self.archive()
        for index, path in enumerate(("AndroidManifest.xml", "resources.arsc", "classes.dex",
                                     "assets/addons/skin.novatv/media/Textures.xbt",
                                     "assets/smarted/profile/userdata/guisettings.xml")):
            result = self.archive(f"wrong-{index}.apk", {path: b"changed"})
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "outside ad allowlist"):
                preserve.compare(base, result, {AD})

    def test_no_new_welcome_or_service(self):
        base = self.archive()
        result = self.archive("wrong.apk", {"assets/addons/service.smartedtv.startup/service.py": b"injected"})
        with self.assertRaisesRegex(ValueError, "outside ad allowlist"):
            preserve.compare(base, result, {AD})

    def test_requires_reviewed_nonempty_plan(self):
        for plan in ({}, {"reviewed": True, "changes": {}}, {"reviewed": False, "changes": {AD: {}}}):
            with self.assertRaisesRegex(ValueError, "No reviewed"):
                preserve.validate_plan(plan)

    def test_original_ad_hash_must_match(self):
        plan = self.plan()
        plan["changes"][AD]["original_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            preserve.patch(self.archive(), self.root / "result.apk", {AD: b"new"}, plan)

    def test_unsafe_repackaging_removed(self):
        source = Path(apk.__file__).read_text()
        self.assertNotIn("def patch_manifest", source)
        self.assertNotIn("def prepare", source)
        self.assertNotIn("shutil.copytree", source)
        script = Path(__file__).with_name("build-universal-apk.sh").read_text()
        self.assertIn("exit 1", script)
        self.assertNotIn('apktool', script.lower())

    def test_workflow_only_audits_no_release(self):
        workflow = (apk.ROOT / ".github/workflows/build-universal-apk.yml").read_text()
        self.assertIn("  workflow_dispatch:", workflow)
        for text in ("  push:", "  pull_request:", "gh release create", "build-universal-apk.sh"):
            self.assertNotIn(text, workflow)


if __name__ == "__main__":
    unittest.main()
