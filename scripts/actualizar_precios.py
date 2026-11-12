#!/usr/bin/env python3
"""
Ticker y dashboard de precios mayoristas - El Comercio
Extrae precios diarios del SISAP (MIDAGRI) y genera:
  * data/historico_precios.json  -> todos los productos, serie diaria de 90 días (dashboard)
  * data/ticker_precios.json     -> 7 productos con su último precio y variación (ticker)

Endpoints (descubiertos en el JS del portal SISAP v2, módulo "Mercados"):
    POST http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/generos/filtrarPorMercado
         mercado=<código>  -> catálogo de productos del mercado (checkboxes con su código)
    POST http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/resumenes/filtrar
         mercado, variables[]=precio_prom, fecha=DD/MM/AAAA, productos[]=<código> (repetible),
         periodicidad=dia, __ajax_carga_final=consulta
         -> fragmento HTML (latin-1) con una <table> Producto | Variedad | Precio.

Funcionamiento:
  * Cada corrida descarga el catálogo completo de cada mercado y guarda TODAS las
    variedades con precio (no hay lista fija): si el Midagri agrega un producto,
    aparece solo.
  * El histórico es incremental: por mercado se recuerdan los días ya consultados y
    solo se piden los que faltan en la ventana de 90 días, más los últimos 3 días
    siempre (el MIDAGRI puede completarlos durante la mañana).
  * El Gran Mercado Mayorista no opera domingos ni feriados, pero el SISAP repite
    esos días los precios del anterior: esas copias se descartan.

Resiliencia:
  * Reintentos HTTP con backoff exponencial ante timeouts y errores 5xx.
  * Circuit breaker: tras 3 fallos de red seguidos deja de consultar.
  * Si el MIDAGRI aún no publicó "hoy", el ticker usa la última fecha con al
    menos --min-items de sus productos y la compara con la fecha previa de cada uno.
  * Un producto del ticker sin dato en esa fecha conserva su último valor, marcado
    "desactualizado": true.
  * Nunca se sobrescribe un JSON con datos insuficientes. Escritura atómica
    (archivo temporal + rename) y sin reescritura si nada cambió.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL_CATALOGO = "http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/generos/filtrarPorMercado"
URL_REPORTE = "http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/resumenes/filtrar"
LIMA_TZ = timezone(timedelta(hours=-5))  # Perú no usa horario de verano
HISTORICO_DIAS = 90
REFRESCAR_DIAS = 3        # los últimos N días se vuelven a pedir en cada corrida
MAX_ERRORES_SEGUIDOS = 3  # tras 3 fallos de red consecutivos se asume servidor caído
MIN_SERIES_COPIA = 10     # solo se buscan copias en mercados con 10+ variedades ese día
VERSION_HISTORICO = 3
FUENTE = "MIDAGRI - SISAP"

# Códigos de mercado (select#mercado del portal)
GMML = "15011501"         # Gran Mercado Mayorista de Lima
FRUTAS2 = "15011502"      # Mercado Mayorista N° 2 de Frutas
AVES = "15010106"         # Mercado Mayorista de Aves Vivas
SANTA_ANITA = "15013704"  # Mercado de Productores de Santa Anita
CEREALES = "15011506"     # Mercado Mayorista de Cereales, Legumbres y Oleaginosas
PLATANOS = "15013405"     # Mercado Cooperativo de Plátanos
# (El Mercado Modelo de Frutas, 15011503, no publica precios: no se incluye)

# Orden = prioridad. Si una variedad se vende en varios mercados, la del primero es la
# "principal" (entra al ranking) y las demás llevan el mercado en el nombre.
# (código, nombre completo, sufijo para el id, nombre corto para mostrar)
MERCADOS = [
    (GMML,        "Gran Mercado Mayorista de Lima",                         "",            ""),
    (FRUTAS2,     "Mercado Mayorista N° 2 de Frutas",                       "frutas",      "Mercado de Frutas"),
    (AVES,        "Mercado Mayorista de Aves Vivas",                        "aves",        "Aves vivas"),
    (SANTA_ANITA, "Mercado de Productores de Santa Anita",                  "santa-anita", "Santa Anita"),
    (CEREALES,    "Mercado Mayorista de Cereales, Legumbres y Oleaginosas", "cereales",    "Mercado de Cereales"),
    (PLATANOS,    "Mercado Cooperativo de Plátanos",                        "platanos",    "Mercado de Plátanos"),
]
INFO_MERCADO = {m[0]: m for m in MERCADOS}

# Canasta de 15 productos básicos para el índice "¿Subieron los precios?": (mercado, variedad en SISAP)
CANASTA = [
    (GMML, "Limon Sutil Cajon"), (AVES, "Pollo Vivo"), (GMML, "Papa Canchan"), (GMML, "Papa Amarilla"),
    (GMML, "Papa Blanca"), (GMML, "Cebolla Cabeza Roja"), (GMML, "Choclo ( Tipo Cusco)"), (GMML, "Tomate"),
    (GMML, "Zanahoria"), (GMML, "Aji Escabeche"), (GMML, "Ajo Morado"), (GMML, "Camote Amarillo"),
    (GMML, "Yuca Amarilla"), (FRUTAS2, "Palta Fuerte"), (FRUTAS2, "Palta Hass"),
]

# Productos del ticker, en el orden en que se muestran: (mercado, variedad en SISAP, etiqueta, silueta)
TICKER = [  # en orden alfabético; la etiqueta se muestra tal cual
    (GMML,        "Camote Amarillo",      "Camote amarillo",    "camote"),
    (GMML,        "Cebolla Cabeza Roja",  "Cebolla roja",       "cebolla"),
    (GMML,        "Choclo ( Tipo Cusco)", "Choclo",             "choclo"),
    (SANTA_ANITA, "Huevos Rosados",       "Huevos rosados",     "huevo"),
    (GMML,        "Kion",                 "Kion",               "kion"),
    (GMML,        "Limon Sutil Cajon",    "Limón",              "limon"),
    (FRUTAS2,     "Palta Fuerte",         "Palta fuerte",       "palta"),
    (GMML,        "Papa Amarilla",        "Papa amarilla",      "papa"),
    (GMML,        "Papa Blanca",          "Papa blanca",        "papa"),
    (FRUTAS2,     "Platano Seda Congo",   "Plátano seda Congo", "platano"),
    (AVES,        "Pollo Vivo",           "Pollo vivo",         "pollo"),
    (GMML,        "Yuca Amarilla",        "Yuca amarilla",      "yuca"),
]

# --- Nombres para mostrar -------------------------------------------------------
# El SISAP escribe sin tildes y En Mayúsculas Iniciales. Se corrigen tildes, se pasa a
# mayúscula inicial (estilo de la portada) y se respetan los nombres propios.
TILDES = {
    "aji": "ají", "limon": "limón", "cajon": "cajón", "maiz": "maíz", "maracuya": "maracuyá",
    "melon": "melón", "melocoton": "melocotón", "platano": "plátano", "sandia": "sandía",
    "brocoli": "brócoli", "esparrago": "espárrago", "guanabana": "guanábana", "canchan": "canchán",
    "unica": "única", "morron": "morrón", "yacon": "yacón", "llacon": "llacón", "rio": "río",
    "hidroponica": "hidropónica", "organica": "orgánica", "lucuma": "lúcuma", "azucar": "azúcar",
    "mani": "maní", "ajonjoli": "ajonjolí", "chia": "chía", "frejol": "fréjol",
    "pina": "piña", "pimenton": "pimentón", "fruticolas": "frutícolas", "agricolas": "agrícolas",
    "tallarin": "tallarín", "maria": "maría", "cafe": "café",
}
# Nombres propios y marcas (una palabra): van con mayúscula inicial
PROPIOS = {
    "cusco", "hass", "washington", "valencia", "golden", "israel", "winter", "kent", "edward",
    "haden", "hayde", "kafro", "murcott", "satsuma", "thompson", "italia", "borgoña", "palestina",
    "fley", "arra", "pirovano", "queen", "hall", "huayco", "cumbe", "sabrina", "tangelo",
    "napuri", "huamantanga", "yungay", "loche", "congo", "tango", "delicia",
    "alsol", "laive", "vigor", "gloria", "ideal", "cartavio", "paramonga", "andahuasi", "laredo",
    "pomalca", "anita", "molitalia", "nicolini", "chanchamayo", "ayacucho",
}
# Nombres propios de varias palabras (se aplican después de la mayúscula inicial)
FRASES = {
    "red globe": "Red Globe", "río de oro": "Río de Oro", "villa campa": "Villa Campa", "kin kan": "Kin Kan",
    "san andreas": "San Andreas", "alfonso lavalett": "Alfonso Lavalett", "casa grande": "Casa Grande",
    "caña brava": "Caña Brava", "dulce norte": "Dulce Norte", "dulce olmos": "Dulce Olmos",
    "san jacinto": "San Jacinto", "don angelo": "Don Angelo", "sta. anita": "Santa Anita",
    "villa rica": "Villa Rica", "tingo maría": "Tingo María", "uht": "UHT",
}
# Nombres editoriales para algunas variedades (clave = variedad normalizada)
NOMBRES = {
    "limon sutil cajon": "Limón sutil (cajón)",
    "limon sutil bolsa": "Limón sutil (bolsa)",
    "cebolla cabeza roja": "Cebolla roja",
    "cebolla cabeza blanca": "Cebolla blanca",
    "aji escabeche": "Ají amarillo escabeche",
}
# Productos que el SISAP cotiza por litro (el resto, por kilo)
POR_LITRO = {"aceite", "leche"}

log = logging.getLogger("ticker")


def normalizar(texto: str) -> str:
    """'Limón  Sutil Cajón' -> 'limon sutil cajon' (para comparar variedades)."""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def nombre_bonito(texto: str) -> str:
    """'Choclo ( Tipo Cusco)' -> 'Choclo (tipo Cusco)'; 'Platano Seda ( Selva)' -> 'Plátano seda (selva)'."""
    clave = normalizar(texto)
    if clave in NOMBRES:
        return NOMBRES[clave]
    t = re.sub(r"\s+", " ", texto).strip()
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    propios = {normalizar(x) for x in PROPIOS}
    palabras = []
    for i, p in enumerate(t.split(" ")):
        abre = p.startswith("(")
        base = p.lstrip("(")
        cierra = base.endswith(")")
        base = base.rstrip(")")
        b = base.lower()
        b = TILDES.get(normalizar(b), b)
        if i == 0 or normalizar(b) in propios:
            b = b[:1].upper() + b[1:]
        palabras.append(("(" if abre else "") + b + (")" if cierra else ""))
    t = " ".join(palabras)
    for frase, propia in FRASES.items():
        t = re.sub(r"(?i)(?<![\wáéíóúñ])" + re.escape(frase) + r"(?![\wáéíóúñ])", propia, t)
    return t


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")


def crear_sesion() -> requests.Session:
    reintentos = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=5,  # 5s, 10s, 20s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),  # el POST es una consulta idempotente
    )
    s = requests.Session()
    s.mount("http://", HTTPAdapter(max_retries=reintentos))
    s.mount("https://", HTTPAdapter(max_retries=reintentos))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; ElComercio-TickerPrecios/1.0)",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/",
    })
    return s


def catalogo(sesion: requests.Session, mercado: str) -> list[str]:
    """Códigos de todos los productos que el portal ofrece para un mercado."""
    r = sesion.post(URL_CATALOGO, data={"mercado": mercado}, timeout=(10, 35))
    r.raise_for_status()
    html = r.content.decode("latin-1", errors="replace")
    return list(dict.fromkeys(re.findall(r'value="?(\d{4})"?[^>]*type=checkbox', html)))


def consultar(sesion: requests.Session, mercado: str, productos: list[str], dia: date) -> dict[str, tuple]:
    """{variedad_normalizada: (precio, variedad, producto)} para un mercado y día. {} si no hay datos."""
    payload = [
        ("mercado", mercado),
        ("variables[]", "precio_prom"),
        ("fecha", dia.strftime("%d/%m/%Y")),
        ("periodicidad", "dia"),
        ("__ajax_carga_final", "consulta"),
    ] + [("productos[]", p) for p in productos]

    # 35 s de lectura: el mismo límite que usa el JS del portal para esta consulta
    r = sesion.post(URL_REPORTE, data=payload, timeout=(10, 35))
    r.raise_for_status()
    html = r.content.decode("latin-1", errors="replace")

    if "mensajeDeError" in html or "No existen resultados" in html:
        return {}

    precios: dict[str, tuple] = {}
    producto = ""
    for fila in BeautifulSoup(html, "html.parser").select("tr.contenido"):
        celdas = [td.get_text(" ", strip=True) for td in fila.find_all("td")]
        # Primera fila de cada producto trae <td rowspan> con el nombre del producto:
        # [Producto, Variedad, Precio]; las siguientes solo [Variedad, Precio].
        if len(celdas) < 2:
            continue
        if len(celdas) >= 3:
            producto = celdas[-3]
        variedad, valor = celdas[-2], celdas[-1]
        try:
            precio = float(valor.replace(",", ""))
        except ValueError:
            continue
        if precio > 0:
            precios[normalizar(variedad)] = (precio, variedad, producto)
    return precios


# ---------------------------------------------------------------- histórico

def cargar_json(ruta: Path) -> dict:
    try:
        with ruta.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def historico_a_memoria(hist: dict):
    """
    Formato en disco -> (precios {id: {fecha: precio}}, productos {(mercado, clave): ficha},
    consultas {mercado: {fechas ya consultadas}}). Un histórico de una versión anterior
    se descarta y se vuelve a descargar completo.
    """
    if hist.get("version") != VERSION_HISTORICO:
        if hist:
            log.info("Histórico de una versión anterior: se descargará de nuevo completo")
        return {}, {}, {}
    fechas = hist.get("fechas", [])
    precios = {pid: {f: v for f, v in zip(fechas, vals) if v is not None}
               for pid, vals in hist.get("precios", {}).items()}
    productos = {(p["mercado_codigo"], p["clave"]): p for p in hist.get("productos", []) if p.get("sisap")}
    consultas = {m: set(fs) for m, fs in hist.get("consultas", {}).items()}
    return precios, productos, consultas


def rotular(f: dict) -> dict:
    """Calcula los campos para mostrar desde el texto original del SISAP. Se repite en cada
    corrida, así una corrección de nombres se aplica también a lo ya descargado."""
    _, nombre_mercado, _, corto = INFO_MERCADO[f["mercado_codigo"]]
    nombre = nombre_bonito(f["sisap"])
    f["nombre"] = nombre if f["principal"] else f"{nombre} · {corto}"
    f["grupo"] = nombre_bonito(f["sisap_producto"]) if f.get("sisap_producto") else nombre.split(" ")[0]
    f["mercado"] = nombre_mercado
    f["unidad"] = "litro" if normalizar(f.get("sisap_producto", "")) in POR_LITRO else "kg"
    f["canasta"] = (f["mercado_codigo"], f["clave"]) in {(m, normalizar(v)) for m, v in CANASTA}
    return f


def ficha(productos: dict, mercado: str, clave: str, variedad: str, producto: str) -> dict:
    """Devuelve (o crea) la ficha de una variedad, con un id estable entre corridas."""
    if (mercado, clave) in productos:
        f = productos[(mercado, clave)]
        f["sisap"], f["sisap_producto"] = variedad, producto or f.get("sisap_producto", "")
        return f
    sufijo = INFO_MERCADO[mercado][2]
    # Principal si ningún mercado de mayor prioridad tiene ya esa variedad
    principal = not any(c == clave for (m, c) in productos if m != mercado)
    ids = {p["id"] for p in productos.values()}
    pid = slug(clave)
    if not principal or pid in ids:
        pid = f"{pid}-{sufijo or 'gmml'}"
    f = {"id": pid, "mercado_codigo": mercado, "clave": clave, "principal": principal,
         "sisap": variedad, "sisap_producto": producto}
    productos[(mercado, clave)] = rotular(f)
    return f


def actualizar_historico(sesion, precios, productos, consultas, hoy: date, dias: int) -> int:
    """Completa en memoria los días faltantes de la ventana. Devuelve nº de consultas exitosas."""
    exitosas, errores_seguidos = 0, 0
    for mercado, nombre_mercado, *_ in MERCADOS:
        if errores_seguidos >= MAX_ERRORES_SEGUIDOS:
            log.error("Circuit breaker: SISAP no responde, se aborta la consulta de %s", nombre_mercado)
            continue
        try:
            codigos = catalogo(sesion, mercado)
            errores_seguidos = 0
        except requests.RequestException as e:
            errores_seguidos += 1
            log.warning("%s: no se pudo leer el catálogo (%s)", nombre_mercado, e)
            continue
        if not codigos:
            continue
        hechas = consultas.setdefault(mercado, set())
        for i in range(dias):
            dia = hoy - timedelta(days=i)
            iso = dia.isoformat()
            reciente = i < REFRESCAR_DIAS
            if iso in hechas and not reciente:
                continue
            if errores_seguidos >= MAX_ERRORES_SEGUIDOS:
                log.error("Circuit breaker: SISAP no responde, se aborta la consulta de %s", nombre_mercado)
                break
            try:
                res = consultar(sesion, mercado, codigos, dia)
                errores_seguidos = 0
                exitosas += 1
            except requests.RequestException as e:
                errores_seguidos += 1
                log.warning("%s, %s: error de red tras reintentos (%s)", nombre_mercado, iso, e)
                continue
            for clave, (precio, variedad, producto) in res.items():
                f = ficha(productos, mercado, clave, variedad, producto)
                precios.setdefault(f["id"], {})[iso] = precio
            # Un día reciente vacío puede publicarse más tarde: no se da por consultado
            if not reciente:
                hechas.add(iso)
            log.info("%s, %s: %d variedades", nombre_mercado, iso, len(res))
    return exitosas


def quitar_copias(precios, productos, hoy: date) -> int:
    """
    El Gran Mercado Mayorista no opera domingos ni feriados, pero el SISAP repite esos
    días los precios del día anterior. Si TODAS las variedades de un mercado son idénticas
    al último día válido, el día se descarta (si no, el ticker mostraría 0.0% en todo cada
    domingo). Solo aplica a mercados con 10+ variedades ese día: en uno pequeño, un precio
    igual al de ayer puede ser real.
    """
    por_mercado: dict[str, list[str]] = {}
    for f in productos.values():
        por_mercado.setdefault(f["mercado_codigo"], []).append(f["id"])

    quitados = 0
    for mercado, pids in por_mercado.items():
        fechas = sorted(set().union(*(precios.get(p, {}).keys() for p in pids)))
        previo: dict | None = None
        for f in fechas:
            valores = {p: precios[p][f] for p in pids if f in precios.get(p, {})}
            if previo is not None and len(valores) >= MIN_SERIES_COPIA and valores == previo:
                for p in valores:
                    del precios[p][f]
                quitados += 1
                log.info("%s, %s: copia del día anterior (domingo/feriado), se descarta",
                         INFO_MERCADO[mercado][1], f)
                continue
            previo = valores
    return quitados


def historico_a_disco(precios, productos, consultas, hoy: date, dias: int) -> dict:
    desde = (hoy - timedelta(days=dias - 1)).isoformat()
    fechas = sorted({f for serie in precios.values() for f in serie if f >= desde})
    orden = {m[0]: i for i, m in enumerate(MERCADOS)}
    for f in productos.values():
        rotular(f)
    fichas = sorted(
        (f for f in productos.values() if any(d >= desde for d in precios.get(f["id"], {}))),
        key=lambda f: (orden[f["mercado_codigo"]], normalizar(f["grupo"]), normalizar(f["nombre"])),
    )
    return {
        "version": VERSION_HISTORICO,
        "generado": datetime.now(LIMA_TZ).isoformat(timespec="seconds"),
        "fuente": FUENTE,
        "productos": fichas,
        "fechas": fechas,
        "precios": {f["id"]: [precios[f["id"]].get(d) for d in fechas] for f in fichas},
        "consultas": {m: sorted(d for d in fs if d >= desde) for m, fs in consultas.items()},
    }


# ---------------------------------------------------------------- ticker

def construir_ticker(precios, productos, anterior: dict, hoy: date, min_items: int) -> dict | None:
    """Último precio de cada producto del ticker vs. su dato previo. None si no hay datos suficientes."""
    elegidos = []
    for mercado, variedad, etiqueta, icono in TICKER:
        f = productos.get((mercado, normalizar(variedad)))
        if f is None:
            log.warning("Ticker: %s no aparece en el SISAP", variedad)
        elegidos.append((f["id"] if f else None, etiqueta, icono))
    series = {pid: sorted(precios.get(pid, {}).items(), reverse=True) for pid, _, _ in elegidos if pid}

    # Fecha de referencia: la más reciente con al menos min_items productos del ticker publicados
    conteo = Counter(f for s in series.values() for f, _ in s)
    candidatas = sorted((f for f, n in conteo.items() if n >= min_items), reverse=True)
    if not candidatas:
        return None
    fecha_datos = candidatas[0]
    # Santa Anita (huevos) publica por la tarde: un precio del día anterior con datos se
    # muestra como los demás; solo se marca desactualizado si está más atrás
    fecha_minima = candidatas[1] if len(candidatas) > 1 else fecha_datos

    previos = {it.get("id"): it for it in anterior.get("items", [])}
    items = []
    for pid, etiqueta, icono in elegidos:
        s = [(f, p) for f, p in series.get(pid, []) if f <= fecha_datos] or series.get(pid, [])
        if not s:
            if pid in previos:
                items.append(dict(previos[pid], desactualizado=True))
                log.warning("%s: sin datos, se mantiene el último valor publicado", pid)
            continue
        fecha, precio = s[0]
        precio_ant = s[1][1] if len(s) > 1 else None
        var = round((precio - precio_ant) / precio_ant * 100, 1) if precio_ant else None
        if fecha < fecha_minima:
            log.warning("%s: sin dato el %s, se mantiene el del %s", pid, fecha_datos, fecha)
        items.append({
            "id": pid,
            "nombre": etiqueta,
            "detalle": "",
            "icono": icono,
            "unidad": "kg",
            "precio": round(precio, 2),
            "precio_anterior": round(precio_ant, 2) if precio_ant else None,
            "variacion_pct": var,
            "fecha": fecha,
            "desactualizado": fecha < fecha_minima,
        })

    frescos = sum(not it["desactualizado"] for it in items)
    return {
        "fecha_datos": fecha_datos,
        "es_hoy": fecha_datos == hoy.isoformat(),
        "generado": datetime.now(LIMA_TZ).isoformat(timespec="seconds"),
        "fuente": FUENTE,
        "estado": "completo" if frescos == len(TICKER) else "parcial",
        "items": items,
    }


# ---------------------------------------------------------------- escritura

def escribir_atomico(ruta: Path, data: dict, indent: int | None = 2) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(data, ensure_ascii=False, indent=indent)
    json.loads(texto)  # sanity check
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".tmp_", suffix=".json")
    try:
        # newline="\n": mismo archivo en Windows y en Linux (sin cambios fantasma en git)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto + "\n")
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def sin_cambios(nuevo: dict, anterior: dict) -> bool:
    """Ignora 'generado' para no hacer commits vacíos en cada corrida."""
    def limpio(d):
        return {k: v for k, v in d.items() if k != "generado"}
    return bool(anterior) and limpio(nuevo) == limpio(anterior)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default="data/ticker_precios.json", help="JSON del ticker")
    ap.add_argument("--historico", default="data/historico_precios.json", help="JSON del dashboard")
    ap.add_argument("--dias", type=int, default=HISTORICO_DIAS, help="Ventana del histórico (default 90)")
    ap.add_argument("--fecha", help="Fecha de referencia AAAA-MM-DD (por defecto: hoy en Lima)")
    ap.add_argument("--min-items", type=int, default=5,
                    help="Mínimo de productos del ticker con dato en una fecha para usarla (default 5 de 7)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    hoy = date.fromisoformat(args.fecha) if args.fecha else datetime.now(LIMA_TZ).date()
    ruta_ticker, ruta_hist = Path(args.salida), Path(args.historico)
    ticker_ant, hist_ant = cargar_json(ruta_ticker), cargar_json(ruta_hist)

    precios, productos, consultas = historico_a_memoria(hist_ant)
    try:
        exitosas = actualizar_historico(crear_sesion(), precios, productos, consultas, hoy, args.dias)
    except Exception:
        log.exception("Fallo inesperado consultando SISAP; se conservan los JSON actuales")
        return 0
    if exitosas == 0:
        print("::warning::El SISAP no respondió ninguna consulta. Se conservan los JSON actuales.")
        return 0

    quitar_copias(precios, productos, hoy)
    hist = historico_a_disco(precios, productos, consultas, hoy, args.dias)
    if sin_cambios(hist, hist_ant):
        log.info("Histórico sin cambios")
    else:
        escribir_atomico(ruta_hist, hist, indent=None)
        log.info("Escrito %s (%d productos, %d fechas)", ruta_hist, len(hist["productos"]), len(hist["fechas"]))

    ticker = construir_ticker(precios, productos, ticker_ant, hoy, args.min_items)
    if ticker is None:
        print(f"::warning::Ninguna fecha tiene {args.min_items}+ productos del ticker. Se conserva el ticker actual.")
        return 0
    log.info("Ticker: fecha_datos=%s | es_hoy=%s | estado=%s",
             ticker["fecha_datos"], ticker["es_hoy"], ticker["estado"])
    if sin_cambios(ticker, ticker_ant):
        log.info("Ticker sin cambios; no se reescribe el archivo")
        return 0
    if not ticker["es_hoy"]:
        print(f"::notice::MIDAGRI aún no publica {hoy}; se usa el último día disponible ({ticker['fecha_datos']}).")
    escribir_atomico(ruta_ticker, ticker)
    log.info("Escrito %s", ruta_ticker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
