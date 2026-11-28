#!/usr/bin/env python3
"""Replace SMARTEDTV addon files in a decoded APK directory."""
import shutil
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
ADDONS = ("script.smartedtv.welcome", "service.smartedtv.startup", "skin.estilo.personalizado")

def main():
    decoded = Path(sys.argv[1])
    assets = decoded / "assets"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")

    for addon in ADDONS:
        source = ROOT / ("skin" if addon.startswith("skin.") else "kodi-addon") / addon
        target = assets / "addons" / addon
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=ignore)
        print(f"Copied: {addon}")

    web = assets / "smartedtv"
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(ROOT / "smartedtv", web, ignore=ignore)
    print("Copied: smartedtv web interface")

    addon_manifest = assets / "system/addon-manifest.xml"
    tree = ET.parse(addon_manifest)
    for addon in ADDONS:
        existing = next((el for el in tree.getroot() if (el.text or "").strip() == addon), None)
        if existing is None:
            existing = ET.SubElement(tree.getroot(), "addon")
            existing.text = addon
        existing.attrib.pop("optional", None)
    tree.write(addon_manifest, encoding="utf-8", xml_declaration=True)
    print("Addon manifest updated")

if __name__ == "__main__":
    main()
