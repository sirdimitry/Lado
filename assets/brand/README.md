# Lado visual identity

A pair of opposing pixel corners: two layouts finding alignment. Flat geometry,
no gradients, no shadows. Source grid: 16 × 16. The menu-bar mark is monochrome
and follows macOS appearance automatically.

| Color | Hex | Use |
| --- | --- | --- |
| Ink | `#182322` | App tile and banner background |
| Ivory | `#F5F1E8` | Light mark and text |
| Orange | `#F06436` | Accent corner |

- `logo.svg` / `logo.png`: transparent mark for light backgrounds.
- `logo-light.svg` / `logo-light.png`: transparent mark for dark backgrounds.
- `icon.svg` / `icon.png`: macOS app tile, 1024 × 1024.
- `Lado.icns`: multi-resolution macOS icon.
- `github-banner.svg` / `github-banner.png`: 1280 × 640 GitHub/README banner.

Editable SVG geometry is the final source of truth. Rebuild raster assets with
`python scripts/build_brand.py` on macOS (Pillow required). PNG text uses system
Arial/Andale Mono; SVG keeps editable text with fallback fonts.

## Design provenance

An initial concept was explored using the built-in image generation tool. The
production mark was then authored on an exact SVG pixel grid to enforce flat
colors, consistent edges and small-size legibility. No generated raster is
required to build the application.

Concept prompt:

> Minimalist pixel-art mark for Lado, an offline RU/EN keyboard layout companion.
> Two interlocking stepped L-shaped glyphs suggesting two writing directions
> finding alignment. Orange #F06436, ivory #F5F1E8, ink #182322. Transparent
> background. No text, gradients, shadows, texture or 3D. Legible at 16 pixels.

Refinement prompt: preserve the silhouette; flatten every surface to the three
solid brand colors and align all edges to a coherent square grid.
