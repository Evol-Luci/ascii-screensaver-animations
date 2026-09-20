#!/usr/bin/env python3
"""Regenerate index.json from all animations/*/manifest.json files.

Usage: python generate_index.py
Run from the repo root. Writes index.json.
"""

import json
import os
from datetime import date

ANIMATIONS_DIR = "animations"
REPO = "Evol-Luci/ascii-screensaver-animations"
BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/refs/heads/{BRANCH}"


def raw_url(animation_id, filename):
    return f"{RAW_BASE}/animations/{animation_id}/{filename}"


def list_files(folder):
    """Return all files in a folder recursively, relative to the folder."""
    result = []
    for dirpath, _, filenames in os.walk(folder):
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, folder)
            result.append(rel)
    return sorted(result)


def main():
    animations = []
    anim_dir = ANIMATIONS_DIR

    if not os.path.isdir(anim_dir):
        print(f"WARNING: {anim_dir}/ directory not found. No animations indexed.")
        index = {"version": 1, "updated": date.today().isoformat(), "animations": []}
        with open("index.json", "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
            f.write("\n")
        print("Generated empty index.json.")
        return

    for name in sorted(os.listdir(anim_dir)):
        folder = os.path.join(anim_dir, name)
        if not os.path.isdir(folder):
            continue
        manifest_path = os.path.join(folder, "manifest.json")
        if not os.path.isfile(manifest_path):
            print(f"WARNING: skipping {name} — no manifest.json")
            continue
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            print(f"WARNING: skipping {name} — invalid manifest.json: {e}")
            continue

        files = [raw_url(name, f) for f in list_files(folder)]
        preview_file = manifest.get("preview", "")
        preview_url = raw_url(name, preview_file) if preview_file else ""

        entry = {
            "id": manifest["id"],
            "name": manifest["name"],
            "description": manifest.get("description", ""),
            "author": manifest.get("author", ""),
            "version": manifest.get("version", "1.0.0"),
            "preview": preview_url,
            "params": manifest.get("params", []),
            "files": files,
        }
        animations.append(entry)

    index = {
        "version": 1,
        "updated": date.today().isoformat(),
        "animations": animations,
    }

    with open("index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
        f.write("\n")

    print(f"Generated index.json with {len(animations)} animations.")


if __name__ == "__main__":
    main()
