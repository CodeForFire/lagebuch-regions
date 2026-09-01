#!/usr/bin/env python3
"""Pack a rendered {z}/{x}/{y}.png tile tree into an MBTiles sqlite file.

Writes TMS row numbering explicitly (row 0 = south), as the app expects:
tile_row = (2**z - 1) - y, where y is the standard XYZ/slippy-map row that
render_bbox_to_tiles.sh lays the tiles out with.

Env vars: TILES_DIR (default build/tiles), OUT (default build/region.dem's
sibling build/region.mbtiles), NAME (region display name for metadata).
Reads bbox from ./build/region.json.
"""
import json
import os
import sqlite3
import sys

BUILD_DIR = "build"


def main() -> int:
    tiles_dir = os.environ.get("TILES_DIR", os.path.join(BUILD_DIR, "tiles"))
    out_path = os.environ.get("OUT", os.path.join(BUILD_DIR, "region.mbtiles"))
    name = os.environ.get("NAME", "region")

    with open(os.path.join(BUILD_DIR, "region.json"), encoding="utf-8") as f:
        region = json.load(f)
    bbox = region["boundingBox"]

    if os.path.exists(out_path):
        os.remove(out_path)

    conn = sqlite3.connect(out_path)
    conn.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    conn.execute(
        "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)"
    )

    zoom_levels = sorted(
        int(z) for z in os.listdir(tiles_dir) if os.path.isdir(os.path.join(tiles_dir, z))
    )
    if not zoom_levels:
        print(f"::error::No rendered tiles found under {tiles_dir}", file=sys.stderr)
        return 1

    tile_count = 0
    for z in zoom_levels:
        z_dir = os.path.join(tiles_dir, str(z))
        for x_name in os.listdir(z_dir):
            x_dir = os.path.join(z_dir, x_name)
            if not os.path.isdir(x_dir):
                continue
            x = int(x_name)
            for y_file in os.listdir(x_dir):
                if not y_file.endswith(".png"):
                    continue
                y = int(y_file[: -len(".png")])
                tms_row = (2**z - 1) - y
                with open(os.path.join(x_dir, y_file), "rb") as f:
                    data = f.read()
                conn.execute(
                    "INSERT INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                    (z, x, tms_row, sqlite3.Binary(data)),
                )
                tile_count += 1

    metadata = {
        "name": name,
        "format": "png",
        "type": "baselayer",
        "version": "1.1",
        "bounds": f"{bbox['minLon']},{bbox['minLat']},{bbox['maxLon']},{bbox['maxLat']}",
        "minzoom": str(min(zoom_levels)),
        "maxzoom": str(max(zoom_levels)),
    }
    conn.executemany(
        "INSERT INTO metadata (name, value) VALUES (?, ?)", metadata.items()
    )

    conn.commit()
    conn.close()
    print(f"Wrote {out_path}: {tile_count} tiles, zoom {min(zoom_levels)}-{max(zoom_levels)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
