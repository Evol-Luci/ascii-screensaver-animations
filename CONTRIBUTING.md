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

Supported `type` values: `"range"`, `"select"`, `"boolean"`.

For `"select"` params, include an `"options"` array of strings.

## Reading params at runtime

The plugin injects params into your animation via `window.animationParams`. At page load, read it like this:

```js
const params = window.animationParams || {};
const speed = params.speed ?? 1.0;
```

The plugin writes your configured values into `window.animationParams` before the page finishes loading, so reading it synchronously at the top of your script is safe.

## Self-containment & Runtime rules

Your animation MUST:
- Be entirely self-contained in `index.html` (inline all JS and CSS)
- Not load scripts from external URLs (`<script src="https://...">` is rejected)
- Not call `fetch()` or `XMLHttpRequest` to external domains
- Not use `eval()` or `new Function()`
- Have a valid, real image file for its preview (a corrupt or placeholder text file will crash the QML UI renderer)
- Fit within 2 MB total (all files combined)
- Include the following snippet at the end of your script to properly close the screensaver on mouse or keyboard movement:

```js
// ─── Screensaver Dismiss Logic ────────────────────────────────────────────────
if (new URLSearchParams(window.location.search).get('screensaver') === '1') {
    let armed = false;
    setTimeout(() => { armed = true; }, 1500);
    const dismiss = () => {
        if (!armed) return;
        try { window.close(); } catch(e) {}
        document.body.innerHTML = '';
        document.body.style.background = '#000';
    };
    window.addEventListener('keydown', dismiss);
    window.addEventListener('mousedown', dismiss);
    window.addEventListener('mousemove', (() => {
        let lastX = -1, lastY = -1, moveCount = 0;
        return (e) => {
            if (lastX === -1) { lastX = e.clientX; lastY = e.clientY; return; }
            if (e.clientX === lastX && e.clientY === lastY) return;
            lastX = e.clientX; lastY = e.clientY;
            if (++moveCount > 10) dismiss();
        };
    })());
}
```

## Submitting

1. Fork this repo
2. Add your animation folder to `animations/`
3. Open a pull request — do not modify `index.json`, the bot handles it
4. CI will automatically check your submission and close the PR with feedback if anything fails
5. If CI passes, a maintainer reviews and merges
