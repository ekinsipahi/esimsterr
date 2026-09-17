#!/usr/bin/env python3
"""Draw each region as the place it actually is.

Regions were all one globe -- on the website a stack of identical "layers"
glyphs, in the app the same Material world icon nine times over. Nine tiles
saying "somewhere on Earth" tell a customer nothing, and the one thing they are
deciding between is *where*.

So each region gets its own outline, drawn from real coastlines: Natural Earth's
110m country geometry, which is public domain. The shapes are the region as a
place, not as a list of the countries we happen to sell in it -- Latin America
that is missing Brazil because no plan covers it would be a worse picture than
the globe was.

Two outputs from the same path data, because the two surfaces want different
wrappers and must not drift apart:

  * static/img/regions/<slug>.svg          for the website
  * app/src/main/res/drawable/region_<slug>.xml  for the app, as a vector
    drawable that takes the theme's tint like any other icon

Run it when a region is added; commit what it writes. The 24 MB source file is
not committed -- it is fetched on demand and thrown away.

    python3 tools/build_region_maps.py
"""
from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path

SOURCE = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "master/geojson/ne_110m_admin_0_countries.geojson")

# The region as a place. Deliberately not the country lists in the database:
# those are what the provider sells today, and a map with holes in it where we
# happen not to have a plan is a map of our inventory, not of anywhere.
#
# "*" means every country -- the whole world, which is what Global is.
REGIONS: dict[str, list[str] | str] = {
    "global": "*",  # minus EXCLUDE_FROM_WORLD, below
    "europe": ("AL AD AT BY BE BA BG HR CY CZ DK EE FI FR DE GR HU IS IE IT XK LV LI LT "
               "LU MT MD MC ME NL MK NO PL PT RO SM RS SK SI ES SE CH UA GB VA").split(),
    "asia-pacific": ("CN JP KR KP MN TW HK MO IN PK BD NP BT LK MV MM TH VN LA KH MY SG "
                     "ID PH BN TL AU NZ PG FJ SB VU NC").split(),
    "southeast-asia": "MM TH VN LA KH MY SG ID PH BN TL".split(),
    "north-america": "US CA MX".split(),
    "latin-america": ("MX GT BZ SV HN NI CR PA CO VE GY SR GF EC PE BR BO PY CL AR UY "
                      "CU DO HT JM TT PR BS").split(),
    "middle-east": "TR SY LB IL PS JO IQ IR SA YE OM AE QA BH KW EG CY".split(),
    "balkans": "SI HR BA RS ME XK MK AL GR BG RO".split(),
    "cis": "RU KZ UZ TM KG TJ AZ AM GE BY UA MD".split(),
    # Not sold yet. Drawn anyway so that the day a plan appears, the picture is
    # already there rather than falling back to a globe nobody meant.
    "africa": ("DZ AO BJ BW BF BI CM CV CF TD KM CD CG CI DJ EG GQ ER SZ ET GA GM GH GN "
               "GW KE LS LR LY MG MW ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD "
               "TZ TG TN UG ZM ZW EH").split(),
}

# Antarctica is a bar across the bottom of any world map and nobody buys a plan
# for it. Leaving it in also wrecks the framing: it stretches the drawing to the
# pole, which shrinks every continent anybody is actually looking for.
EXCLUDE_FROM_WORLD = {"AQ", "GL", "FK", "TF", "HM", "BV", "SJ"}

# Rendering. The tile these sit in is small, so anything that survives has to be
# worth the pixels: specks below this share of the region's area are dropped, and
# what is left is simplified until it still reads at 40dp.
CANVAS = 100.0
PADDING = 4.0
MIN_AREA_SHARE = 0.0012
SIMPLIFY = 0.35

# A second, blunter cut for the places these appear at 16px: a chip, a list row.
# At that size a coastline is mush and the islands are single pixels, so the
# detail is pure page weight -- and a listing page carries nine of these. The
# silhouette still differs per region, which is the whole point of having them.
COMPACT_MIN_AREA_SHARE = 0.02
COMPACT_SIMPLIFY = 1.6

