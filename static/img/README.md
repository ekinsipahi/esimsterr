# Brand assets

The files here are generated placeholders so the site renders (and
`collectstatic` succeeds) before real artwork exists. Replace them with your own,
keeping the exact filenames — nothing in the templates needs to change:

| File | Size | Where it shows |
|---|---|---|
| `favicon.ico` | 16/32/48 | Browser tab (legacy) |
| `favicon-32.png` | 32×32 | Browser tab |
| `apple-touch-icon.png` | 180×180 | iOS home screen |
| `icon-192.png` | 192×192 | PWA / Android |
| `icon-512.png` | 512×512 | PWA splash |
| `logo.png` | 256×256 | Organization JSON-LD, emails |
| `og-image.png` | 1200×630 | Link previews on social and chat |

To use a wordmark in the header instead of the generated "e" tile, replace the
`<span class="brand-mark">` block in `templates/partials/header.html` with:

```html
<img src="{% static 'img/logo.png' %}" alt="eSIMsterr">
```
