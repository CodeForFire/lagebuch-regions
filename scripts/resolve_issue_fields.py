#!/usr/bin/env python3
"""Resolve the slug/name/relation_id to build from parsed issue-form fields.

Deliberately reads everything from environment variables (never from
interpolated shell/source text) since these values come straight from
untrusted issue text -- only os.environ access and dict lookups touch them,
no shell or eval.

Env vars: TEMPLATE ("new" or "update"), NEW_SLUG, NEW_RELATION_ID, NEW_NAME,
UPDATE_SLUG, UPDATE_RELATION_ID (may be empty to reuse the stored relation).
Writes GITHUB_OUTPUT: slug, name, relation_id.
"""
import json
import os
import sys


def main() -> int:
    template = os.environ.get("TEMPLATE", "new")

    if template == "update":
        slug = os.environ.get("UPDATE_SLUG", "")
        relation_id = os.environ.get("UPDATE_RELATION_ID", "")

        regions = json.load(open("regions.json", encoding="utf-8"))
        entry = next((r for r in regions if r.get("slug") == slug), None)
        if entry is None:
            print(f"::error::No existing regions.json entry for slug {slug!r}.", file=sys.stderr)
            return 1
        name = entry["name"]

        if not relation_id:
            sources = json.load(open("region-sources.json", encoding="utf-8"))
            relation_id = sources.get(slug, {}).get("relationId", "")
    else:
        slug = os.environ.get("NEW_SLUG", "")
        relation_id = os.environ.get("NEW_RELATION_ID", "")
        name = os.environ.get("NEW_NAME", "")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"slug={slug}\n")
            f.write(f"relation_id={relation_id}\n")
            f.write(f"name={name}\n")
    print(f"Resolved: slug={slug!r} name={name!r} relation_id={relation_id!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
