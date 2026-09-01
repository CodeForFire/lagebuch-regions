#!/usr/bin/env bash
# Orchestrates the full pack build: boundary lookup -> OSM extract -> render
# -> mbtiles -> DEM -> zip. Expects SLUG, NAME, RELATION_ID in the
# environment (already validated by the caller). Produces build/<slug>.zip.
#
# Runnable locally the same way CI runs it, given osmium-tool, docker and
# python3 on PATH.
set -euo pipefail

: "${SLUG:?}" "${NAME:?}" "${RELATION_ID:?}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p build

echo "== Validating inputs =="
python3 "$SCRIPT_DIR/validate_inputs.py"

echo "== Looking up boundary =="
python3 "$SCRIPT_DIR/lookup_boundary.py"

echo "== Resolving Geofabrik extract =="
EXTRACT_PATH="$(python3 "$SCRIPT_DIR/resolve_geofabrik_extract.py")"
echo "Using $EXTRACT_PATH"

echo "== Downloading regional extract =="
curl -fL --retry 3 "https://download.geofabrik.de/europe/germany/$EXTRACT_PATH" -o build/state.osm.pbf

echo "== Clipping to region boundary =="
osmium extract --polygon build/boundary.geojson build/state.osm.pbf -o build/region.osm.pbf --overwrite
rm -f build/state.osm.pbf # free disk before the render step, which is the tight resource

MIN_LAT="$(python3 -c "import json;print(json.load(open('build/region.json'))['boundingBox']['minLat'])")"
MIN_LON="$(python3 -c "import json;print(json.load(open('build/region.json'))['boundingBox']['minLon'])")"
MAX_LAT="$(python3 -c "import json;print(json.load(open('build/region.json'))['boundingBox']['maxLat'])")"
MAX_LON="$(python3 -c "import json;print(json.load(open('build/region.json'))['boundingBox']['maxLon'])")"

echo "== Rendering tiles =="
EXTRACT_PBF=build/region.osm.pbf \
  MIN_LAT="$MIN_LAT" MIN_LON="$MIN_LON" MAX_LAT="$MAX_LAT" MAX_LON="$MAX_LON" \
  TILES_DIR=build/tiles \
  bash "$SCRIPT_DIR/render_bbox_to_tiles.sh"

echo "== Building region.mbtiles =="
TILES_DIR=build/tiles OUT=build/region.mbtiles NAME="$NAME" python3 "$SCRIPT_DIR/build_mbtiles.py"

echo "== Building region.dem =="
python3 "$SCRIPT_DIR/build_dem.py"

echo "== Packaging =="
rm -f "build/$SLUG.zip"
(cd build && zip -j "$SLUG.zip" region.mbtiles region.dem)

echo "Built build/$SLUG.zip"
