#!/usr/bin/env python3
"""
Mide a qué hora publican sus datos el SISAP y el boletín de aves del SIEA.

No cambia ni publica datos: en cada corrida agrega filas a un CSV con cuántas
variedades tiene hoy cada mercado, cuántas repiten el precio de ayer (una copia
del día anterior no es un dato nuevo) y si ya existe el PDF de hoy.

    python scripts/medir_publicacion.py --salida medicion_publicacion.csv
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path

import requests

from actualizar_precios import AVES, FRUTAS2, GMML, LIMA_TZ, SANTA_ANITA, catalogo, consultar, crear_sesion

MERCADOS = {GMML: "Gran Mercado", FRUTAS2: "Frutas N2", AVES: "Aves", SANTA_ANITA: "Santa Anita"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
URL_PDF = "https://siea.midagri.gob.pe/files/datos_estadisticas/diarias/aves/{a}/{m:02d}/sisap-aves-{d:02d}{mes}{aa:02d}.pdf"


def medir_mercado(sesion, mercado: str, hoy, ayer) -> tuple[int | str, int | str]:
    try:
        codigos = catalogo(sesion, mercado)
        de_hoy = consultar(sesion, mercado, codigos, hoy)
        de_ayer = consultar(sesion, mercado, codigos, ayer) if de_hoy else {}
    except requests.RequestException:
        return "error", ""
    iguales = sum(1 for k, v in de_hoy.items() if k in de_ayer and v[0] == de_ayer[k][0])
    return len(de_hoy), iguales


def medir_pdf(sesion, hoy) -> tuple[str, str]:
    url = URL_PDF.format(a=hoy.year, m=hoy.month, d=hoy.day, mes=MESES[hoy.month - 1], aa=hoy.year % 100)
    try:
        r = sesion.head(url, timeout=(10, 25), allow_redirects=True)
    except requests.RequestException:
        return "error", ""
    return ("si", r.headers.get("Last-Modified", "")) if r.status_code == 200 else ("no", "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default="medicion_publicacion.csv")
    args = ap.parse_args()

    ahora = datetime.now(LIMA_TZ)
    hoy, ayer = ahora.date(), ahora.date() - timedelta(days=1)
    sesion = crear_sesion()
    momento = ahora.isoformat(timespec="minutes")
    filas = [[momento, nombre, *medir_mercado(sesion, m, hoy, ayer), ""] for m, nombre in MERCADOS.items()]
    existe, modificado = medir_pdf(sesion, hoy)
    filas.append([momento, "PDF aves", existe, "", modificado])

    ruta = Path(args.salida)
    nuevo = not ruta.exists()
    with ruta.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["momento", "fuente", "variedades_o_existe", "iguales_a_ayer", "ultima_modificacion"])
        w.writerows(filas)
    for fila in filas:
        print(*fila, sep=" | ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
