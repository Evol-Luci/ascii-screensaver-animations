# Contributing an Animation

## Animation format

Each animation is a self-contained folder:

```
my-animation/
├── index.html        # The animation (required)
├── manifest.json     # Metadata and params schema (required)
└── preview.gif       # Preview image — GIF or PNG/JPG (required)
```

## manifest.json

```json
{
  "id": "my-animation",
  "name": "My Animation",
  "description": "A short human-readable description.",
  "author": "Your Name",
  "version": "1.0.0",
  "preview": "preview.gif",
  "params": []
}
```

All fields are required. `id` must match the folder name exactly.

`params` is an array of param descriptors. Each entry:

```json
{
  "key": "speed",
  "type": "range",
  "label": "Speed",
  "description": "Overall animation speed.",
  "defaultValue": 1.0,
  "min": 0.1,
  "max": 4.0,
  "step": 0.1
}
```

Supported `type` values: `"range"` (numeric: `min`, `max`, optional `step`,
`defaultValue` within range) and `"select"` (an `"options"` array of strings
or numbers; `defaultValue` must be one of them). A toggle is a `select` with
`"options": [0, 1]` (numbers) — the plugin shows it as an on/off switch.

Param `key`s are letters, digits and `_`, starting with a letter. These names
are reserved by the plugin and can't be used: `anim`, `path`, `state`,
`screensaver`, `startAt`, `delayedStart`, and anything starting with `meta_`.

`name`, `description` and `author` are shown as plain text in the plugin
(marketplace, settings panel, and the screensaver's info panel): no HTML or
`<`/`>`, at most 60 / 400 / 80 characters.

## Reading params at runtime

The plugin passes your configured values as URL query parameters. Read them
at the top of your script, falling back to your defaults:

```js
const params = new URLSearchParams(location.search);
const speed = parseFloat(params.get('speed') || '1');
const palette = params.get('palette') || 'natural';
```

## What the plugin does for you

Don't write any of this yourself — the plugin wraps every animation in its
own viewer, which:

- shows the info panel (your manifest's `name`, `description`, `author`);
- dismisses the screensaver on mouse or keyboard input and hides the cursor.

CI rejects submissions that still carry their own copy (a `window.close()`
call, code building a `credits-popup`, or a check of the `screensaver` URL
param).

Your animation runs in a sandboxed frame with no network access (except
Google Fonts) and no access to local files, so it only needs to draw.

## Self-containment & Runtime rules

Your animation MUST:
- Be entirely self-contained in `index.html` (inline all JS and CSS)
- Not load anything from another host — scripts, images, stylesheets, frames
  (Google Fonts via `@import` is the one exception; plain `<a href>` links
  are fine)
- Not use `fetch()`, `XMLHttpRequest`, `WebSocket`, `EventSource`, workers,
  `sendBeacon`, dynamic `import()`, or `file:` URLs
- Not use `eval()` or `new Function()`
- Size its canvas in a `resize` handler (or `ResizeObserver`), not just once
  at startup: the screensaver can start before its window has its final
  size, and a canvas measured at 0x0 stays blank. CI rejects animations that
  read `innerWidth`/`innerHeight` without handling `resize`.
- Have a valid, real image file for its preview: at least 200x120, actually
  a decodable image (not a text file or corrupt binary), and if it's a
  `.gif`, actually animated — multiple frames that aren't all identical.
  `preview` must be a plain file name inside your folder.
  CI checks all of this automatically (`.github/scripts/validate_animation.py`).
  It also renders your `index.html` in a real headless browser and posts a
  freshly-captured live frame in a PR comment next to your submitted
  preview — a preview that passes the automated checks but isn't actually a
  capture of *this* animation (e.g. a placeholder or an unrelated image)
  will still be obvious there, and the maintainer will ask you to fix it
  before merging.
- Fit within 2 MB total (all files combined)

## Submitting

1. Fork this repo
2. Add your animation folder to `animations/`
3. Open a pull request — do not modify `index.json`, the bot handles it
4. CI will automatically check your submission and close the PR with feedback if anything fails
5. If CI passes, a maintainer reviews and merges
