# Pase a Tecnología: Observatorio de precios de alimentos

Ticker de precios para la portada de elcomercio.pe y dashboard para una nota en Arc. Los datos son públicos, del Midagri, y se actualizan solos 4 veces al día.

Repositorio: https://github.com/FabMonge/precios-mayoristas

## Cómo funciona

```
Midagri (SISAP + boletín de aves)  →  script en Python (4 veces al día)  →  2 archivos JSON  →  ticker y dashboard
```

1. `scripts/actualizar_precios.py` descarga los precios mayoristas de 6 mercados de Lima desde el SISAP. También lee del boletín diario de aves en PDF el precio del pollo al consumidor.
2. Genera dos JSON:
   - `data/ticker_precios.json` (unos 3 KB): los 12 productos del ticker.
   - `data/historico_precios.json` (unos 200 KB): 90 días de todos los productos, para el dashboard.
3. `scripts/actualizar_y_publicar.sh` corre el script y, solo si los datos cambiaron, hace commit y push al repositorio.
4. GitHub Pages publica los JSON, y el ticker y el dashboard los leen desde el navegador:
   - https://fabmonge.github.io/precios-mayoristas/data/ticker_precios.json
   - https://fabmonge.github.io/precios-mayoristas/data/historico_precios.json

Hoy el script corre en la PC de Fabrizio Monge con el Programador de tareas de Windows. Es una solución temporal: si la PC está apagada, los precios no se actualizan.

## Por qué tiene que correr en un servidor en el Perú

**El SISAP (`sistemas.midagri.gob.pe`) bloquea las conexiones desde fuera del Perú.** Desde GitHub Actions, cuyos servidores están en EE. UU., todas las consultas terminan en timeout. Desde una conexión peruana responden en menos de un segundo. Por eso no sirve un servicio en la nube con IP extranjera.

## Lo que se necesita

**Una máquina Linux en el Perú, siempre encendida**, con:

- Python 3.10 o superior y git.
- Salida a internet hacia:
  - `sistemas.midagri.gob.pe`: HTTP, puerto 80 (SISAP).
  - `siea.midagri.gob.pe`: HTTPS, puerto 443 (boletín de aves en PDF).
  - `github.com`: HTTPS, puerto 443, o el destino donde se publiquen los JSON (ver la decisión más abajo).
- Unos 100 MB en disco para el entorno de Python. El script corre de 10 a 60 segundos, 4 veces al día.

**No hace falta** base de datos, servicio permanente, claves de APIs ni costo: el script corre, escribe dos archivos y termina.

## Pasos de instalación (unos 15 minutos)

