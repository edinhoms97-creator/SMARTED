#!/usr/bin/env bash
# The previous build changed startup/skin and failed on the user's device.
# Fail closed until an ads-only patch against the exact original is reviewed.
set -Eeuo pipefail
printf '%s\n' '::error title=Build anterior retirado::Publicacao bloqueada: nao substituir skin, welcome, inicializacao, manifesto ou recursos do APK original. Auditar o ponto de anuncios existente antes de empacotar novamente.' >&2
exit 1
