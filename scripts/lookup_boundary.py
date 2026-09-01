#!/usr/bin/env python3
"""Look up an OSM relation's admin boundary via Nominatim and enforce the
"Landkreis-sized region" guardrail.

Reads RELATION_ID (and, for messages, SLUG/NAME) from the environment.
Writes ./build/boundary.geojson and ./build/region.json on success. On a
guardrail failure, prints an issue-postable message and exits 1 instead of
writing anything.

Required Germany-only admin_level for a Kreis / kreisfreie Stadt is 6.
A flat bounding-box area threshold cannot reliably distinguish a Kreis from
a Bundesland (e.g. Mecklenburgische Seenplatte, a real Landkreis, is
~5,470 km^2 -- bigger than some whole states like Saarland at ~2,570 km^2),
so admin_level is the primary check; area is only a generous backstop for
data-quality anomalies.
"""
import json
import math
import os
import sys
import urllib.request
import urllib.error

NOMINATIM_URL = (
    "https://nominatim.openstreetmap.org/lookup"
    "?osm_ids=R{relation_id}&format=json&polygon_geojson=1"
    "&addressdetails=1&extratags=1"
)
USER_AGENT = "lagebuch-regions-build-bot/1.0 (+https://github.com/CodeForFire/lagebuch-regions)"
REQUIRED_ADMIN_LEVEL = "6"
MAX_AREA_KM2 = 7000
EARTH_RADIUS_KM = 6371.0
BUILD_DIR = "build"


def fail(message: str) -> "NoReturn":
    print(f"::error::{message}", file=sys.stderr)
    print(message)
    sys.exit(1)


def fetch_nominatim(relation_id: str) -> dict:
    url = NOMINATIM_URL.format(relation_id=relation_id)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
    except urllib.error.URLError as exc:
        fail(f"Nominatim lookup failed for relation {relation_id}: {exc}")
    if not body:
        fail(
            f"Nominatim has no record for relation {relation_id}. "
            "Double check the ID at https://www.openstreetmap.org/relation/"
            f"{relation_id}"
        )
    return body[0]


def bbox_area_km2(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> float:
    """Rough equirectangular-approximation area, adequate for a sanity backstop."""
    mean_lat_rad = math.radians((min_lat + max_lat) / 2)
    lat_km = (max_lat - min_lat) * (math.pi / 180) * EARTH_RADIUS_KM
    lon_km = (max_lon - min_lon) * (math.pi / 180) * EARTH_RADIUS_KM * math.cos(mean_lat_rad)
    return abs(lat_km * lon_km)


def main() -> int:
    relation_id = os.environ["RELATION_ID"]
    result = fetch_nominatim(relation_id)

    admin_level = str(result.get("extratags", {}).get("admin_level", ""))
    if admin_level != REQUIRED_ADMIN_LEVEL:
        fail(
            f"Relation {relation_id} has admin_level={admin_level!r}, expected "
            f"{REQUIRED_ADMIN_LEVEL!r} (Kreis / kreisfreie Stadt). This workflow only "
            "builds Landkreis-sized region packs -- pick the OSM relation for the "
            "Kreis itself, not a Bundesland or municipality."
        )

    try:
        min_lat, max_lat, min_lon, max_lon = (float(v) for v in result["boundingbox"])
    except (KeyError, ValueError) as exc:
        fail(f"Relation {relation_id} has no usable bounding box: {exc}")

    area_km2 = bbox_area_km2(min_lat, min_lon, max_lat, max_lon)
    if area_km2 > MAX_AREA_KM2:
        fail(
            f"Relation {relation_id}'s bounding box is ~{area_km2:.0f} km^2, above the "
            f"{MAX_AREA_KM2} km^2 sanity backstop for a Landkreis-sized region. "
            "Please double check the relation ID."
        )

    address = result.get("address", {})
    state = address.get("state")
    state_district = address.get("state_district")
    if not state:
        fail(f"Relation {relation_id} has no address.state from Nominatim; cannot pick a Geofabrik extract.")

    geometry = result.get("geojson")
    if not geometry:
        fail(f"Relation {relation_id} has no polygon geometry from Nominatim.")

    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(os.path.join(BUILD_DIR, "boundary.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "Feature", "properties": {}, "geometry": geometry}, f)

    region = {
        "relationId": relation_id,
        "displayName": result.get("display_name"),
        "adminLevel": admin_level,
        "state": state,
        "stateDistrict": state_district,
        "boundingBox": {
            "minLat": min_lat,
            "minLon": min_lon,
            "maxLat": max_lat,
            "maxLon": max_lon,
        },
        "areaKm2": area_km2,
    }
    with open(os.path.join(BUILD_DIR, "region.json"), "w", encoding="utf-8") as f:
        json.dump(region, f, indent=2)

    print(f"Boundary OK: {result.get('display_name')} ({area_km2:.0f} km^2, admin_level={admin_level})")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"state={state}\n")
            f.write(f"state_district={state_district or ''}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