1. **Clonar el repositorio** con una *deploy key* de escritura. Esa clave da acceso solo a este repositorio, no a una cuenta:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/precios_mayoristas -N "" -C "servidor precios mayoristas"
   # Enviar ~/.ssh/precios_mayoristas.pub a Fabrizio para que la agregue en
   # GitHub → Settings → Deploy keys → Add deploy key (marcar "Allow write access")
   GIT_SSH_COMMAND="ssh -i ~/.ssh/precios_mayoristas" git clone git@github.com:FabMonge/precios-mayoristas.git
   cd precios-mayoristas
   git config core.sshCommand "ssh -i ~/.ssh/precios_mayoristas"
   git config user.name "Servidor El Comercio" && git config user.email "<correo técnico>"
   ```
2. **Instalar las dependencias**: `requests`, `beautifulsoup4` y `pdfplumber`, este último para leer el PDF:
   ```bash
   python3 -m venv venv && venv/bin/pip install -r scripts/requirements.txt
   ```
3. **Probar una vez.** La primera corrida puede tardar un par de minutos si tiene que completar días faltantes:
   ```bash
   sh scripts/actualizar_y_publicar.sh
   ```
   Debe terminar con "Publicado en GitHub" o "Sin cambios en los datos".
4. **Programarlo con cron** a las 9 a.m., 12 p.m., 3 p.m. y 7 p.m., hora de Lima. Si el servidor está en UTC, usar `0 14,17,20,0 * * *`:
   ```cron
   0 9,12,15,19 * * *  /ruta/a/precios-mayoristas/scripts/actualizar_y_publicar.sh >> /var/log/precios-mayoristas.log 2>&1
   ```
5. **Avisar a Fabrizio** cuando haya corrido bien un día completo, para desactivar la tarea de su PC. Si las dos máquinas publican a la vez, no se rompe nada, pero se duplican commits.

## Decisión pendiente: dónde se publican los JSON

Hoy los JSON salen desde el GitHub personal de Fabrizio. Funciona, pero la portada del diario dependería de una cuenta personal. Hay dos caminos:

- **A. Pasar el repositorio a la organización de GitHub del diario** y seguir con GitHub Pages. Es el cambio más chico: los pasos de arriba siguen igual, solo cambia la dirección del repositorio.
- **B. Publicar los JSON en el CDN o S3 del diario.** En vez del `git push`, el script copia los dos archivos al bucket. El workflow `.github/workflows/actualizar_precios.yml` ya trae un ejemplo del paso para S3.

En cualquiera de los dos casos, si cambia la dirección de los JSON, hay que actualizar el atributo `data-src` en los dos fragmentos de HTML del ticker y del dashboard. Es una línea en cada uno.

Requisitos para la dirección pública de los JSON: CORS abierto (`Access-Control-Allow-Origin: *`) y caché corta, de unos 10 minutos como máximo. GitHub Pages ya cumple las dos cosas.

## Fragmentos de HTML (para portada y Arc)

| Archivo | Dónde va | Qué cambiar |
|---|---|---|
| `frontend/ticker-precios.html` | Portada de elcomercio.pe, como bloque HTML | `data-href`: hoy dice `https://elcomercio.pe/URL-DE-LA-NOTA/#precios-mayoristas`. **Hay que poner la URL real de la nota**, con `#precios-mayoristas` al final. |
| `frontend/dashboard-precios.html` | Nota en Arc, como bloque HTML | Nada, salvo `data-src` si se mueven los JSON. |

Los dos fragmentos son autocontenidos: estilos y código van dentro, con las clases encapsuladas para no chocar con el sitio. El dashboard carga D3 7.9.0 desde cdnjs. Vista previa con datos reales: https://fabmonge.github.io/precios-mayoristas/frontend/demo-dashboard.html

## Si algo falla

El script está pensado para nunca romper lo publicado:

- Si el SISAP no responde, reintenta. Tras 3 fallos seguidos deja de consultar y **conserva los JSON actuales**: el ticker sigue mostrando el último precio válido.
- Si un producto del ticker no tiene dato del día, conserva su último precio y lo marca como desactualizado.
- Si el Midagri cambia el formato del boletín de aves, el pollo al consumidor conserva sus precios guardados y el registro muestra una advertencia. El resto sigue igual.
- Los JSON se escriben de forma atómica: nunca queda un archivo a medias.

Qué revisar en el registro (`/var/log/precios-mayoristas.log`): líneas `WARNING` o `ERROR`. Una advertencia aislada, como un día sin boletín, es normal. Si se repite varios días, conviene avisar a ECData.

## Otros detalles

- **Horarios de publicación del Midagri:** el Gran Mercado Mayorista publica temprano, Santa Anita (huevos) hacia las 5–6 p.m. y el boletín de aves por la tarde. Por eso hay corridas a las 3 p.m. y 7 p.m.
- **Domingos y feriados:** el SISAP repite los precios del día anterior. El script detecta esas copias y las descarta.
- **GitHub Actions:** el workflow del repositorio sigue programado, pero no logra conectarse al SISAP por el bloqueo y no cambia nada. Se puede desactivar en GitHub → Actions cuando el servidor esté funcionando.
- **Contacto:** Fabrizio Monge (ECData).