# --- the flag ----------------------------------------------------------------
# A third variant, and the one that actually gets looked at.
#
# The first two were outlines in a square tile, and at the 30px they are drawn
# at, nine different coastlines read as nine identical blue smudges -- which is
# what a globe on every card looked like, only slower. A country in the same
# list has a real flag: a filled rectangle you recognise before you have read
# anything. So a region gets the same object, at the same size, with the
# silhouette filled and the ground coloured, and the shape has room to be a
# shape.
FLAG_W, FLAG_H = 40.0, 30.0        # 4:3, the ratio the country flags are drawn at
FLAG_PADDING = 1.5
# Tolerances are distances in canvas units, so they only mean anything relative
# to the canvas. Reusing the 100-unit figures on a 40-unit flag asked for a
# simplification of four percent of the width, and every region came out as the
# same handful of triangles -- which is how a coastline becomes a smudge twice
# in a row. At 40 units wide drawn at 40px, one unit is one pixel.
FLAG_SIMPLIFY = 0.22
FLAG_MIN_AREA_SHARE = 0.004

# One colour each, so the tiles are told apart before the outline is even read.
# Warm for the warm places is not a rule, just the easiest thing to remember.
FLAG_COLORS = {
    "global": "#0d5c91",
    "europe": "#1a8fd1",
    "asia-pacific": "#0e7490",
    "southeast-asia": "#0f766e",
    "north-america": "#3f4ea8",
    "latin-america": "#c2600f",
    "middle-east": "#b98b28",
    "balkans": "#7c4dab",
    "cis": "#3f5d75",
    "africa": "#b5452f",
}
FLAG_FALLBACK = "#12395a"


def load(path: Path) -> dict:
    if not path.exists():
        print(f"fetching {SOURCE}")
        with urllib.request.urlopen(SOURCE, timeout=180) as response:
            path.write_bytes(response.read())
    return json.loads(path.read_text(encoding="utf-8"))


def iso2(feature: dict) -> str:
    props = feature["properties"]
    return (props.get("ISO_A2_EH") or props.get("ISO_A2") or "").upper()


def rings(geometry: dict) -> list[list[tuple[float, float]]]:
    """Outer rings only. Holes are lakes, and a lake is not the point here."""
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "Polygon":
        return [[(x, y) for x, y in coords[0]]]
    if kind == "MultiPolygon":
        return [[(x, y) for x, y in polygon[0]] for polygon in coords]
    return []


def unwrap(polygons: list[list[tuple[float, float]]], enabled: bool = True
           ) -> list[list[tuple[float, float]]]:
    """Put the antimeridian back together.

    Natural Earth cuts Russia and Fiji at 180 degrees, so their eastern halves
    arrive at -180. Left alone, a region containing either spans the whole planet
    and the drawing collapses to a smear. Shifting the western strays east keeps
    the landmass in one piece.
    """
    longitudes = [x for ring in polygons for x, _ in ring]
    if not enabled:
        # A world map is supposed to span the antimeridian; "repairing" it drags
        # the eastern half of Russia across the Pacific and smears the result.
        return polygons
    if not longitudes or max(longitudes) - min(longitudes) < 180:
        return polygons
    eastern = sum(1 for x in longitudes if x > 0)
    if eastern < len(longitudes) / 2:
        return polygons
    return [[((x + 360 if x < -30 else x), y) for x, y in ring] for ring in polygons]


