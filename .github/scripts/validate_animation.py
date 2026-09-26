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

# Manifest text is shown by the plugin (marketplace cards, the settings
# panel, and the info panel the screensaver draws over every animation), so
# it must be short plain text. The plugin renders it as plain text anyway;
# rejecting markup here keeps the catalog honest for any other consumer.
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
PARAM_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
TEXT_FIELD_LIMITS = {"name": 60, "description": 400, "author": 80}
FORBIDDEN_TEXT_RE = re.compile(r"[<>\x00-\x08\x0b-\x1f\x7f]")
PARAM_TYPES = {"range", "select"}
# URL params the plugin's viewer reserves for itself (system/viewer.js);
# an animation param with one of these names would never reach it.
RESERVED_PARAM_KEYS = {"anim", "path", "state", "screensaver", "startAt", "delayedStart"}

# The plugin's viewer draws the info panel and handles dismissal for every
# animation, and never passes `screensaver=1` down to it. Submissions still
# carrying their own copy of either are dead code at best and a second,
# conflicting info panel at worst (with older plugin versions).
LEGACY_BOILERPLATE = [
    (re.compile(r"window\.close\s*\("), "calls window.close()"),
    # Leftover `.credits-popup` CSS is harmless; code that builds one isn't.
    (re.compile(r"""(?:className\s*=|classList\.add\()\s*['"`]credits-popup"""), "builds its own credits popup"),
    (re.compile(r"""\.(?:has|get)\(\s*['"]screensaver['"]\s*\)"""), "checks the `screensaver` URL param"),
]

EXTERNAL_SCRIPT_RE = re.compile(
    r'<script[^>]+src=["\']https?://', re.IGNORECASE
)
EXTERNAL_FETCH_RE = re.compile(
    r"""fetch\s*\(\s*['"]https?://""", re.IGNORECASE
)
EXTERNAL_XHR_RE = re.compile(
    r"""XMLHttpRequest""", re.IGNORECASE
)
# Any attribute or CSS url() pointing off-box (images, stylesheets, fonts,
# iframes...). Two exceptions: plain <a href> links, which are inert inside
# the screensaver (it never lets clicks through), and Google Fonts, the one
# host the plugin lets animations reach (for the JetBrains Mono @import
# nearly every animation uses).
_OFF_BOX = r"""(?:https?:)?//(?!fonts\.(?:googleapis|gstatic)\.com/)"""
EXTERNAL_RESOURCE_RE = re.compile(
    r"""<(?!a\b)[a-z][^>]*\s(?:src|href|data|poster|srcset)\s*=\s*["']?\s*""" + _OFF_BOX
    + r"""|url\(\s*["']?\s*""" + _OFF_BOX,
    re.IGNORECASE,
)
NETWORK_API_RE = re.compile(
    r"\bnew\s+(?:WebSocket|EventSource|Worker|SharedWorker)\s*\(|\bsendBeacon\s*\(|\bimport\s*\(",
)
FILE_URL_RE = re.compile(r"file:", re.IGNORECASE)
# The plugin's viewer loads an animation before its window has its final size
# (on Wayland a window can map at 0x0), so an animation that measures the
# window once at startup can end up drawing into a 0x0 canvas forever —
# exactly how dna, fireworks, galaxy and ocean once shipped broken.
READS_WINDOW_SIZE_RE = re.compile(r"\binner(?:Width|Height)\b|\bclient(?:Width|Height)\b")
RESIZE_HANDLER_RE = re.compile(
    r"""addEventListener\(\s*['"]resize['"]|\bonresize\s*=|\bResizeObserver\b""")
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


