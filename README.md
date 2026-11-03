# Ticker de precios mayoristas · El Comercio

Tira de precios para la portada (7 alimentos) y dashboard con todos los productos del SISAP (MIDAGRI), actualizados solos cada mañana.

**Direcciones públicas (GitHub Pages):**
- Datos del ticker: https://fabmonge.github.io/precios-mayoristas/data/ticker_precios.json
- Datos del dashboard: https://fabmonge.github.io/precios-mayoristas/data/historico_precios.json
- Demo del ticker: https://fabmonge.github.io/precios-mayoristas/frontend/demo.html
- Demo del dashboard: https://fabmonge.github.io/precios-mayoristas/frontend/demo-dashboard.html

Pendiente: cuando la nota esté publicada, poner su link en `data-href` de `frontend/ticker-precios.html`.

```
scripts/actualizar_precios.py          extractor (Python 3.10+)
scripts/requirements.txt
data/ticker_precios.json               7 productos del ticker: último precio + variación
data/historico_precios.json            todos los productos, serie diaria de 90 días (dashboard, ~200 KB)
.github/workflows/actualizar_precios.yml   cron 7/8/9 a.m. Lima
frontend/ticker-precios.html           snippet del ticker para Arc (Custom HTML / HTML Box)
frontend/dashboard-precios.html        snippet del dashboard para Arc
frontend/demo.html                     demo local del ticker
frontend/demo-dashboard.html           demo local de ticker + dashboard
```

## Productos

- **Dashboard: todos los productos.** Cada corrida descarga el catálogo completo de 6 mercados (`MERCADOS` en el script): Gran Mercado Mayorista, Frutas N° 2, Aves, Santa Anita, Cereales y Plátanos. Son unas 230 variedades. Si el Midagri agrega un producto, aparece solo. El Mercado Modelo de Frutas no publica precios y no se incluye.
- **Variedades repetidas:** si una variedad se vende en varios mercados, la del de mayor prioridad es la "principal" y las demás llevan el mercado en el nombre ("Quinua blanca · Mercado de Cereales"). El ranking usa solo las principales.
- **Ticker (7, con silueta):** papa amarilla, papa blanca, cebolla roja, limón (cajón), palta fuerte, pollo vivo y choclo. Se definen en `TICKER`, con la silueta en el campo `icono` del JSON.
- **Canasta (15 productos básicos, `CANASTA`):** solo sirve para ordenar las sugerencias del buscador (aparecen primero). El índice usa todos los productos.
- **Nombres:** el SISAP escribe sin tildes y En Mayúsculas. El script corrige tildes (`TILDES`), pasa a mayúscula inicial y respeta nombres propios y marcas (`PROPIOS`, `FRASES`). Los cambios se aplican también al histórico en la siguiente corrida.
- **Unidad:** por kilo, salvo aceite y leche (por litro, `POR_LITRO`).
- Las siluetas son SVG en línea dentro de `ticker-precios.html` (objeto `ICONOS`). El color se cambia con `--ec-icon`.
- **Domingos y feriados:** el Gran Mercado Mayorista no opera y el SISAP repite los precios del día anterior. El script detecta esas copias (todas las variedades de un mercado idénticas al día previo) y las descarta, así el ticker no muestra "0.0%" en todo. Aves y Frutas sí operan los domingos, así que sus datos se conservan.

## Dashboard

Un clic en cualquier parte del ticker lleva a `data-href`: el link de la nota con `#precios-mayoristas` al final, que es el ancla del inicio del dashboard. Así el lector llega siempre al comienzo del dashboard, aunque la nota tenga texto antes. El dashboard también acepta `?producto=<id>` para abrir un producto, pero el ticker ya no lo usa.

