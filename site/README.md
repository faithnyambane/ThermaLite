# ThermaLite Siting — website

A static website: one HTML file plus three data files. No build step or server code.

| File | What it is |
|---|---|
| `index.html` | The whole site: map, guide, about, guided tour. Valid HTML (W3C Nu validator and html-validate). |
| `data-va.json`, `data-tx.json`, `data-nc.json` | Scored 2 km grid for Virginia, Texas and North Carolina, produced by `thermalite site` + `thermalite.siting_ui.pack`. |

## Run it locally

The page loads its data with `fetch`, so open it through a web server, not by double-clicking:

```bash
cd site
python3 -m http.server 8000
# then open http://localhost:8000
```

## Host it

Any static host works. For GitHub Pages: push the repo, then in the repository settings set Pages to deploy from the `site/` folder.

## Light and dark mode

The header switch offers Auto (follows the device setting), Light and Dark. The choice is remembered in the browser.

## Check it

```bash
npx html-validate site/index.html                  # HTML validity + accessibility rules
node tests/check_ui_data.js site                   # data files match what the page expects
NODE_PATH=<dir with jsdom> node tests/ui_e2e.js site   # 80+ end-to-end checks in a simulated browser
```

## Publish the claude.ai version

`python3 tools/build_artifact.py` writes `out/siting/ui/index.html` (the same page without the outer document, which the artifact host adds) and copies the data files next to it.
