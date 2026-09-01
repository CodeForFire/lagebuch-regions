#!/usr/bin/env python3
"""Build the workflow_call matrix for the scheduled refresh, from
region-sources.json (relation IDs) joined with regions.json (display
names). Writes GITHUB_OUTPUT: matrix (a {"include": [...]} JSON object).
"""
import json
import os
import sys


def main() -> int:
    sources = json.load(open("region-sources.json", encoding="utf-8"))
    regions = {r["slug"]: r for r in json.load(open("regions.json", encoding="utf-8"))}

    include = [
        {"slug": slug, "name": regions[slug]["name"], "relation_id": src["relationId"]}
        for slug, src in sources.items()
        if slug in regions
    ]
    matrix = json.dumps({"include": include})

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"matrix={matrix}\n")
            f.write(f"has_regions={'true' if include else 'false'}\n")
    print(f"Refresh matrix: {matrix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