def area(ring: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def simplify_ring(ring: list[tuple[float, float]], tolerance: float
                  ) -> list[tuple[float, float]]:
    """Simplify a closed ring.

    Ramer-Douglas-Peucker measures every point against the line from the first
    to the last, and on a closed ring those are the same point: the line has no
    length, every distance comes out zero, and the whole coastline reduces to
    two points. Cutting the ring at its far side first gives the algorithm two
    open chains, which is what it is for.
    """
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 4:
        return ring
    start = ring[0]
    far = max(range(len(ring)), key=lambda i: math.dist(start, ring[i]))
    first = simplify(ring[: far + 1], tolerance)
    second = simplify(ring[far:] + [start], tolerance)
    return first[:-1] + second[:-1]


def simplify(ring: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker on an open chain. Coastlines carry far more detail
    than a 40dp tile can show, and every point kept is bytes in every install."""
    if len(ring) < 3:
        return ring
    start, end = ring[0], ring[-1]
    worst, index = 0.0, 0
    dx, dy = end[0] - start[0], end[1] - start[1]
    span = math.hypot(dx, dy) or 1e-9
    for i in range(1, len(ring) - 1):
        px, py = ring[i]
        distance = abs(dy * px - dx * py + end[0] * start[1] - end[1] * start[0]) / span
        if distance > worst:
            worst, index = distance, i
    if worst <= tolerance:
        return [start, end]
    left = simplify(ring[: index + 1], tolerance)
    right = simplify(ring[index:], tolerance)
    return left[:-1] + right


def build(polygons: list[list[tuple[float, float]]], *, whole_world: bool = False,
          tolerance: float = SIMPLIFY, min_area: float = MIN_AREA_SHARE,
          width: float = CANVAS, height: float = CANVAS,
          padding: float = PADDING) -> str:
    """Project, crop and simplify into one SVG path. Empty string if nothing survives."""
    polygons = unwrap(polygons, enabled=not whole_world)
    if not polygons:
        return ""

    # Frame on what will actually be drawn. Specks are dropped later, but if the
    # bounding box is measured before that, one islet off Svalbard pushes the
    # frame north and leaves mainland Europe as a smudge in the middle of an
    # otherwise empty tile.
    largest = max((area(ring) for ring in polygons), default=0) or 1
    kept = [ring for ring in polygons if area(ring) / largest >= min_area]
    polygons = kept or polygons

    lats = [y for ring in polygons for _, y in ring]
    mid_lat = (max(lats) + min(lats)) / 2
    # Equirectangular with the region's own standard parallel. Plain lon/lat
    # stretches anywhere far from the equator sideways -- Europe ends up looking
    # like it was sat on.
    squeeze = max(0.25, math.cos(math.radians(mid_lat)))
    projected = [[(x * squeeze, -y) for x, y in ring] for ring in polygons]

    xs = [x for ring in projected for x, _ in ring]
    ys = [y for ring in projected for _, y in ring]
    span_x, span_y = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
    # Fit to whichever side runs out first, so a wide region fills the width and
    # a tall one fills the height rather than both being sized by the same edge.
    scale = min((width - 2 * padding) / span_x, (height - 2 * padding) / span_y)
    offset_x = padding + (width - 2 * padding - span_x * scale) / 2
    offset_y = padding + (height - 2 * padding - span_y * scale) / 2

    placed = [
        [((x - min(xs)) * scale + offset_x, (y - min(ys)) * scale + offset_y) for x, y in ring]
        for ring in projected
    ]
    biggest = max((area(r) for r in placed), default=0) or 1

    parts = []
    for ring in sorted(placed, key=area, reverse=True):
        if area(ring) / biggest < min_area:
            continue
        thinned = simplify_ring(ring, tolerance)
        if len(thinned) < 3:
            continue
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in thinned)
        first, rest = points.split(" ", 1) if " " in points else (points, "")
        parts.append(f"M{first} L{rest} Z" if rest else f"M{first} Z")
    return " ".join(parts)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img"
     aria-label="{label}" fill="currentColor">
  <title>{label}</title>
  <path d="{path}"/>
</svg>
"""

FLAG_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 30" role="img"
     aria-label="{label}" preserveAspectRatio="xMidYMid meet">
  <title>{label}</title>
  <rect width="40" height="30" fill="{colour}"/>
  <path d="{path}" fill="#ffffff" fill-opacity=".92"/>
</svg>
"""

FLAG_VECTOR = """<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/build_region_maps.py in the esimsterr backend. -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="40dp"
    android:height="30dp"
    android:viewportWidth="40"
    android:viewportHeight="30">
    <path
        android:fillColor="{colour}"
        android:pathData="M0,0 L40,0 L40,30 L0,30 Z"/>
    <path
        android:fillColor="#EBFFFFFF"
        android:pathData="{path}"/>
</vector>
"""

VECTOR = """<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/build_region_maps.py in the esimsterr backend. Do not
     hand-edit: the website's copy is generated from the same coastlines and the
     two have to stay identical. -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp"
    android:height="24dp"
    android:viewportWidth="100"
    android:viewportHeight="100"
    android:tint="?attr/colorPrimary">
    <path
        android:fillColor="@android:color/white"
        android:pathData="{path}"/>
</vector>
"""


def main():
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=str(here / ".cache" / "ne_110m_countries.geojson"))
    parser.add_argument("--svg-out", default=str(here / "static" / "img" / "regions"))
    parser.add_argument("--vector-out",
                        default=str(here.parent / "esimsterr-mobile-app" / "app" / "src"
                                    / "main" / "res" / "drawable"))
    args = parser.parse_args()

    source = Path(args.source)
    source.parent.mkdir(parents=True, exist_ok=True)
    data = load(source)
    by_code: dict[str, list] = {}
    for feature in data["features"]:
        code = iso2(feature)
        if len(code) == 2:
            by_code.setdefault(code, []).extend(rings(feature["geometry"]))

    svg_dir = Path(args.svg_out)
    svg_dir.mkdir(parents=True, exist_ok=True)
    vector_dir = Path(args.vector_out) if args.vector_out else None
    if vector_dir and not vector_dir.exists():
        vector_dir = None

    for slug, members in REGIONS.items():
        whole_world = members == "*"
        codes = ([c for c in sorted(by_code) if c not in EXCLUDE_FROM_WORLD]
                 if whole_world else list(members))
        polygons = [ring for code in codes for ring in by_code.get(code, [])]
        missing = [c for c in codes if c not in by_code]
        path = build(polygons, whole_world=whole_world)
        if not path:
            print(f"  {slug:15} NOTHING DRAWN — check the country codes")
            continue

        compact = build(polygons, whole_world=whole_world,
                        tolerance=COMPACT_SIMPLIFY, min_area=COMPACT_MIN_AREA_SHARE) or path
        # The flag is drawn at 34-44px, so it gets the blunt cut and the tight
        # padding: at that size the detail is invisible and the empty margin is
        # the difference between a shape and a smudge.
        flag = build(polygons, whole_world=whole_world,
                     tolerance=FLAG_SIMPLIFY, min_area=FLAG_MIN_AREA_SHARE,
                     width=FLAG_W, height=FLAG_H, padding=FLAG_PADDING)
        colour = FLAG_COLORS.get(slug, FLAG_FALLBACK)

        label = slug.replace("-", " ").title()
        (svg_dir / f"{slug}.svg").write_text(SVG.format(label=label, path=path), encoding="utf-8")
        (svg_dir / f"{slug}.min.svg").write_text(SVG.format(label=label, path=compact),
                                                 encoding="utf-8")
        if flag:
            (svg_dir / f"{slug}.flag.svg").write_text(
                FLAG_SVG.format(label=label, path=flag, colour=colour), encoding="utf-8")
        written = f"{svg_dir.name}/{slug}.svg (+{len(compact)} compact, +{len(flag)} flag)"
        if vector_dir:
            stem = slug.replace("-", "_")
            (vector_dir / f"region_{stem}.xml").write_text(VECTOR.format(path=path),
                                                           encoding="utf-8")
            written += f" + region_{stem}.xml"
            if flag:
                (vector_dir / f"flag_{stem}.xml").write_text(
                    FLAG_VECTOR.format(path=flag, colour=colour.upper().replace("#", "#FF")),
                    encoding="utf-8")
                written += f" + flag_{stem}.xml"
        note = f"  (no geometry for {', '.join(missing)})" if missing else ""
        print(f"  {slug:15} {len(path):>6} chars  {written}{note}")


if __name__ == "__main__":
    main()
