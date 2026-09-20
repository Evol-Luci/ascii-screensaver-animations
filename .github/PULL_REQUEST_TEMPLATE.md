## Animation submission checklist

- [ ] My animation folder is inside `animations/` and the folder name matches the `id` in `manifest.json`
- [ ] `index.html` is present and self-contained (no external scripts, no fetch to external domains, no eval)
- [ ] `manifest.json` is present and all required fields are filled in (`id`, `name`, `description`, `author`, `version`, `preview`)
- [ ] A preview image (GIF or PNG/JPG) is present and named correctly in `manifest.json`
- [ ] Total folder size is under 2 MB
- [ ] I have NOT modified `index.json` (the bot updates it on merge)
