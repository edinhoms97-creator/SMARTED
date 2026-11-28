#!/usr/bin/env python3
"""Read-only APK inspection. Never extracts private config or publishes sources.

Expose filenames, hashes, addon identities and function names through Checks
annotations, since the sandbox cannot reach GitHub artifact/log CDNs.
"""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


def audit(path):
    result = {"mode": "read-only-original-apk", "skin_addons": [], "startup_addons": [],
              "candidate_code": [], "bootstrap_files": [], "containers": [], "asset_groups": {}}
    with zipfile.ZipFile(path) as archive:
        groups = Counter()
        for info in archive.infolist():
            name = info.filename
            if name.startswith("assets/"):
                groups["/".join(name.split("/")[:3])] += 1
            if name.startswith("assets/addons/service.smarted.bootstrap/") and not name.endswith("/"):
                result["bootstrap_files"].append({"path": name, "size": info.file_size,
                                                  "sha256": hashlib.sha256(archive.read(name)).hexdigest()})
            if name.endswith((".zip", ".7z", ".tar", ".obb")):
                result["containers"].append({"path": name, "size": info.file_size})
            if name.endswith("/addon.xml") and info.file_size < 100000:
                try:
                    root = ET.fromstring(archive.read(name))
                except ET.ParseError:
                    continue
                extensions = [el.get("point") for el in root.findall("extension")]
                identity = {"path": name, "id": root.get("id"), "name": root.get("name"),
                            "version": root.get("version"), "sha256": hashlib.sha256(archive.read(name)).hexdigest()}
                if "xbmc.gui.skin" in extensions:
                    result["skin_addons"].append(identity)
                if "xbmc.service" in extensions:
                    result["startup_addons"].append(identity)
            if (name.endswith((".py", ".js", ".html")) and info.file_size < 1024 * 1024
                    and not any(part in name for part in ("python3.", "/site-packages/", "/script.module."))):
                data = archive.read(name)
                text = data.decode("utf-8", errors="replace")
                terms = [term for term in ("vast", "admob", "clickadilla", "spot_id", "smarted", "welcome")
                         if re.search(r"\b" + term + r"\b", text, re.I) or term in Path(name).name.lower()]
                if not terms and not name.startswith("assets/addons/service.smarted.bootstrap/"):
                    continue
                entry = {"path": name, "size": info.file_size,
                         "sha256": hashlib.sha256(data).hexdigest(), "terms": terms}
                if name.endswith(".py"):
                    try:
                        tree = ast.parse(text)
                        entry["functions"] = [node.name for node in ast.walk(tree)
                                              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))][:60]
                        entry["imports"] = sorted({node.module or "" for node in ast.walk(tree)
                                                   if isinstance(node, ast.ImportFrom)}
                                                  | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                                                     for alias in node.names})[:40]
                    except SyntaxError:
                        entry["ast"] = "unparsed"
                result["candidate_code"].append(entry)
        result["asset_groups"] = dict(sorted(groups.items()))
    return result


def notices(report):
    # GitHub limits notices per step; one annotation per section, not many
    # chunks that can silently omit the important first addon candidates.
    for section in ("skin_addons", "startup_addons", "bootstrap_files", "candidate_code", "containers", "asset_groups"):
        items = report[section]
        if section == "candidate_code":
            items = sorted(items, key=lambda el: (
                not bool(set(el["terms"]) & {"vast", "admob", "clickadilla", "spot_id"}),
                not el["path"].startswith("assets/addons/service.smarted.bootstrap/"), el["path"]))[:30]
        if isinstance(items, dict):
            items = [{"path": key, "entries": value} for key, value in items.items()][:100]
        message = json.dumps({section: items}, ensure_ascii=True)
        message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::notice title=SMARTED original inventory::" + message, flush=True)


if __name__ == "__main__":
    report = audit(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    notices(report)
