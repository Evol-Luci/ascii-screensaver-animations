#!/usr/bin/env python3
"""Orchestrates PR validation for changed animation folders and produces a
single markdown PR comment covering all of them.

Runs, per changed folder:
  1. validate_animation.py  — structural checks on the *submitted* preview
     (real image, big enough, actually animated if .gif, not blank).
  2. render_preview.py      — renders the *actual* index.html in a headless
     browser and checks that IT produces real, moving output too.

Neither of those can reliably tell whether the submitted preview is a
genuine capture of *this* animation specifically (rather than a plausible
but unrelated fabrication) — see AGENTS-equivalent notes in this repo's
CONTRIBUTING.md. So this also embeds a freshly live-rendered frame in the
PR comment, next to the submitted preview, so a human reviewer can just
look at both and tell.

Usage: python validate_pr.py <file with one animation folder path per line>
Prints the markdown comment body to stdout. Exits 1 if any folder failed
either check (0 otherwise).
"""

import base64
import io
import os
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# GitHub comment body limit
MAX_COMMENT_CHARS = 65536

try:
    from PIL import Image
except ImportError:
    Image = None


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def embed_image(path, max_width=200, quality=50):
    """Small base64 data-URI <img>, downscaled to keep the PR comment size
    reasonable regardless of how many folders changed in one PR."""
    if Image is None or not os.path.isfile(path):
        return ""
    im = Image.open(path).convert("RGB")
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f'<img src="data:image/jpeg;base64,{b64}" width="{max_width}">'


def submitted_preview_path(folder):
    manifest_path = os.path.join(folder, "manifest.json")
    if not os.path.isfile(manifest_path):
        return None
    import json
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError:
        return None
    preview = manifest.get("preview", "")
    path = os.path.join(folder, preview)
    return path if os.path.isfile(path) else None


def process_folder(folder):
    name = os.path.basename(folder.rstrip("/"))
    struct_code, struct_output = run(["python3", os.path.join(SCRIPT_DIR, "validate_animation.py"), folder])

    with tempfile.TemporaryDirectory() as render_dir:
        render_code, render_output = run(
            ["python3", os.path.join(SCRIPT_DIR, "render_preview.py"), folder, render_dir]
        )
        live_preview = os.path.join(render_dir, "live_preview.png")
        live_img_html = embed_image(live_preview) if render_code == 0 else ""

        preview_path = submitted_preview_path(folder)
        submitted_img_html = embed_image(preview_path) if preview_path else ""

        ok = struct_code == 0 and render_code == 0

        lines = [f"### {'✅' if ok else '❌'} `{name}`", ""]
        if struct_code != 0:
            lines.append(f"**Submitted preview failed validation:**\n```\n{struct_output}\n```\n")
        if render_code != 0:
            lines.append(f"**Live render failed validation:**\n```\n{render_output}\n```\n")

        if submitted_img_html or live_img_html:
            lines.append("| Submitted preview | Live-rendered frame (just now, in CI) |")
            lines.append("|---|---|")
            lines.append(f"| {submitted_img_html or '_(none)_'} | {live_img_html or '_(render failed)_'} |")
            lines.append("")
            lines.append(
                "_Compare these two columns before merging — this is the check that "
                "actually verifies the preview shows this animation, not just that it's "
                "a valid image file._"
            )

        return ok, "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_pr.py <folders-file>", file=sys.stderr)
        sys.exit(2)

    with open(sys.argv[1]) as f:
        folders = [line.strip() for line in f if line.strip()]

    if not folders:
        print("No `animations/*` folders changed by this PR.")
        sys.exit(0)

    all_ok = True
    sections = []
    for folder in folders:
        ok, section = process_folder(folder)
        all_ok = all_ok and ok
        sections.append(section)

    header = "## Animation validation" + ("" if all_ok else " — failed")
    body = header + "\n\n" + "\n\n---\n\n".join(sections)

    # Truncate if exceeds GitHub's comment limit
    if len(body) > MAX_COMMENT_CHARS:
        truncated = body[:MAX_COMMENT_CHARS - 200]
        # Find last complete section
        last_sep = truncated.rfind("\n\n---\n\n")
        if last_sep > 0:
            truncated = truncated[:last_sep]
        body = truncated + "\n\n... (comment truncated — exceeds GitHub's 65536 char limit)"

    print(body)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