- **Selector de periodo (Día / Semana / Mes), Semana por defecto.** Día = último precio vs. el día anterior. Semana y Mes = promedio de los últimos 7 (o 30) días vs. el de los 7 (o 30) previos. Con promedios, un día atípico no dispara la variación.
- **Los que más subieron y bajaron:** entre todos los productos, las 4 mayores bajadas y las 8 mayores subidas (`RANKING_TOTAL`, `RANKING_BAJADAS`). Los productos con pocos días de precio en el periodo quedan fuera.
- **¿Subieron los precios?** Número destacado + índice general de todos los productos a 90 días (base 100 el primer día), con la ventana del periodo sombreada. Es un índice encadenado: cada día se toma la media geométrica de la variación de los productos con precio ese día y el anterior, así un producto que aparece o desaparece no lo mueve. Se excluyen los días con menos de la mitad de los productos habituales (domingos y feriados).
- **¿Caro o barato para lo que suele costar?** Los mismos productos del ranking, con su precio de hoy dentro del rango mínimo–máximo de 90 días y su promedio.
- **Busca un producto:** un solo control. Al escribir aparecen sugerencias (ignora tildes y mayúsculas, se maneja con teclado); al entrar al campo o tocar la flecha se ve la lista completa agrupada por tipo de producto. Muestra una frase en lenguaje simple y una línea con el día más barato, el más caro y hoy.
- Las barras y filas de los gráficos son clicables y llevan al detalle del producto.
- D3 7.9.0 se carga desde cdnjs (si Arc ya tiene `window.d3`, la reutiliza).
- Estilo ECData: fondo blanco, Georgia, paleta de rojos y grises cálidos, nota de fuente bajo cada gráfico.
- El histórico se llena solo: la primera corrida descarga 90 días de los 6 mercados (~540 consultas, 3–4 min). Después, cada corrida pide solo los 3 últimos días (~24 consultas, unos segundos).

## Fuente de datos (verificada el 23/10/2026)

| | |
|---|---|
| Endpoint | `POST http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/resumenes/filtrar` |
| Body (form-urlencoded) | `mercado=15011501` · `variables[]=precio_prom` · `fecha=22/10/2026` · `periodicidad=dia` · `productos[]=0611` (repetible) · `__ajax_carga_final=consulta` |
| Respuesta | Fragmento HTML (latin-1): `<tr class=contenido>` → Producto (rowspan) · Variedad · Precio S/ x kg |
| Sin datos | `<p class=mensajeDeError>No existen resultados…` |
| Catálogo de productos por mercado | `POST …/mayorista/generos/filtrarPorMercado` con `mercado=<código>` |

No requiere cookies, token ni CSRF.

Mercados: `15011501` Gran Mercado Mayorista de Lima · `15010106` Aves vivas (Pollo = `1301`) · `15011502` Mayorista N°2 de Frutas.

### Cómo encontrar la ruta tú mismo (DevTools)

1. Abre `http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/` (el enlace "MERCADOS" del portal).
2. Abre DevTools (F12) → pestaña **Network** → filtro **Fetch/XHR** → activa *Preserve log*.
3. Elige un mercado: verás `generos/filtrarPorMercado` (la lista de productos).
4. Marca productos, deja "Precio Promedio", periodicidad diaria y pulsa **Consultar**.
5. Aparece `resumenes/filtrar` (POST). En **Payload** están los campos; en **Response**, la tabla HTML.
6. Clic derecho → *Copy → Copy as cURL (bash)* para reproducirlo en la terminal.

El portal es jQuery con un bundle minificado (`/mayorista/js~…`). Si algún día cambian la ruta, búscala en **Sources** o con Ctrl+Shift+F buscando `url:'http://sistemas.midagri.gob.pe`.

## Resiliencia

- Reintentos HTTP: 3, con backoff de 5/10/20 s ante timeouts o errores 5xx. Timeout de lectura de 35 s, el mismo que usa el portal.
- Si a las 7 a.m. aún no está el día de hoy, usa la última fecha publicada y la compara con la fecha previa con datos. Busca hasta 10 días atrás, lo que cubre domingos y feriados.
- Circuit breaker: tras 3 fallos de red seguidos aborta y no escribe nada (~2 min).
- Si cae un producto o un mercado, se conserva el último valor de ese producto con `"desactualizado": true`. El ticker lo muestra atenuado.
- Si hay menos de 8 productos frescos (`--min-items`), no sobrescribe el JSON.
- La escritura es atómica (archivo temporal + `os.replace`). Si el contenido no cambió, no reescribe el archivo, así que no hay commits vacíos.
- Siempre sale con código 0, para que el workflow no falle en rojo por culpa del MIDAGRI. Los avisos aparecen como anotaciones `::warning::` en Actions.

