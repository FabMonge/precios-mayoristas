# Observatorio de precios de alimentos

Ticker y dashboard de precios mayoristas de Lima, con datos del Midagri. Proyecto de ECData y Economía de El Comercio.

- Ticker: va en las portadas de Economía y ECData. Muestra 12 productos y al hacer clic lleva a la nota.
- Dashboard: va en una nota especial en Arc. Tiene todos los productos del SISAP (unos 230) con 90 días de historia.

Vista previa: https://fabmonge.github.io/precios-mayoristas/frontend/demo-dashboard.html

## Archivos

- `scripts/actualizar_precios.py`: descarga los precios y genera los dos JSON.
- `scripts/actualizar_y_publicar.sh` y `.cmd`: corren el script y suben los datos (Linux y Windows).
- `data/ticker_precios.json`: datos del ticker.
- `data/historico_precios.json`: datos del dashboard.
- `frontend/ticker-precios.html`: código del ticker para pegar en Arc.
- `frontend/dashboard-precios.html`: código del dashboard para pegar en Arc.

## De dónde salen los datos

Del SISAP del Midagri, de seis mercados: Gran Mercado Mayorista, Frutas N° 2, Aves, Santa Anita, Cereales y Plátanos. El precio del pollo al consumidor sale del boletín diario de aves del Midagri, en PDF.

El SISAP bloquea conexiones desde fuera del Perú, así que el script tiene que correr desde una conexión peruana.

## Actualización

El script corre 4 veces al día: 9 a.m., 12 p.m., 3 p.m. y 7 p.m. Por ahora lo hace desde mi computadora; la idea es pasarlo a un servidor del diario.

Para correrlo a mano:

```bash
pip install -r scripts/requirements.txt
python scripts/actualizar_precios.py
```

Si el Midagri no responde o no hay datos nuevos, el script no toca los JSON. El ticker y el dashboard siguen mostrando los últimos precios.

## En Arc

Se pega el contenido de cada archivo de `frontend/` en un bloque HTML. El ticker y el dashboard leen los JSON cada vez que alguien abre la página, así que se actualizan solos sin volver a publicar.

En el ticker, `data-href` tiene que apuntar a la nota publicada, con `#precios-mayoristas` al final. Si los JSON cambian de dirección, hay que actualizar `data-src` en los dos archivos.
