---
name: md-to-pdf
description: Use this skill when building user tutorials, converting markdown documentation to PDF, or creating multi-page tutorial guides. Activates for docs/tutorials/ changes, PDF export requests, or tutorial authoring tasks.
---

# MD-to-PDF Tutorial Builder Skill

## Goal
Convert markdown documentation into styled, print-ready HTML that can be saved as PDF via the browser. Supports both single-file export and multi-page tutorial assembly with an auto-generated Table of Contents.

## When to Use
- Exporting any markdown file as a PDF
- Building or updating user tutorials in `docs/tutorials/`
- Creating multi-page documentation guides
- Generating printable versions of docs

## Prerequisites
- **pandoc** must be installed (`brew install pandoc`)
- No Python pip dependencies required (uses only stdlib + pandoc)

## Commands

### Single File Export
```bash
.venv/bin/python scripts/md_to_pdf.py docs/DEVELOPMENT.md
```
Opens a styled HTML in the browser → **Cmd+P → Save as PDF**.

### Tutorial Mode (Multi-Page with TOC)
```bash
.venv/bin/python scripts/md_to_pdf.py docs/tutorials/ --tutorial
```
Combines all numbered `.md` files into a single HTML with cover page, table of contents, and chapter page breaks.

### Options
| Flag | Description |
|------|-------------|
| `-o PATH` | Custom output path |
| `--title "My Title"` | Override the auto-derived tutorial title |
| `--no-open` | Don't auto-open in browser |

## Tutorial Directory Convention

Place numbered markdown files in `docs/tutorials/`:

```
docs/tutorials/
├── README.md              ← Not included in output
├── 01_getting_started.md  ← Chapter 1
├── 02_creating_datasets.md
├── 03_labeling_images.md
├── 04_training_models.md
└── 05_running_inference.md
```

### Naming Rules
1. **Prefix with a number** for ordering: `01_`, `02_`, etc.
2. **Use underscores** to separate words in filenames
3. **Start each file with an `# H1` heading** — this becomes the chapter title in the TOC
4. `README.md` is always excluded from the output

### Chapter Title Resolution
- If the file starts with `# Title`, that title is used
- Otherwise, the filename is cleaned up: `03_labeling_images.md` → "Labeling Images"

## Adding a New Tutorial Page

1. Create a new numbered `.md` file in `docs/tutorials/`:
   ```bash
   touch docs/tutorials/06_using_the_api.md
   ```
2. Start the file with a heading:
   ```markdown
   # Using the API
   Your content here...
   ```
3. Rebuild:
   ```bash
   .venv/bin/python scripts/md_to_pdf.py docs/tutorials/ --tutorial
   ```

## Branding

The output uses the **SAFARI Naturalist Design System** (sourced from `styles.py`):

| Token | Value | Usage |
|-------|-------|-------|
| `BG_PRIMARY` | `#F5F0EB` (warm cream) | Table alternating rows |
| `ACCENT` | `#5FAD56` (leaf green) | Links, TOC numbers, accent lines |
| `HEADER_BG` | `#352516` (chocolate brown) | Headings |
| `TEXT_PRIMARY` | `#333333` | Body text |
| `TEXT_SECONDARY` | `#6b6b6b` | Subtitles, blockquotes |
| `CODE_BG` / `CODE_TEXT` | `#1E1E1E` / `#D4D4D4` | Code blocks |
| `BORDER` | `#D5D0CB` | Table borders, dividers |

Additional branding:
- **Font**: Poppins (body + headings) / JetBrains Mono (code)
- **Cover page**: Embedded inline SVG of the `[●]` icon mark (`assets/branding/safari_icon_mark.svg`)
- **Footer**: Small icon mark + "SAFARI — Biota Cloud" on every output
- **Print**: `@media print` rules with page breaks between chapters

> [!TIP]
> If the SAFARI brand tokens change in `styles.py`, update the corresponding `_*` constants at the top of `scripts/md_to_pdf.py`.

## Resources
- [md_to_pdf.py](file:///Users/jorge/PycharmProjects/Tyto/scripts/md_to_pdf.py) — the conversion script
- [styles.py](file:///Users/jorge/PycharmProjects/Tyto/styles.py) — design system source of truth
- [Branding assets](file:///Users/jorge/PycharmProjects/Tyto/assets/branding/) — logos and icon marks
- [Tutorial directory](file:///Users/jorge/PycharmProjects/Tyto/docs/tutorials/) — where tutorial pages live
