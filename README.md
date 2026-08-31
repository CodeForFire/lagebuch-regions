# lagebuch-regions

Published Wasserförderung region packs for the [LageBuch](https://github.com/CodeForFire/lagebuch)
fire-brigade incident-logging app. Each pack contains raster map tiles and an elevation grid for
one Landkreis, downloadable directly from the app's Stammdaten → Einsatzgebiet screen.

`regions.json` is the manifest the app fetches (served raw, no auth, no GitHub API rate limit).
Each entry points at a GitHub Release asset — a zip containing exactly `region.mbtiles` (MBTiles
raster tiles, zoom 11–15) and `region.dem` (a small custom elevation-grid format; see the LageBuch
repo's `src/LageBuch.Persistence/Wasserfoerderung/DemFileElevationSampler.cs` for the exact byte
layout).

See [`tools/build-region-pack/README.md`](https://github.com/CodeForFire/lagebuch/blob/main/tools/build-region-pack/README.md)
in the main repo for how a pack is built.

## Licensing

- Map tiles: rendered from © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
  data (ODbL 1.0). Rendered raster tiles are a "Produced Work" under ODbL — attribution required,
  share-alike does not apply.
- Elevation: [SRTM](https://www2.jpl.nasa.gov/srtm/) (NASA/USGS) — US public domain.