Prueba local:

```bash
pip install -r scripts/requirements.txt
python scripts/actualizar_precios.py --salida data/ticker_precios.json
python scripts/actualizar_precios.py --fecha 2026-10-15   # reprocesar un día pasado
```

Para cambiar la canasta, edita `CANASTA` en el script. La variedad debe coincidir con el texto de la columna "Variedad" del SISAP; tildes y mayúsculas dan igual.

## Automatización (GitHub Actions)

- Cron `7 12,13,14 * * *` UTC = 7:07, 8:07 y 9:07 a.m. en Lima. Perú no tiene horario de verano, así que no hay que ajustarlo.
- El workflow hace commit de `data/ticker_precios.json` solo si cambió. Opcionalmente lo sube a S3 e invalida CloudFront: define `vars.S3_BUCKET`, `vars.AWS_REGION`, `secrets.AWS_ROLE_ARN` y, si usas CloudFront, `vars.CLOUDFRONT_ID`.
- Para probarlo: Actions → *Actualizar precios mayoristas* → **Run workflow**.

Advertencias:
- GitHub puede retrasar los crons entre 5 y 30 min en horas punta.
- GitHub desactiva los crons de repos sin actividad en 60 días. Los commits diarios del bot cuentan como actividad.
- **IP extranjera (confirmado el 3/11/2026):** el SISAP bloquea las conexiones desde fuera del Perú, y los servidores de GitHub están en EE. UU.: el workflow termina sin datos nuevos (no rompe nada). Por eso la actualización real corre desde el Perú con `scripts/actualizar_y_publicar.cmd` (Windows) o `.sh` (Linux):
  - **Hoy:** tarea programada "Precios mayoristas El Comercio" en la PC de Fabrizio (7, 8 y 9 a.m.; si la PC estaba apagada, corre al prenderla). Registro en `%USERPROFILE%\PreciosMayoristas\actualizar.log`; Python en `%USERPROFILE%\PreciosMayoristas\venv`.
  - **Definitivo:** un servidor del diario en el Perú. Ver `PARA_TECNOLOGIA.md`.

## Publicar el JSON

Opción A, **GitHub Pages** (lo más simple): Settings → Pages → *Deploy from branch* `main` / root. La URL queda así: `https://<usuario>.github.io/<repo>/data/ticker_precios.json`. Pages envía `Access-Control-Allow-Origin: *` y `max-age=600`.

Opción B, **S3 + CloudFront**: añade CORS al bucket:

```json
[{ "AllowedOrigins": ["https://elcomercio.pe", "https://*.elcomercio.pe"], "AllowedMethods": ["GET"], "AllowedHeaders": ["*"], "MaxAgeSeconds": 3600 }]
```

y en CloudFront, incluye el *query string* `v` en la clave de caché.

No uses `raw.githubusercontent.com` en producción: no tiene SLA y tiene límite de peticiones.

## Frontend (Arc Publishing)

1. Copia `frontend/ticker-precios.html` completo en un bloque **Custom HTML** (Composer) o **HTML Box** (PageBuilder).
2. Cambia `data-src` por la URL pública del JSON.
3. Listo:
   - Cache-busting `?v=AAAAMMDD-HH` (hora de Lima). Cambia cada día y también entre la corrida de 7 y la de 9.
   - Fecha en la esquina: "Precios mayoristas al 22 oct".
   - Bucle infinito sin saltos (contenido duplicado, de 0 a −50%).
   - Pausa al pasar el mouse.
   - Respeta `prefers-reduced-motion`.
   - Si el fetch falla, la tira queda oculta y no rompe la página.
- Colores en variables CSS (`--ec-sube`, `--ec-baja`, `--ec-label-bg`…). Por defecto ▲ es rojo (el alimento se encarece) y ▼ es verde. Para la convención bursátil, intercambia los dos colores.
- Velocidad: `--ec-speed` (px/s).
