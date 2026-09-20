#!/usr/bin/env python3
"""Validate a single animation folder for PR submission.

Usage: python validate_animation.py <path/to/animation-folder>
Exits 0 on success, 1 on failure (prints reason to stdout).
"""

import json
import os
import re
import sys


MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
REQUIRED_MANIFEST_FIELDS = ["id", "name", "description", "author", "version", "preview"]
ALLOWED_PREVIEW_EXTENSIONS = {".gif", ".png", ".jpg", ".jpeg"}

EXTERNAL_SCRIPT_RE = re.compile(
    r'<script[^>]+src=["\']https?://', re.IGNORECASE
)
EXTERNAL_FETCH_RE = re.compile(
    r"""fetch\s*\(\s*['"]https?://""", re.IGNORECASE
)
EXTERNAL_XHR_RE = re.compile(
    r"""XMLHttpRequest""", re.IGNORECASE
)
EVAL_RE = re.compile(r'\beval\s*\(')
NEW_FUNCTION_RE = re.compile(r'\bnew\s+Function\s*\(')


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_animation.py <animation-folder>")
        sys.exit(1)

    folder = sys.argv[1].rstrip("/")
    name = os.path.basename(folder)

    # 1. index.html exists
    html_path = os.path.join(folder, "index.html")
    if not os.path.isfile(html_path):
        fail(f"Missing index.html in {name}/")

    # 2. manifest.json exists and is valid JSON
    manifest_path = os.path.join(folder, "manifest.json")
    if not os.path.isfile(manifest_path):
        fail(f"Missing manifest.json in {name}/")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        fail(f"manifest.json is not valid JSON: {e}")

    # 3. Required manifest fields present and non-empty
    for field in REQUIRED_MANIFEST_FIELDS:
        if not manifest.get(field):
            fail(f"manifest.json missing or empty required field: '{field}'")

    # 4. Folder name matches manifest id
    if manifest["id"] != name:
        fail(
            f"Folder name '{name}' does not match manifest id '{manifest['id']}'. "
            f"Rename the folder or update manifest.json."
        )

    # 5. Preview file exists and has allowed extension
    preview = manifest.get("preview", "")
    preview_path = os.path.join(folder, preview)
    ext = os.path.splitext(preview)[1].lower()
    if not os.path.isfile(preview_path):
        fail(f"Preview file '{preview}' listed in manifest.json not found in {name}/")
    if ext not in ALLOWED_PREVIEW_EXTENSIONS:
        fail(
            f"Preview file must be .gif, .png, .jpg, or .jpeg — got '{ext}'"
        )

    # 6. Total folder size
    total_size = 0
    for dirpath, _, filenames in os.walk(folder):
        for fname in filenames:
            total_size += os.path.getsize(os.path.join(dirpath, fname))
    if total_size > MAX_SIZE_BYTES:
        fail(
            f"Animation folder is {total_size / 1024 / 1024:.2f} MB, "
            f"exceeds 2 MB limit."
        )

    # 7. index.html self-containment checks
    with open(html_path, encoding="utf-8", errors="replace") as f:
        html = f.read()

    if EXTERNAL_SCRIPT_RE.search(html):
        fail(
            "index.html loads a script from an external URL "
            '(<script src="https://...">). All JS must be inlined.'
        )
    if EXTERNAL_FETCH_RE.search(html):
        fail(
            "index.html calls fetch() with an external URL. "
            "Animations must be fully self-contained."
        )
    if EXTERNAL_XHR_RE.search(html):
        fail(
            "index.html uses XMLHttpRequest. "
            "Animations must be fully self-contained."
        )
    if EVAL_RE.search(html):
        fail("index.html uses eval(). This is not permitted.")
    if NEW_FUNCTION_RE.search(html):
        fail("index.html uses new Function(). This is not permitted.")

    print(f"OK: {name} passed all checks.")


if __name__ == "__main__":
    main()
