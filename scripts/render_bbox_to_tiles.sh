#!/usr/bin/env bash
# Render zoom 11-15 raster PNG tiles for a bbox from a clipped .osm.pbf,
# using the overv/openstreetmap-tile-server image (Mapnik + osm2pgsql +
# renderd), matching how the manual ffb-v1 pack was built.
#
# render_list writes into mod_tile's on-disk cache as hashed binary
# metatiles (TILEDIR/default/<z>/<hashed-path>/<n>.meta, each covering an
# 8x8 tile block) -- not a plain {z}/{x}/{y}.png tree, and not reachable by
# just bind-mounting the cache dir. The documented way to get a plain PNG
# back out is the HTTP endpoint mod_tile/Apache serve at
# /tile/{z}/{x}/{y}.png, which decodes the metatile on request. So we
# pre-render with render_list (fast, bulk) to warm that cache, then fetch
# each tile individually over HTTP into TILES_DIR (near-instant, served
# from cache). Confirmed against a live import+render in this repo.
set -euo pipefail

: "${EXTRACT_PBF:?set EXTRACT_PBF to the clipped .osm.pbf path}"
: "${MIN_LAT:?}" "${MIN_LON:?}" "${MAX_LAT:?}" "${MAX_LON:?}"
TILES_DIR="${TILES_DIR:-build/tiles}"
MIN_ZOOM=11
MAX_ZOOM=15
CONTAINER_NAME="region-tile-server-$$"

mkdir -p "$TILES_DIR"
EXTRACT_PBF_ABS="$(cd "$(dirname "$EXTRACT_PBF")" && pwd)/$(basename "$EXTRACT_PBF")"
TILES_DIR_ABS="$(cd "$TILES_DIR" && pwd)"

echo "Importing $EXTRACT_PBF_ABS into overv/openstreetmap-tile-server ..."
docker run --rm \
  -v "$EXTRACT_PBF_ABS":/data/region.osm.pbf \
  -v osm-data:/data/database/ \
  overv/openstreetmap-tile-server import

echo "Starting renderd/tile server ..."
docker run -d --name "$CONTAINER_NAME" \
  -p 127.0.0.1:0:80 \
  -v osm-data:/data/database/ \
  overv/openstreetmap-tile-server run

HOST_PORT="$(docker port "$CONTAINER_NAME" 80/tcp | head -n1 | cut -d: -f2)"
TILE_BASE_URL="http://127.0.0.1:$HOST_PORT/tile"

cleanup() {
  docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Waiting for renderd to become ready ..."
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER_NAME" pgrep renderd >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

# Compute per-zoom tile x/y ranges from the bbox (standard slippy-map math).
# render_list's -x/-X/-y/-Y take tile coordinates at the zoom level being
# rendered, so each zoom needs its own range -- looping avoids relying on
# assumptions about how a single range would scale across -z/-Z.
TILE_RANGES="$(python3 - "$MIN_LAT" "$MIN_LON" "$MAX_LAT" "$MAX_LON" "$MIN_ZOOM" "$MAX_ZOOM" <<'PYEOF'
import math
import sys

min_lat, min_lon, max_lat, max_lon, min_zoom, max_zoom = sys.argv[1:7]
min_lat, min_lon, max_lat, max_lon = map(float, (min_lat, min_lon, max_lat, max_lon))
min_zoom, max_zoom = int(min_zoom), int(max_zoom)


def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0**zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(xtile, int(n) - 1)), max(0, min(ytile, int(n) - 1))


for z in range(min_zoom, max_zoom + 1):
    x_min, y_min = deg2num(max_lat, min_lon, z)  # NW corner
    x_max, y_max = deg2num(min_lat, max_lon, z)  # SE corner
    print(f"{z} {x_min} {x_max} {y_min} {y_max}")
PYEOF
)"

NPROC="$(nproc)"
echo "$TILE_RANGES" | while read -r z x_min x_max y_min y_max; do
  echo "Rendering zoom $z (x $x_min-$x_max, y $y_min-$y_max) ..."
  docker exec "$CONTAINER_NAME" render_list \
    -a -z "$z" -Z "$z" \
    -x "$x_min" -X "$x_max" -y "$y_min" -Y "$y_max" \
    -n "$NPROC" -f
done

echo "Fetching rendered tiles from $TILE_BASE_URL into $TILES_DIR_ABS ..."
echo "$TILE_RANGES" | while read -r z x_min x_max y_min y_max; do
  for x in $(seq "$x_min" "$x_max"); do
    mkdir -p "$TILES_DIR_ABS/$z/$x"
    for y in $(seq "$y_min" "$y_max"); do
      echo "$TILES_DIR_ABS/$z/$x/$y.png" "$TILE_BASE_URL/$z/$x/$y.png"
    done
  done
done | xargs -P "$NPROC" -n2 curl -fsS --retry 3 -o

echo "Tiles written under $TILES_DIR_ABS"
