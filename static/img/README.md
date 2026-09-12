# Brand assets

Sources live in `assets-src/` (the originals the owner supplied). The files here
are the web-ready derivatives; regenerate them from source rather than editing
these by hand.

| File | Used for |
|---|---|
| `logo-wordmark-on-light.png` | Header/footer logo on light surfaces |
| `logo-wordmark-on-dark.png` | Header/footer logo on dark surfaces, and email headers |
| `logo-mark-on-light.png` | Icon-only mark on light surfaces |
| `logo-mark-on-dark.png` | Icon-only mark on dark surfaces |
| `logo.png` | Organization JSON-LD |
| `favicon.ico`, `favicon-32.png` | Browser tab |
| `apple-touch-icon.png` | iOS home screen |
| `icon-192.png`, `icon-512.png` | PWA manifest |
| `og-image.png` | Link previews (1200x630) |

The two wordmark files are a matched pair: the artwork was drawn twice, once for
a light background and once for a dark one, so the header swaps between them with
the theme via `.logo-on-light` / `.logo-on-dark` in `app.css`. Do not recolour one
to serve both.

Backgrounds were keyed out of the supplied JPGs by flood-filling from the image
border, so colours that also appear inside the artwork survive. If you replace a
source file, rerun that step rather than using a plain colour-distance key.

## Flags
`static/vendor/flags/` holds the flag-icons SVG set (MIT, licence included).
Never use emoji flags: Windows has no regional-indicator font, so they render as
bare letters. Use `{% flag country.iso2 %}`.

## Video
`static/video/hero.mp4` / `.webm` is the brand film, re-encoded muted at CRF 30
from `assets-src/second-ver.mp4`. `hero-poster.jpg` is the still shown before it
loads.
