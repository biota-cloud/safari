# SAFARI Tutorials

User tutorials for the SAFARI platform. Each `.md` file is a chapter in the tutorial guide.

## Building the Tutorial PDF

```bash
# From the project root
.venv/bin/python scripts/md_to_pdf.py docs/tutorials/ --tutorial
```

This combines all numbered `.md` files into a single styled HTML with a table of contents, then opens it in the browser. Use **Cmd+P → Save as PDF** to export.

## Adding a Page

1. Create a new file following the naming convention: `NN_topic_name.md`
2. Start with an `# H1` heading (becomes the chapter title)
3. Rebuild with the command above

## File Naming Convention

| File | Chapter |
|------|---------|
| `01_getting_started.md` | Chapter 1: Getting Started |
| `02_creating_datasets.md` | Chapter 2: Creating Datasets |
| `03_labeling_images.md` | Chapter 3: Labeling Images |

Files are sorted alphabetically, so the numeric prefix controls order.
