#!/bin/sh
# ---------------------------------------------------------------------------
# Actualiza los precios desde el SISAP y los sube a GitHub (versión Linux/macOS).
# Para un servidor en el Perú (el SISAP bloquea IPs del extranjero), con cron:
#   0 9,12,15,19 * * *  /ruta/a/precios-mayoristas/scripts/actualizar_y_publicar.sh
# (el servidor en hora de Lima; si está en UTC: 0 14,17,20,0 * * *)
# Requiere: git con permiso de escritura al repositorio y Python 3.10+ con
# scripts/requirements.txt instalado (por defecto usa ./venv si existe).
# ---------------------------------------------------------------------------
set -u
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-$( [ -x venv/bin/python ] && echo venv/bin/python || echo python3 )}"
export PYTHONIOENCODING=utf-8

echo "===== $(date '+%Y-%m-%d %H:%M:%S')"
git pull --rebase --autostash -q origin main

"$PY" -W ignore scripts/actualizar_precios.py \
  --salida data/ticker_precios.json --historico data/historico_precios.json

# Solo se hace commit si los datos cambiaron
if [ -z "$(git status --porcelain -- data)" ]; then
  echo "Sin cambios en los datos"
  exit 0
fi
git add data/ticker_precios.json data/historico_precios.json
git commit -q -m "Precios mayoristas (actualizado desde Lima)"
git push -q origin HEAD:main && echo "Publicado en GitHub"
