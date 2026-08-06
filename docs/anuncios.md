# Anuncios & Branding — Manual

Cada anuncio vive en `static/templates/anuncios/` y se monta sobre la misma base que el
hero/checkout (`hero.html`), con todo el branding (cielo, fuentes, colores, átomos) y **sin**
el botón flotante de WhatsApp.

## Cómo funciona

1. Crea el template del anuncio, p.ej. `anuncios/_mi_anuncio.html`:
   - `{% extends "anuncios/base.html" %}`
   - Sobrescribe los bloques SEO/OG **a mano** (title, meta_description, og_title, og_description,
     og_image, og_image_width, og_image_height) — cero Python.
   - Contenido en `{% block lienzo %}` usando los átomos del branding (ver abajo).
2. Registra el slug en `src/pages/router.py` → `ANUNCIOS = {"slug": "anuncios/_x.html"}`.
3. Agrega la URL a `static/sitemap.xml`.
4. Corre tests: `uv run pytest`.

Rutas:
- Página indexable: `GET /anuncios/{slug}`
- Lista de slugs: `GET /api/anuncios`

## Átomos de branding (los mismos del sitio)

- **Colores**: `bg-primal-blue`, `bg-black-mesa`, `text-baroque` (#DDAC23), `text-teal-tree` (#90BDB5),
  `bg-mud-brown`, bordes `border-[#DDAC23]/30`.
- **Tipografía**: títulos `font-heading text-white` con `text-baroque` de acento; eyebrow
  `font-sans text-xs uppercase tracking-[0.2em] text-[#90BDB5]`.
- **Cards**: `bg-[#1F200B]/15 backdrop-blur-[40px] border border-white/10 rounded-3xl relative overflow-hidden`
  + el `<svg>` de `fractal-noise` (mix-blend-overlay opacity-[0.03]) + borde superior dorado
  `h-[2px] bg-gradient-to-r from-transparent via-[#DDAC23]/40 to-transparent`.
- **CTA**: `bg-[#DDAC23] text-[#1F200B] rounded-full` + `cta-arrow` + `animate-pulse-glow`; CTA outline
  `border border-[#DDAC23] text-[#DDAC23]`. Links de WhatsApp → `https://wa.me/5219995050854`.
- **Animaciones**: `hover-glow`, `animate-shimmer`, `photo-stamp-*`.

## Capturar imágenes con DevTools (sin subir PNG al repo)

1. Arranca el server: `uv run uvicorn src.main:app --port 8000`
2. Abre `http://localhost:8000/anuncios/fresco_vs_30dias`
3. DevTools: `Ctrl+Shift+M` (modo dispositivo) o el icono 📱 arriba a la izquierda.
4. Arriba del panel escribe los px exactos del viewport (el diseño es responsive y rellena todo):
   - **1200×630** → og:image / link preview
   - **1080×1350** → IG post retrato
   - **1080×1080** → IG feed cuadrado
   - **1080×1920** → IG stories
5. Captura: menú ⋮ (tres puntos) → "Capture screenshot". Guarda el PNG.
6. Sube la imagen a **Supabase Storage** (bucket `anuncios`, mismo storage de las fotos del hero)
   u otro host. Pega esa URL en `og_image` del template del anuncio.
7. No hace falta commitear ninguna imagen al repo.

## Crear un anuncio nuevo

1. Copia `anuncios/_fresco_vs_30dias.html` → `anuncios/_mi_anuncio.html`.
2. Cambia los bloques SEO/OG y el contenido del `lienzo`.
3. `src/pages/router.py`: añade `"mi_anuncio": "anuncios/_mi_anuncio.html"` a `ANUNCIOS`.
4. `static/sitemap.xml`: añade `<url>` con `https://granjaceballos.com/anuncios/mi_anuncio`.
5. Tests + QA pre-deploy (`uv run pytest`).
