"""Greenhouse detector: NAIP aerial imagery + OSM labels, in Google Earth Engine.

There is no national greenhouse database, but greenhouses are distinctive from
above (bright, translucent, regular, low vegetation signal, strong row texture).
This trains a random forest on OpenStreetMap greenhouse polygons and maps
candidates that OSM is missing, which become new heat sinks.

Validation uses a SPATIAL BLOCK split (~5 km grid cells held out whole), so the
reported accuracy reflects performance on places the model never saw, not
neighbouring pixels of the same greenhouse.

Quota: training samples only small areas around labels; classification runs over
an AOI you choose. Keep AOIs to roughly a few hundred km^2 for interactive runs.

Status: built and validated, but it found only 3 of 26 known greenhouses on a
real test area, so its output is NOT used in any result.
"""
from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

from .climate import init
from .osm import SINK_TYPES, polygon_area_m2

NAIP = "USDA/NAIP/DOQQ"
BLOCK_DEG = 0.05  # ~5 km spatial blocks for train/test split
TEST_FOLDS = 3  # of 10 -> ~30% of blocks held out


def osm_greenhouse_polygons(osm_cache: Path) -> list[list[list[float]]]:
    """Greenhouse outer rings [[lon, lat], ...] from a cached Overpass response."""
    els = json.loads(osm_cache.read_text())["elements"]
    polys = []
    for e in els:
        t = e.get("tags", {})
        if (t.get("building") == "greenhouse" or t.get("landuse") == "greenhouse_horticulture") and e.get("geometry"):
            ring = [[p["lon"], p["lat"]] for p in e["geometry"]]
            if len(ring) >= 4 and polygon_area_m2(e["geometry"]) >= 200:
                polys.append(ring)
    return polys


def naip_mosaic(ee, region):
    col = ee.ImageCollection(NAIP).filterBounds(region).filterDate("2018-01-01", "2027-01-01")
    year = ee.Date(col.aggregate_max("system:time_start")).get("year")
    img = col.filter(ee.Filter.calendarRange(year, year, "year")).mosaic()
    return img, year


def features(ee, naip):
    """Spectral + texture stack. NAIP bands R, G, B, N (0-255)."""
    f = naip.select(["R", "G", "B", "N"]).toFloat()
    ndvi = f.normalizedDifference(["N", "R"]).rename("ndvi")
    bright = f.select(["R", "G", "B"]).reduce(ee.Reducer.mean()).rename("bright")
    gray = bright.toInt()
    entropy = gray.entropy(ee.Kernel.square(3)).rename("entropy")
    local_sd = bright.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.square(5)).rename("sd5")
    local_mean = bright.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.square(15)).rename("mean15")
    return ee.Image.cat([f, ndvi, bright, entropy, local_sd, local_mean])


def fold_of(lon: float, lat: float) -> int:
    """Spatial block (~5 km) -> fold 0..9. Whole blocks go to train or test."""
    bx, by = math.floor(lon / BLOCK_DEG), math.floor(lat / BLOCK_DEG)
    return abs(bx * 7919 + by * 104729) % 10


