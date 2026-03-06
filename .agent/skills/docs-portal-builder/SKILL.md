---
name: docs-portal-builder
description: Use this skill when editing onboarding documentation content, adding new portal pages, modifying portal styling/layout, or rebuilding the documentation portal. Activates for docs/onboard/ changes, build.py modifications, or screenshot additions.
---

# Documentation Portal Builder

The SAFARI documentation portal is a static site generated from Markdown content via `docs/onboard/build.py`.

## Architecture

```
docs/onboard/
├── content/              # Markdown source pages (00_index.md → 10_development.md)
├── assets/
│   └── screenshots/      # Screenshot PNGs referenced by content pages
└── build.py              # Static site generator (Pandoc + custom template)

assets/onboard/           # ← Generated output (served by Reflex at /onboard/)
├── index.html
├── 01_getting-started.html
├── ...
└── screenshots/
```

## Build Command

```bash
# Build and open in browser
python docs/onboard/build.py

# Build only (CI/headless)
python docs/onboard/build.py --no-open
```

## Adding a New Page

1. Create `docs/onboard/content/NN_slug.md` (prefix number controls sort order)
2. Start with an H1 title and a blockquote subtitle (used as card description on index):
   ```markdown
   # Page Title

   > Short description used on the index card grid.
   ```
3. Register the page in `build.py`:
   - Add the stem to `USER_GUIDE_PAGES` or `TECHNICAL_PAGES` list
   - Add a Lucide icon name in the `PAGE_ICONS` dict
4. Run `python docs/onboard/build.py --no-open`

## Adding Screenshots

1. Place PNGs in `docs/onboard/assets/screenshots/`
2. Reference in markdown: `![Caption text](screenshots/Filename.png)`
3. **Compact screenshots** (modals, cards, dropdowns): filenames matching `/modal|card|dropdown|popover|menu|results|compact|key_|confirmation/` auto-get `max-width: 420px`
4. Pandoc generates `<figure>` + `<figcaption>` — captions render centered and italic

## Key Features

| Feature | Implementation |
|---------|---------------|
| **Sidebar navigation** | Auto-generated from page list + H2 anchors |
| **Index card grid** | Auto-generated from page blockquote subtitles |
| **Mermaid diagrams** | Client-side rendering via Mermaid JS v11 (neutral theme, SAFARI colors) |
| **Inline icon buttons** | `<span class="icon-btn">` with Lucide icons — see existing pages for patterns |
| **Image placeholders** | Runtime restoration of Reflex-replaced `<img>` tags |
| **Prev/Next navigation** | Auto-generated page-level navigation at bottom |

## Styling

All CSS is embedded in `build.py` as `PORTAL_CSS`. Key design tokens:

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#faf7f2` | Page background |
| `--header-bg` | `#2d2a26` | Header bar |
| `--accent` | `#8B7355` | Links, active states |
| `--text-primary` | `#2d2a26` | Body text |
| `--border` | `#d4cdc4` | Cards, images |

## Mermaid Diagrams

Use standard fenced code blocks with `mermaid` language. The build system auto-converts Pandoc's `<pre class="mermaid"><code>` output to `<div class="mermaid">` for client-side rendering.

```markdown
\`\`\`mermaid
flowchart TB
    A["Node A"] --> B["Node B"]
\`\`\`
```

Theme uses SAFARI brand colors (warm browns/tans) via `themeVariables` in the Mermaid init config.

## Content Pages Reference

| # | File | Section | Content |
|---|------|---------|---------|
| 00 | `00_index.md` | — | Welcome page (card grid auto-generated) |
| 01 | `01_getting-started.md` | User Guide | Login, dashboard, project creation |
| 02 | `02_image-labeling.md` | User Guide | Bounding box editor |
| 03 | `03_video-labeling.md` | User Guide | Keyframe annotation |
| 04 | `04_autolabeling.md` | User Guide | SAM3/YOLO auto-annotation |
| 05 | `05_training.md` | User Guide | Model training dashboard |
| 06 | `06_playground.md` | User Guide | Inference playground |
| 07 | `07_api.md` | User Guide | REST API access |
| 08 | `08_architecture.md` | Technical | System design (Mermaid diagrams) |
| 09 | `09_deployment.md` | Technical | Production VPS setup |
| 10 | `10_development.md` | Technical | Local dev environment |
