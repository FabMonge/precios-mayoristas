# Pedido a Tecnología: actualización diaria desde un servidor en el Perú

## Contexto

El ticker de la home y el dashboard de la nota leen dos archivos JSON publicados en GitHub Pages:

- https://fabmonge.github.io/precios-mayoristas/data/ticker_precios.json
- https://fabmonge.github.io/precios-mayoristas/data/historico_precios.json

Un script en Python los regenera cada mañana con los precios del SISAP del Midagri. **El SISAP (`sistemas.midagri.gob.pe`) bloquea las conexiones desde fuera del Perú**: desde GitHub Actions (servidores en EE. UU.) todas las consultas terminan en timeout, y desde una conexión peruana responden en menos de un segundo. Hoy el script corre en la PC de Fabrizio Monge como solución temporal, y depende de que esa PC esté encendida.

## Lo que necesitamos

Correr el script **3 veces al día (7, 8 y 9 a.m., hora de Lima) desde una máquina en el Perú** que esté siempre encendida y tenga salida a internet hacia:

- `sistemas.midagri.gob.pe` (HTTP, puerto 80)
- `github.com` (HTTPS)

### Pasos (Linux, unos 15 minutos)

1. **Clonar el repositorio** con una *deploy key* de escritura (da acceso solo a este repositorio, no a una cuenta):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/precios_mayoristas -N "" -C "servidor precios mayoristas"
   # Enviar ~/.ssh/precios_mayoristas.pub a Fabrizio para que la agregue en
   # GitHub → Settings → Deploy keys → Add deploy key (marcar "Allow write access")
   GIT_SSH_COMMAND="ssh -i ~/.ssh/precios_mayoristas" git clone git@github.com:FabMonge/precios-mayoristas.git
   cd precios-mayoristas
   git config core.sshCommand "ssh -i ~/.ssh/precios_mayoristas"
   git config user.name "Servidor El Comercio" && git config user.email "<correo técnico>"
   ```
2. **Instalar Python 3.10+ y las dependencias** (`requests`, `beautifulsoup4`):
   ```bash
   python3 -m venv venv && venv/bin/pip install -r scripts/requirements.txt
   ```
3. **Probar una vez** (tarda unos segundos; si es la primera vez en el día puede tardar más):
   ```bash
   sh scripts/actualizar_y_publicar.sh
   ```
4. **Programarlo con cron** (servidor en hora de Lima; si está en UTC, usar `0 12,13,14 * * *`):
   ```cron
   0 7,8,9 * * *  /ruta/a/precios-mayoristas/scripts/actualizar_y_publicar.sh >> /var/log/precios-mayoristas.log 2>&1
   ```

Con eso, la tarea de la PC de Fabrizio se puede desactivar.

### Alternativa: runner de GitHub

También se puede instalar un *self-hosted runner* de GitHub en esa máquina y cambiar `runs-on: ubuntu-latest` por `runs-on: self-hosted` en `.github/workflows/actualizar_precios.yml`. GitHub **no recomienda runners propios en repositorios públicos**, porque código de terceros podría ejecutarse en la máquina. Si se prefiere esta vía, conviene mover antes el repositorio a la organización del diario como privado y publicar los JSON en el CDN o S3 del diario (el workflow ya trae el paso para S3).

## Qué no se necesita

- No hay base de datos ni servicio que mantener: es un script que corre unos segundos y termina.
- No hay claves de APIs: el SISAP es público.
- El costo es nulo: unos 200 KB de datos al día.
