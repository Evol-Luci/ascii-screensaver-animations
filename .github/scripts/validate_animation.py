#!/usr/bin/env python3
"""Validate a single animation folder for PR submission.

Usage: python validate_animation.py <path/to/animation-folder>
Exits 0 on success, 1 on failure (prints reason to stdout).
"""

import json
import os
import re
import statistics
import sys

try:
    from PIL import Image, ImageSequence
except ImportError:
    Image = None


MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
REQUIRED_MANIFEST_FIELDS = ["id", "name", "description", "author", "version", "preview"]
ALLOWED_PREVIEW_EXTENSIONS = {".gif", ".png", ".jpg", ".jpeg"}

# A submission has twice now shipped a preview that technically satisfied
# "file exists, has an allowed extension" while being useless: first a
# plain-text file with a .gif name, then a real-but-1x1-transparent GIF.
# These thresholds are deliberately loose (calibrated against every
# animation already in this repo, real and previously-fake) — the goal is
# to reject only unambiguously degenerate previews, not to referee whether
# a preview "looks good".
MIN_PREVIEW_WIDTH = 200
MIN_PREVIEW_HEIGHT = 120
MIN_LUMINANCE_STDDEV = 1.0  # rejects a single flat/solid-color image

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


def check_preview_image(path, ext):
    """Structural sanity checks on an image file. Returns None if OK, or a
    human-readable problem description. Deliberately does NOT try to judge
    whether the image looks "good" or matches any particular content —
    only whether it's a real, non-degenerate image at all. Shared with
    render_preview.py, which runs these same checks against a freshly
    rendered live frame of the submitted animation.
    """
    try:
        im = Image.open(path)
        im.verify()
        im = Image.open(path)  # verify() invalidates the handle; reopen
    except Exception as e:
        return f"'{path}' could not be opened as an image: {e}"

    width, height = im.size
    if width < MIN_PREVIEW_WIDTH or height < MIN_PREVIEW_HEIGHT:
        return (
            f"'{path}' is {width}x{height}, smaller than the "
            f"{MIN_PREVIEW_WIDTH}x{MIN_PREVIEW_HEIGHT} minimum. "
            "(A 1x1 placeholder image has shipped here before — this is "
            "the check that would have caught it.)"
        )

    frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    n_frames = len(frames)

    if ext == ".gif" and n_frames < 2:
        return (
            f"'{path}' is a .gif with only {n_frames} frame — it isn't "
            "actually animated. Either make it a real multi-frame "
            "animation, or submit a static preview as .png/.jpg instead."
        )

    if n_frames > 1:
        first_bytes = frames[0].tobytes()
        if all(f.tobytes() == first_bytes for f in frames[1:]):
            return (
                f"'{path}' has {n_frames} frames but they're all identical "
                "— this isn't actually animated."
            )

    stddevs = [statistics.pstdev(f.convert("L").tobytes()) for f in frames]
    if max(stddevs) < MIN_LUMINANCE_STDDEV:
        return (
            f"'{path}' appears to be a blank or solid-color image "
            f"(max luminance stddev {max(stddevs):.2f} across {n_frames} "
            f"frame(s), minimum is {MIN_LUMINANCE_STDDEV})."
        )

    return None


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

    # 5b. Preview must actually be a real, non-degenerate image. This is the
    # check that would have caught this repo's two previous preview
    # failures: a plain-text file saved as "preview.gif", and later a real
    # but 1x1 fully-transparent GIF. Neither failed check 5 above.
    if Image is None:
        fail(
            "Pillow is not installed in this environment — cannot validate "
            "preview image content. Install it with `pip install pillow`."
        )
    problem = check_preview_image(preview_path, ext)
    if problem:
        fail(problem)

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