def _inside(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon."""
    inside, n = False, len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[i - 1]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def sample_points(rings, per_polygon: int = 8, neg_per_polygon: int = 24,
                  ring_m: tuple[float, float] = (15, 1500), seed: int = 42) -> list[tuple]:
    """(lon, lat, label, fold) points, generated locally so Earth Engine only has
    to read pixel values at exact points. Negatives come from a ring around each
    greenhouse (nearby fields, roads, other roofs: the hard cases) and are
    rejected if they fall inside any greenhouse."""
    rnd = random.Random(seed)
    boxes = [(min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)) for r in rings]

    def in_any(lon, lat):
        return any(b[0] <= lon <= b[2] and b[1] <= lat <= b[3] and _inside(lon, lat, r)
                   for r, b in zip(rings, boxes))

    pts = []
    for r, (w, s, e, n) in zip(rings, boxes):
        got = tries = 0
        while got < per_polygon and tries < per_polygon * 50:
            tries += 1
            lon, lat = rnd.uniform(w, e), rnd.uniform(s, n)
            if _inside(lon, lat, r):
                pts.append((lon, lat, 1, fold_of(lon, lat)))
                got += 1
        cx, cy = (w + e) / 2, (s + n) / 2
        got = tries = 0
        while got < neg_per_polygon and tries < neg_per_polygon * 50:
            tries += 1
            d = rnd.uniform(*ring_m)
            ang = rnd.uniform(0, 2 * math.pi)
            lat = cy + d * math.sin(ang) / 111_320
            lon = cx + d * math.cos(ang) / (111_320 * math.cos(math.radians(cy)))
            if not in_any(lon, lat):
                pts.append((lon, lat, 0, fold_of(lon, lat)))
                got += 1
    return pts


def train(osm_cache: Path, project: str = "thermalite", max_polygons: int = 400,
          seed: int = 42, **sample_kwargs) -> dict:
    """Train on OSM greenhouses and report block-held-out accuracy."""
    ee = init(project)
    rings = osm_greenhouse_polygons(osm_cache)[:max_polygons]
    if len(rings) < 20:
        raise SystemExit(f"Only {len(rings)} OSM greenhouse polygons; need >= 20 to train.")
    gh = ee.FeatureCollection([ee.Feature(ee.Geometry.Polygon([r])) for r in rings])
    pts = sample_points(rings, seed=seed, **sample_kwargs)
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([lon, lat]), {"label": lab, "fold": fold}) for lon, lat, lab, fold in pts
    ])

    naip, year = naip_mosaic(ee, gh.geometry().bounds())
    stack = features(ee, naip)
    samples = stack.sampleRegions(collection=fc, properties=["label", "fold"], scale=1, tileScale=4)

    bands = stack.bandNames()
    train_fc = samples.filter(ee.Filter.gte("fold", TEST_FOLDS))
    test_fc = samples.filter(ee.Filter.lt("fold", TEST_FOLDS))
    clf = ee.Classifier.smileRandomForest(numberOfTrees=100, seed=seed).train(train_fc, "label", bands)
    cm = test_fc.classify(clf).errorMatrix("label", "classification")

    m = ee.Dictionary({
        "naip_year": year, "train_n": train_fc.size(), "test_n": test_fc.size(),
        "matrix": cm.array(), "accuracy": cm.accuracy(), "kappa": cm.kappa(),
        "producers": cm.producersAccuracy(), "consumers": cm.consumersAccuracy(),
    }).getInfo()
    mat = m["matrix"]  # rows = actual [0,1], cols = predicted [0,1]
    tp, fn, fp = mat[1][1], mat[1][0], mat[0][1]
    return {
        "naip_year": m["naip_year"], "osm_polygons": len(rings), "points_generated": len(pts),
        "train_samples": m["train_n"], "test_samples": m["test_n"],
        "confusion_matrix_actual_by_predicted": mat,
        "accuracy": round(m["accuracy"], 3), "kappa": round(m["kappa"], 3),
        "greenhouse_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "greenhouse_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "_clf": clf, "_gh": gh,
    }


def _overlaps(a: list[list[float]], b: list[list[float]]) -> bool:
    """Rough polygon overlap: any vertex or the centroid of one inside the other."""
    def cen(r):
        return sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r)
    return (any(_inside(x, y, b) for x, y in a + [cen(a)])
            or any(_inside(x, y, a) for x, y in b + [cen(b)]))


def detect(bbox: list[float], osm_cache: Path, out: Path, project: str = "thermalite",
           min_area_m2: float = 300, max_area_m2: float = 200_000, min_rectangularity: float = 0.55,
           prob_threshold: float = 0.75, **train_kwargs) -> dict:
    """Train, then map candidate greenhouses inside bbox [west, south, east, north].

    Candidates must be confident (probability > threshold), plausibly sized, and
    compact (area / bounding-box area >= min_rectangularity), because pixel-level
    false positives multiply across a landscape where greenhouses are rare.

    Writes a sinks CSV of candidates (`in_osm` = OSM already has it), a GeoJSON
    of candidate outlines for review, and reports object-level recall against
    the OSM greenhouses inside the bbox."""
    ee = init(project)
    model = train(osm_cache, project=project, **train_kwargs)
    clf = model.pop("_clf")
    model.pop("_gh")

    aoi = ee.Geometry.Rectangle(bbox)
    naip, _ = naip_mosaic(ee, aoi)
    prob = features(ee, naip).classify(clf.setOutputMode("PROBABILITY"))
    mask = prob.gt(prob_threshold).focalMode(1.5).selfMask().toInt()
    vectors = mask.reduceToVectors(geometry=aoi, scale=1, geometryType="polygon",
                                   eightConnected=False, maxPixels=1e10, tileScale=8)

    def props(f):
        g = f.geometry()
        area = g.area(1)
        return f.set("area_m2", area, "rect", area.divide(g.bounds(1).area(1)))

    vectors = (vectors.map(props)
               .filter(ee.Filter.gte("area_m2", min_area_m2))
               .filter(ee.Filter.lte("area_m2", max_area_m2))
               .filter(ee.Filter.gte("rect", min_rectangularity)))
    result = vectors.map(lambda f: f.setGeometry(f.geometry().simplify(1))).getInfo()

    w, s, e, n = bbox
    osm_in_box = [r for r in osm_greenhouse_polygons(osm_cache)
                  if all(w <= p[0] <= e and s <= p[1] <= n for p in r)]
    temp, kwh_m2, _, _ = SINK_TYPES["greenhouse"]
    rows, outlines = [], []
    for i, f in enumerate(result["features"]):
        ring = f["geometry"]["coordinates"][0]
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        a = f["properties"]["area_m2"]
        in_osm = any(_overlaps(ring, r) for r in osm_in_box)
        rows.append({
            "id": f"GHD{i}", "name": f"Detected greenhouse {i} ({'in OSM' if in_osm else 'NEW'})",
            "type": "greenhouse", "lat": round(lat, 6), "lon": round(lon, 6),
            "annual_heat_mwh": round(a * kwh_m2 / 1000), "supply_temp_c": temp, "profile": "",
            "footprint_m2": round(a), "rectangularity": round(f["properties"]["rect"], 2),
            "in_osm": in_osm, "demand_estimated": "yes", "reviewed": "",
        })
        outlines.append({"type": "Feature", "geometry": f["geometry"],
                         "properties": {"id": f"GHD{i}", "in_osm": in_osm, "area_m2": round(a)}})

    found = sum(any(_overlaps(r, o["geometry"]["coordinates"][0]) for o in outlines) for r in osm_in_box)

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["id"])
        wr.writeheader()
        wr.writerows(rows)
    geo = out.with_suffix(".geojson")
    geo.write_text(json.dumps({
        "type": "FeatureCollection", "features": outlines,
        "osm": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [r]}, "properties": {}}
                for r in osm_in_box],
        "bbox": bbox,
    }))
    model.update({
        "candidates": len(rows), "new_not_in_osm": sum(not r["in_osm"] for r in rows),
        "candidate_area_m2": round(sum(r["footprint_m2"] for r in rows)),
        "osm_greenhouses_in_bbox": len(osm_in_box),
        "osm_greenhouses_found (object recall)": f"{found}/{len(osm_in_box)}",
    })
    return model
