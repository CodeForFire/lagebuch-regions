#!/usr/bin/env python3
"""Build region.dem (the FWDM binary elevation grid) from public SRTM1 tiles.

Format (confirmed against the app's own reader, DemFileElevationSampler.cs):
  Header, 40 bytes, little-endian:
    0-3   ASCII "FWDM" magic
    4-7   Int32 version (=1)
    8-15  Double origin latitude  (NW corner)
    16-23 Double origin longitude (NW corner)
    24-31 Double cell size in degrees
    32-35 Int32 rows (north -> south)
    36-39 Int32 columns (west -> east)
  Body: rows*cols Int16 little-endian samples, row-major, NoData = -32768.

Reads bbox from ./build/region.json (written by lookup_boundary.py). Writes
./build/region.dem.

Uses nearest-neighbor sampling against the public Mapzen "skadi" SRTM1
mirror (one .hgt.gz per 1x1 degree cell) rather than stitching tiles into an
intermediate mosaic -- simpler to get right, and fast enough in pure Python
for a Landkreis-sized area (a few tiles, ~1-1.5M output samples). If this
turns out to be too slow in practice, numpy is the one dependency worth
adding here (see plan) -- avoid reaching for it before measuring.
"""
import array
import gzip
import json
import math
import os
import struct
import sys
import urllib.error
import urllib.request

SRTM_SAMPLES_PER_SIDE = 3601
ARC_SECOND_DEG = 1.0 / 3600.0
NODATA = -32768
SKADI_URL = "https://s3.amazonaws.com/elevation-tiles-prod/skadi/{ns_ew_dir}/{tile}.hgt.gz"
BUILD_DIR = "build"

_tile_cache: dict[tuple[int, int], array.array] = {}


def srtm_tile_name(lat_floor: int, lon_floor: int) -> str:
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    return f"{ns}{abs(lat_floor):02d}{ew}{abs(lon_floor):03d}"


def load_tile(lat_floor: int, lon_floor: int) -> array.array:
    key = (lat_floor, lon_floor)
    if key in _tile_cache:
        return _tile_cache[key]

    tile = srtm_tile_name(lat_floor, lon_floor)
    url = SKADI_URL.format(ns_ew_dir=tile[:3], tile=tile)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            compressed = resp.read()
    except urllib.error.URLError as exc:
        print(f"::warning::No SRTM tile for {tile} ({exc}); treating as NoData.", file=sys.stderr)
        grid = array.array("h", [NODATA]) * (SRTM_SAMPLES_PER_SIDE * SRTM_SAMPLES_PER_SIDE)
        _tile_cache[key] = grid
        return grid

    raw = gzip.decompress(compressed)
    expected_len = SRTM_SAMPLES_PER_SIDE * SRTM_SAMPLES_PER_SIDE * 2
    if len(raw) != expected_len:
        raise ValueError(f"{tile}.hgt has unexpected size {len(raw)}, expected {expected_len}")

    grid = array.array("h")
    grid.frombytes(raw)
    if sys.byteorder == "little":
        grid.byteswap()  # .hgt is big-endian; our native array is little-endian on this runner
    _tile_cache[key] = grid
    return grid


def sample(lat: float, lon: float) -> int:
    lat_floor = math.floor(lat)
    lon_floor = math.floor(lon)
    grid = load_tile(lat_floor, lon_floor)

    pixel_row = round(((lat_floor + 1) - lat) / ARC_SECOND_DEG)
    pixel_col = round((lon - lon_floor) / ARC_SECOND_DEG)
    pixel_row = min(max(pixel_row, 0), SRTM_SAMPLES_PER_SIDE - 1)
    pixel_col = min(max(pixel_col, 0), SRTM_SAMPLES_PER_SIDE - 1)

    return grid[pixel_row * SRTM_SAMPLES_PER_SIDE + pixel_col]


def main() -> int:
    with open(os.path.join(BUILD_DIR, "region.json"), encoding="utf-8") as f:
        region = json.load(f)
    bbox = region["boundingBox"]
    min_lat, min_lon = bbox["minLat"], bbox["minLon"]
    max_lat, max_lon = bbox["maxLat"], bbox["maxLon"]

    cell_size = ARC_SECOND_DEG
    rows = round((max_lat - min_lat) / cell_size) + 1
    cols = round((max_lon - min_lon) / cell_size) + 1

    origin_lat = max_lat  # NW corner
    origin_lon = min_lon

    body = array.array("h", [0]) * (rows * cols)
    for r in range(rows):
        lat = origin_lat - r * cell_size
        row_offset = r * cols
        for c in range(cols):
            lon = origin_lon + c * cell_size
            body[row_offset + c] = sample(lat, lon)

    out_path = os.path.join(BUILD_DIR, "region.dem")
    with open(out_path, "wb") as f:
        f.write(b"FWDM")
        f.write(struct.pack("<i", 1))
        f.write(struct.pack("<d", origin_lat))
        f.write(struct.pack("<d", origin_lon))
        f.write(struct.pack("<d", cell_size))
        f.write(struct.pack("<i", rows))
        f.write(struct.pack("<i", cols))
        if sys.byteorder != "little":
            body.byteswap()
        f.write(body.tobytes())

    print(f"Wrote {out_path}: {rows}x{cols} samples, origin=({origin_lat},{origin_lon}), cellSize={cell_size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
