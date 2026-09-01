#!/usr/bin/env python3
"""Upsert the built pack's entry into regions.json and region-sources.json.

Env vars: SLUG, NAME, RELATION_ID, ZIP_PATH (built <slug>.zip, for
sizeBytes), ATTRIBUTION (optional override), GITHUB_REPOSITORY (owner/repo,
set automatically in Actions).

Determines the next release version by looking for an existing regions.json
entry for SLUG and parsing its "-vN" tag suffix; a fresh slug starts at v1.
Writes GITHUB_OUTPUT: version, tag, branch.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

DEFAULT_ATTRIBUTION = (
    "© OpenStreetMap contributors (ODbL). "
    "Höhendaten: SRTM (NASA/USGS, gemeinfrei)."
)
REGIONS_JSON = "regions.json"
SOURCES_JSON = "region-sources.json"
VERSION_RE = re.compile(r"/releases/download/[a-z0-9-]+-v(\d+)/")


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main() -> int:
    slug = os.environ["SLUG"]
    name = os.environ["NAME"]
    relation_id = os.environ["RELATION_ID"]
    zip_path = os.environ["ZIP_PATH"]
    attribution = os.environ.get("ATTRIBUTION", DEFAULT_ATTRIBUTION)
    repo = os.environ.get("GITHUB_REPOSITORY", "CodeForFire/lagebuch-regions")

    with open("build/region.json", encoding="utf-8") as f:
        region = json.load(f)
    bbox = region["boundingBox"]

    regions = load_json(REGIONS_JSON, [])
    sources = load_json(SOURCES_JSON, {})

    existing_index = next(
        (i for i, entry in enumerate(regions) if entry.get("slug") == slug), None
    )

    next_version = 1
    if existing_index is not None:
        match = VERSION_RE.search(regions[existing_index].get("downloadUrl", ""))
        if match:
            next_version = int(match.group(1)) + 1

    tag = f"{slug}-v{next_version}"
    entry = {
        "name": name,
        "slug": slug,
        "downloadUrl": f"https://github.com/{repo}/releases/download/{tag}/{slug}.zip",
        "sizeBytes": os.path.getsize(zip_path),
        "boundingBox": {
            "minLat": bbox["minLat"],
            "minLon": bbox["minLon"],
            "maxLat": bbox["maxLat"],
            "maxLon": bbox["maxLon"],
        },
        "builtAt": datetime.now(timezone.utc).date().isoformat(),
        "attribution": attribution,
    }

    if existing_index is not None:
        regions[existing_index] = entry
    else:
        regions.append(entry)
    sources[slug] = {"relationId": relation_id}

    save_json(REGIONS_JSON, regions)
    save_json(SOURCES_JSON, sources)

    print(f"regions.json/region-sources.json updated: {slug} -> {tag}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"version={next_version}\n")
            f.write(f"tag={tag}\n")
            f.write(f"branch=region-pack/{tag}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
