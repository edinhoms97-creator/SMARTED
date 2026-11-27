#!/usr/bin/env python3
"""Read-only, narrowly scoped original ad contracts; omit unrelated settings/UI.

URLs other than the user-provided VAST tag and potential credential literals
are redacted before emitting selected ad functions to public annotations.
"""
import ast
import copy
import json
import re
import sys
import zipfile

BASE = "assets/addons/service.smarted.bootstrap/"
GROUPS = {
    "transport": ("ads_vast.py", ("tag_configurada", "escolher_anuncio", "baixar", "disparar")),
    "resume": ("ads_vast.py", ("estado_do_conteudo", "restaurar", "exibir_e_devolver")),
    "routing": ("smart_ads.py", ("motor_anuncio", "usar_vast", "tocar_anuncio_de_video", "mostrar_preroll", "mostrar_abertura", "abrir_anuncio")),
    "fetchflow": ("ads_vast.py", ("exibir",)),
    "playback": ("ads_vast.py", ("reproduzir",)),
    "frequency": ("ads_regra.py", ("abrir_troca", "pode_anunciar", "registrar_anuncio", "cancelar_anuncio", "marcar_conteudo")),
    "monitor": ("smart_ads.py", ("tocar_anuncio", "tocar_anuncio_com_aviso", "monitor", "iniciar_monitor")),
}


class Redact(ast.NodeTransformer):
    def visit_Constant(self, node):
        if isinstance(node.value, str):
            s = node.value
            if (("https://" in s or "http://" in s) and not s.startswith("https://vast.yomeno.xyz/vast")) or re.search(r"[A-Za-z0-9_+/=-]{48,}", s):
                return ast.copy_location(ast.Constant("<redacted-network-or-token-literal>"), node)
        return node


def contract(path, group):
    filename, names = GROUPS[group]
    with zipfile.ZipFile(path) as archive:
        tree = ast.parse(archive.read(BASE + filename).decode("utf-8-sig"))
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    result = {"path": BASE + filename, "functions": [node.name for node in functions], "selected": {}}
    for node in functions:
        if node.name in names:
            result["selected"][node.name] = ast.unparse(Redact().visit(copy.deepcopy(node)))
    result["ad_constants"] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and re.search(r"VAST|ADMOB|TIMEOUT|USER_AGENT|TLS", target.id, re.I)
                for target in node.targets):
            result["ad_constants"].append(ast.unparse(Redact().visit(copy.deepcopy(node))))
    return result


if __name__ == "__main__":
    group = sys.argv[2]
    text = json.dumps(contract(sys.argv[1], group), ensure_ascii=True)
    chunks = [text[i:i + 2800] for i in range(0, len(text), 2800)]
    if len(chunks) > 9:
        raise ValueError("Ad contract too large for safe Checks annotation transport")
    for i, chunk in enumerate(chunks):
        payload = json.dumps({"group": group, "part": i, "parts": len(chunks), "data": chunk})
        safe = payload.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::notice title=SMARTED original ad contract::" + safe)
