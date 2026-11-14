# Observatorio de precios de alimentos: pase a Tecnología

Desde ECData y Economía preparamos el **Observatorio de precios de alimentos**, que tiene dos piezas:

- **Un ticker de precios** para las portadas de las secciones Economía y ECData.
- **Un dashboard** que se publica como nota especial en Arc.

Los datos son los precios mayoristas diarios del Midagri. El desarrollo está terminado; lo que necesito de ustedes es un lugar donde el proceso de actualización corra solo, todos los días.

Repositorio con todo el código: https://github.com/FabMonge/precios-mayoristas
Vista previa con datos reales: https://fabmonge.github.io/precios-mayoristas/frontend/demo-dashboard.html

## Cómo funciona

```
Midagri  →  script de actualización (4 veces al día)  →  2 archivos de datos (JSON)  →  ticker y nota
```

1. El script `scripts/actualizar_precios.py` descarga los precios de 6 mercados mayoristas de Lima desde el sistema del Midagri (SISAP). Del boletín diario de aves, en PDF, toma el precio del pollo al consumidor.
2. Con eso genera dos archivos:
   - `data/ticker_precios.json` (unos 4 KB): los 12 productos del ticker.
   - `data/historico_precios.json` (unos 200 KB): 90 días de todos los productos, para el dashboard.
3. El ticker y la nota no llevan los precios adentro: cada vez que alguien los abre, el navegador descarga esos dos archivos. Por eso la nota se publica una sola vez en Arc y se mantiene al día sin volver a editarla.

Hoy el script corre en mi computadora como solución temporal y publica los archivos en mi cuenta de GitHub. Si la computadora está apagada, los precios no se actualizan.

## Lo que necesito

### 1. Que el script corra en uno de sus servidores en el Perú

- **Tiene que estar en el Perú.** El SISAP bloquea las conexiones desde el extranjero; desde servidores en la nube fuera del país, todas las consultas se quedan sin respuesta.
- **Horario:** 9 a.m., 12 p.m., 3 p.m. y 7 p.m., hora de Lima. Hay corridas por la tarde porque algunos mercados y el boletín de aves publican después del mediodía.
- **Es liviano:** cada corrida dura menos de un minuto. No usa base de datos, servicio permanente ni claves de APIs.
- **Requisitos:** Python 3.10 o superior, en Linux o Windows. El repositorio trae un lanzador para cada uno: `scripts/actualizar_y_publicar.sh` y `scripts/actualizar_y_publicar.cmd`.
- **Acceso a internet hacia:**
  - `sistemas.midagri.gob.pe` (HTTP, puerto 80)
  - `siea.midagri.gob.pe` (HTTPS, puerto 443)
  - el destino donde se publiquen los datos (punto 2)

### 2. Un espacio del diario para publicar los dos archivos de datos

Prefiero que los datos no dependan de mi cuenta personal de GitHub, sino de un espacio de El Comercio: el CDN, un bucket o el servidor donde suelen alojarse los especiales. En cada corrida, el servidor sube ahí los dos JSON, y el ticker y la nota los leen desde esa dirección.

Lo que necesita esa dirección:

- **Pública y con HTTPS.**
- **CORS abierto** (`Access-Control-Allow-Origin: *`), para que las páginas de elcomercio.pe puedan leer los archivos.
- **Caché corta**, de unos 10 minutos como máximo. Si no, los lectores verían precios viejos después de cada actualización.

Cuando tengan la dirección final, me la pasan y la cambio en el ticker y en la nota. Es una línea en cada uno, el atributo `data-src`.

Mientras ese espacio no esté listo, el servidor puede seguir publicando en GitHub, como hoy.

## Instalación

1. **Copiar el repositorio** en el servidor. Es público, así que se puede clonar sin credenciales:
   ```bash
   git clone https://github.com/FabMonge/precios-mayoristas.git
   ```
2. **Instalar las dependencias de Python** (`requests`, `beautifulsoup4` y `pdfplumber`):
   ```bash
   python3 -m venv venv && venv/bin/pip install -r scripts/requirements.txt
   ```
3. **Probar una corrida.** La primera puede tardar un par de minutos si tiene que completar días faltantes:
   ```bash
   venv/bin/python scripts/actualizar_precios.py
   ```
   Deja los archivos actualizados en `data/`.
4. **Publicar los archivos.** Después de cada corrida, subir `data/ticker_precios.json` y `data/historico_precios.json` al espacio del punto 2, con el método que usen para su CDN. Si mientras tanto se sigue publicando en GitHub, el lanzador `scripts/actualizar_y_publicar.sh` hace la corrida y el envío juntos. Para eso hace falta permiso de escritura en el repositorio: me envían una *deploy key*, una clave que da acceso solo a este repositorio, y yo la autorizo.
5. **Dejarlo programado** en los cuatro horarios. Por ejemplo, con cron en un servidor en hora de Lima:
   ```cron
   0 9,12,15,19 * * *  /ruta/a/precios-mayoristas/scripts/actualizar_y_publicar.sh >> /var/log/precios-mayoristas.log 2>&1
   ```
   Si el servidor está en UTC: `0 14,17,20,0 * * *`.

Cuando haya funcionado bien un día completo, avísenme y desactivo la tarea de mi computadora.

## Si algo falla

El script está hecho para no romper nunca lo publicado:

- **Si el Midagri no responde:** reintenta. Tras 3 fallos seguidos deja de consultar y conserva los archivos actuales, así que el ticker y la nota siguen mostrando los últimos precios válidos.
- **Si un producto del ticker no tiene dato del día:** conserva su último precio y lo marca como desactualizado.
- **Si el Midagri cambia el formato del boletín de aves:** el pollo al consumidor mantiene sus precios guardados y el resto sigue igual.
- **Escritura segura:** los archivos se escriben de forma atómica, así que nunca queda uno a medias.
- **En el registro:** las líneas `WARNING` o `ERROR` son las que importan. Una advertencia aislada es normal, por ejemplo un día sin boletín. Si se repite varios días, avísenme.

## Otros detalles

- **Domingos y feriados:** el SISAP repite los precios del día anterior. El script detecta esas copias y las descarta.
- **GitHub Actions:** el repositorio tiene un flujo de GitHub Actions programado que no logra conectarse al SISAP por el bloqueo, así que no cambia nada. Lo desactivo cuando el servidor esté funcionando.