def check_params(params):
    """The optional `params` list becomes the plugin's settings UI; a
    malformed entry breaks that animation's page (or the whole panel)."""
    if not isinstance(params, list):
        fail("manifest.json 'params' must be a list.")
    seen = set()
    for i, p in enumerate(params):
        where = f"params[{i}]"
        if not isinstance(p, dict):
            fail(f"manifest.json {where} must be an object.")
        key = p.get("key")
        if not isinstance(key, str) or not PARAM_KEY_RE.match(key):
            fail(f"manifest.json {where}.key must be a letter followed by letters, digits or '_'.")
        where = f"param '{key}'"
        if key in seen:
            fail(f"manifest.json has two params named '{key}'.")
        seen.add(key)
        if key in RESERVED_PARAM_KEYS or key.startswith("meta_"):
            fail(f"manifest.json {where}: that name is reserved by the plugin's viewer.")
        label = p.get("label", "")
        if not isinstance(label, str) or len(label) > 60 or FORBIDDEN_TEXT_RE.search(label):
            fail(f"manifest.json {where}: 'label' must be plain text of at most 60 characters.")
        kind = p.get("type")
        if kind not in PARAM_TYPES:
            fail(f"manifest.json {where}: 'type' must be one of {sorted(PARAM_TYPES)}.")
        default = p.get("defaultValue")
        if kind == "range":
            lo, hi = p.get("min"), p.get("max")
            numbers = [v for v in (lo, hi, default, p.get("step", 1))
                       if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if len(numbers) != 4:
                fail(f"manifest.json {where}: a range needs numeric min, max, defaultValue (and step, if given).")
            if not lo < hi or not lo <= default <= hi:
                fail(f"manifest.json {where}: needs min < max and min <= defaultValue <= max.")
        else:
            options = p.get("options")
            if (not isinstance(options, list) or not options
                    or not all(isinstance(o, (str, int, float)) and not isinstance(o, bool) for o in options)):
                fail(f"manifest.json {where}: a select needs a non-empty 'options' list of strings or numbers.")
            if any(isinstance(o, str) and FORBIDDEN_TEXT_RE.search(o) for o in options):
                fail(f"manifest.json {where}: options must be plain text.")
            if default not in options:
                fail(f"manifest.json {where}: defaultValue must be one of its options.")


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

    # 3b. Field shapes: the plugin builds paths, URL params and UI out of
    # these, so each has to be exactly what it expects.
    if not isinstance(manifest["id"], str) or not ID_RE.match(manifest["id"]):
        fail("manifest.json 'id' must be 1-64 characters of letters, digits, '_' or '-'.")
    for field, limit in TEXT_FIELD_LIMITS.items():
        value = manifest[field]
        if not isinstance(value, str):
            fail(f"manifest.json '{field}' must be a string.")
        if len(value) > limit:
            fail(f"manifest.json '{field}' is {len(value)} characters; the limit is {limit}.")
        if FORBIDDEN_TEXT_RE.search(value):
            fail(
                f"manifest.json '{field}' contains '<', '>' or a control character. "
                "It is shown as plain text: no HTML or markup."
            )
    if not isinstance(manifest["version"], str) or not VERSION_RE.match(manifest["version"]):
        fail("manifest.json 'version' must look like 1.0.0.")
    check_params(manifest.get("params", []))

    # 4. Folder name matches manifest id
    if manifest["id"] != name:
        fail(
            f"Folder name '{name}' does not match manifest id '{manifest['id']}'. "
            f"Rename the folder or update manifest.json."
        )

    # 5. Preview file exists and has allowed extension
    preview = manifest.get("preview", "")
    if (not isinstance(preview, str) or "/" in preview or "\\" in preview
            or preview.startswith(".")):
        fail("manifest.json 'preview' must be a plain file name inside the animation folder, e.g. preview.gif")
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
    if EXTERNAL_RESOURCE_RE.search(html):
        fail(
            "index.html loads something (an image, stylesheet, font, frame...) "
            "from another host. Animations must be fully self-contained."
        )
    if NETWORK_API_RE.search(html):
        fail(
            "index.html uses a network or code-loading API (WebSocket, "
            "EventSource, Worker, sendBeacon or import()). Animations must be "
            "fully self-contained."
        )
    if FILE_URL_RE.search(html):
        fail("index.html references a file: URL. Animations must not read local files.")
    for pattern, what in LEGACY_BOILERPLATE:
        if pattern.search(html):
            fail(
                f"index.html {what}. The plugin now provides the info panel "
                "and dismiss handling for every animation — remove your own "
                "copy (see CONTRIBUTING.md)."
            )
    if READS_WINDOW_SIZE_RE.search(html) and not RESIZE_HANDLER_RE.search(html):
        fail(
            "index.html reads the window size but never handles 'resize'. The "
            "screensaver can start before its window has its final size, so "
            "size your canvas in a resize handler (see CONTRIBUTING.md)."
        )
    if EVAL_RE.search(html):
        fail("index.html uses eval(). This is not permitted.")
    if NEW_FUNCTION_RE.search(html):
        fail("index.html uses new Function(). This is not permitted.")

    print(f"OK: {name} passed all checks.")


if __name__ == "__main__":
    main()
