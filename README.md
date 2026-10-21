# Mostic

Sitio estático educativo de Mostic (orientaciones, actividades y juegos propios).

## Estructura

- `index.html` — página principal
- `assets/img/` — imágenes
- `assets/pdf/` — PDFs descargables
- `games/` — minijuegos HTML
- `scripts/extract_assets.py` — regenera assets si vuelves a partir de un HTML monolítico con base64

## Cómo abrir el sitio

Las descargas (PDF/PNG) y los juegos en iframe usan `fetch` / rutas relativas, así que **no abras `index.html` con `file://`**.

Desde esta carpeta:

```bash
# Python
python -m http.server 8080

# o Node
npx --yes serve -l 8080
```

Luego visita `http://localhost:8080`.

## Regenerar assets

Si tienes de nuevo un HTML único con todo embebido en base64:

1. Colócalo como `Mostic_COMPLETA_CONOCENOS.html` en la raíz del repo.
2. Ejecuta `python scripts/extract_assets.py`.
3. Se generará `index.html` liviano y las carpetas `assets/` y `games/`.
