#!/usr/bin/env python3
"""Render an animation's index.html in a real headless browser and check
that it actually produces visible, moving output — independent of whatever
preview.gif was submitted alongside it.

This exists because validate_animation.py's checks on the *submitted*
preview file can't tell a genuine capture apart from a plausible-looking
fabrication (multi-frame, non-flat, but drawn by hand and unrelated to what
index.html actually renders — this has happened here before). Rendering
the real thing and checking *that* closes part of the gap; the rest is
closed by posting a live-rendered frame in the PR for a human to eyeball
next to the submitted preview.

Usage: python render_preview.py <path/to/animation-folder> <output-dir>
Writes <output-dir>/live_preview.png (a representative live frame) and
<output-dir>/live_frames/*.png (the raw sampled frames).
Exits 0 if the live render looks like real, moving output; 1 otherwise
(reason printed to stdout). Requires `pip install playwright` and
`playwright install chromium` beforehand.
"""

import json
import os
import sys
import statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_animation import check_preview_image  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


SETTLE_SECONDS = 3.0     # let fade-ins / initial setup finish
FRAME_COUNT = 8
FRAME_INTERVAL_MS = 350
VIEWPORT = {"width": 960, "height": 540}


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def capture_frames(html_path):
    """Returns a list of raw PNG screenshots of the whole page sampled over a
    few real seconds. Screenshots rather than canvas.toDataURL(): an
    animation may layer several canvases (e.g. a static backdrop under a
    moving one) plus CSS, and sampling just the first <canvas> would judge
    it by whichever layer happens to come first in the DOM."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(f"file://{html_path}")
        page.wait_for_timeout(int(SETTLE_SECONDS * 1000))
        frames = []
        for _ in range(FRAME_COUNT):
            frames.append(page.screenshot(type="png"))
            page.wait_for_timeout(FRAME_INTERVAL_MS)
        browser.close()
    return frames


def main():
    if len(sys.argv) != 3:
        print("Usage: render_preview.py <animation-folder> <output-dir>")
        sys.exit(1)

    if sync_playwright is None:
        fail("playwright is not installed — `pip install playwright && "
             "playwright install chromium` first.")

    folder = os.path.abspath(sys.argv[1].rstrip("/"))
    out_dir = sys.argv[2]
    name = os.path.basename(folder)
    html_path = os.path.join(folder, "index.html")

    if not os.path.isfile(html_path):
        fail(f"No index.html in {folder}")

    frames = capture_frames(html_path)
    if not frames:
        fail(f"{name}/index.html produced zero frames — did it load at all?")
    if all(f == frames[0] for f in frames[1:]):
        fail(
            f"{name}'s live render didn't change over "
            f"{FRAME_COUNT * FRAME_INTERVAL_MS / 1000:.1f}s — it isn't animating "
            "(or it drew into a canvas that never got a size)."
        )

    frames_dir = os.path.join(out_dir, "live_frames")
    os.makedirs(frames_dir, exist_ok=True)
    for i, data in enumerate(frames):
        with open(os.path.join(frames_dir, f"frame{i:02d}.png"), "wb") as f:
            f.write(data)

    # Check all frames for validity — animations like thunderstorm have
    # intermittent activity (lightning), so the last frame might be dark.
    # Use the frame with the highest luminance stddev as the representative.
    best_frame_idx = -1
    best_stddev = -1.0
    for i, data in enumerate(frames):
        frame_path = os.path.join(frames_dir, f"frame{i:02d}.png")
        problem = check_preview_image(frame_path, ".png")
        if problem is None:
            # Frame passes; compute its stddev to pick the "best" one
            from PIL import Image
            im = Image.open(frame_path).convert("L")
            stddev = statistics.pstdev(im.tobytes())
            if stddev > best_stddev:
                best_stddev = stddev
                best_frame_idx = i

    if best_frame_idx == -1:
        # No frame passed — fail with the last frame's error for clarity
        last_frame_path = os.path.join(frames_dir, f"frame{len(frames)-1:02d}.png")
        problem = check_preview_image(last_frame_path, ".png")
        fail(f"{name}'s live render looks broken: {problem}")

    # Use the best frame for the PR comment preview
    live_preview_path = os.path.join(out_dir, "live_preview.png")
    with open(live_preview_path, "wb") as f:
        f.write(frames[best_frame_idx])

    print(json.dumps({
        "ok": True,
        "name": name,
        "live_preview": live_preview_path,
        "frame_count": len(frames),
    }))


if __name__ == "__main__":
    main()
