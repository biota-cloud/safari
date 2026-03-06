#!/usr/bin/env python3
"""
md_to_pdf.py — Convert Markdown files to styled, print-ready HTML for PDF export.

Usage:
    # Single file
    python scripts/md_to_pdf.py docs/DEVELOPMENT.md

    # Tutorial mode (directory of numbered .md files → combined HTML with TOC)
    python scripts/md_to_pdf.py docs/tutorials/ --tutorial

    # Custom output path
    python scripts/md_to_pdf.py docs/DEVELOPMENT.md -o ~/Desktop/dev_guide.html

Opens the result in the default browser for Cmd+P → Save as PDF.
Requires: pandoc (brew install pandoc)
"""

import argparse
import base64
import os
import re
import subprocess
import sys
import webbrowser

# ─────────────────────────────────────────────
# Branding asset paths (relative to project root)
# ─────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_LOGO_PATH = os.path.join(_PROJECT_ROOT, "assets", "branding", "safari_logo_horizontal_inverted.png")


def _load_logo_b64() -> str:
    """Load the SAFARI horizontal logo as a base64 data URI."""
    if not os.path.exists(_LOGO_PATH):
        return ""  # Graceful fallback — no logo
    with open(_LOGO_PATH, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f'data:image/png;base64,{b64}'

# ─────────────────────────────────────────────
# Styling
# ─────────────────────────────────────────────


# ── SAFARI Design Tokens (from styles.py) ──────────────────────
# Backgrounds
_BG_PRIMARY = "#F5F0EB"       # Warm cream — main page background
_BG_SECONDARY = "#FFFFFF"     # White — cards
_BG_TERTIARY = "#F0EBE5"      # Warm hover

# Accents
_ACCENT = "#5FAD56"           # Leaf green — primary actions
_ACCENT_HOVER = "#4E9A47"
_ACCENT_MUTE = "rgba(95, 173, 86, 0.1)"

# Header
_HEADER_BG = "#352516"        # Dark chocolate brown
_HEADER_TEXT = "#FFFFFF"

# Earth tones
_EARTH_TAUPE = "#8B7355"

# Text
_TEXT_PRIMARY = "#333333"
_TEXT_SECONDARY = "#6b6b6b"

# Code
_CODE_BG = "#1E1E1E"
_CODE_TEXT = "#D4D4D4"

# Borders / Radius
_BORDER = "#D5D0CB"
_RADIUS_SM = "4px"
_RADIUS_MD = "6px"
_RADIUS_LG = "8px"

# Icon Mark SVG (inline, for embedding in HTML)
ICON_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" width="40" height="40" style="vertical-align: middle;">
  <path d="M 18 12 L 8 12 L 8 68 L 18 68" fill="none" stroke="#352516" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="40" cy="42" r="12" fill="#6BBF59"/>
  <path d="M 62 12 L 72 12 L 72 68 L 62 68" fill="none" stroke="#352516" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

ICON_MARK_SVG_LIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" width="40" height="40" style="vertical-align: middle;">
  <path d="M 18 12 L 8 12 L 8 68 L 18 68" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="40" cy="42" r="12" fill="#6BBF59"/>
  <path d="M 62 12 L 72 12 L 72 68 L 62 68" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {{
    --accent: {_ACCENT};
    --accent-hover: {_ACCENT_HOVER};
    --accent-mute: {_ACCENT_MUTE};
    --header-bg: {_HEADER_BG};
    --header-text: {_HEADER_TEXT};
    --bg-primary: {_BG_PRIMARY};
    --bg-secondary: {_BG_SECONDARY};
    --bg-tertiary: {_BG_TERTIARY};
    --text-primary: {_TEXT_PRIMARY};
    --text-secondary: {_TEXT_SECONDARY};
    --border: {_BORDER};
    --earth-taupe: {_EARTH_TAUPE};
    --code-bg: {_CODE_BG};
    --code-text: {_CODE_TEXT};
}}

@media print {{
    body {{ font-size: 11pt; }}
    .toc-page, .chapter {{ page-break-before: always; }}
    .chapter:first-of-type {{ page-break-before: avoid; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; }}
    a {{ color: var(--text-primary); text-decoration: none; }}
    .no-print {{ display: none; }}
    .cover {{ page-break-after: always; }}
}}

@page {{
    margin: 2cm 2.5cm;
    @bottom-center {{ content: counter(page); font-size: 9pt; color: #999; }}
}}

* {{ box-sizing: border-box; }}

body {{
    font-family: 'Poppins', system-ui, -apple-system, sans-serif;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px 20px;
    font-size: 14px;
    color: var(--text-primary);
    line-height: 1.7;
    background: var(--bg-secondary);
}}

/* ── Typography ── */
h1 {{
    font-size: 28px;
    font-weight: 600;
    border-bottom: 2px solid var(--accent);
    padding-bottom: 10px;
    margin-top: 0;
    color: var(--header-bg);
}}

h2 {{
    font-size: 20px;
    font-weight: 500;
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
    margin-top: 32px;
    color: var(--header-bg);
}}

h3 {{
    font-size: 16px;
    font-weight: 600;
    margin-top: 24px;
    color: var(--text-primary);
}}

h4 {{ font-size: 14px; font-weight: 600; margin-top: 20px; }}

p {{ margin: 12px 0; }}

a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; color: var(--accent-hover); }}

/* ── Code ── */
code {{
    font-family: 'JetBrains Mono', 'SF Mono', 'Menlo', monospace;
    background: var(--bg-tertiary);
    padding: 2px 6px;
    border-radius: {_RADIUS_SM};
    font-size: 12.5px;
    color: var(--header-bg);
}}

pre {{
    background: var(--code-bg);
    color: var(--code-text);
    padding: 16px 20px;
    border-radius: {_RADIUS_LG};
    overflow-x: auto;
    font-size: 12px;
    line-height: 1.5;
}}

pre code {{
    background: none;
    padding: 0;
    border-radius: 0;
    color: inherit;
}}

/* ── Tables ── */
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 13px;
}}

th, td {{
    border: 1px solid var(--border);
    padding: 8px 12px;
    text-align: left;
}}

th {{
    background: var(--bg-tertiary);
    font-weight: 600;
    color: var(--header-bg);
}}

tr:nth-child(even) {{ background: var(--bg-primary); }}

/* ── Blockquotes / alerts ── */
blockquote {{
    border-left: 4px solid var(--accent);
    margin: 16px 0;
    padding: 10px 16px;
    background: var(--accent-mute);
    border-radius: 0 {_RADIUS_MD} {_RADIUS_MD} 0;
    color: var(--text-secondary);
}}

/* ── Horizontal rules ── */
hr {{
    border: none;
    border-top: 1px solid var(--border);
    margin: 28px 0;
}}

/* ── Lists ── */
ul, ol {{ padding-left: 24px; }}
li {{ margin: 4px 0; }}

/* ── Cover page (tutorial mode) ── */
.cover {{
    text-align: center;
    padding: 120px 0 40px;
}}

.cover .logo {{
    margin-bottom: 32px;
}}

.cover h1 {{
    font-size: 36px;
    font-weight: 600;
    border: none;
    margin-bottom: 8px;
    color: var(--header-bg);
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}

.cover .subtitle {{
    font-size: 16px;
    font-weight: 300;
    color: var(--text-secondary);
    margin-bottom: 40px;
}}

.cover .brand-line {{
    width: 60px;
    height: 3px;
    background: var(--accent);
    margin: 24px auto;
    border-radius: 2px;
}}

/* ── TOC ── */
.toc-page h2 {{
    border-bottom: 2px solid var(--accent);
    margin-bottom: 20px;
}}

.toc-list {{
    list-style: none;
    padding: 0;
}}

.toc-list li {{
    padding: 10px 0;
    border-bottom: 1px solid var(--bg-tertiary);
    font-size: 15px;
}}

.toc-list li a {{
    display: flex;
    align-items: center;
    color: var(--text-primary);
    text-decoration: none;
}}

.toc-list li a:hover {{
    color: var(--accent);
}}

.toc-list .chapter-num {{
    font-weight: 600;
    color: var(--accent);
    min-width: 36px;
}}

.toc-list .chapter-title {{ flex: 1; }}

/* ── Chapter headings ── */
.chapter h1 {{
    font-size: 26px;
    color: var(--accent);
    border-bottom-color: var(--accent);
}}

/* ── Footer ── */
.page-footer {{
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    text-align: center;
    font-size: 11px;
    color: var(--earth-taupe);
}}
"""


def run_pandoc(md_path: str) -> str:
    """Convert a single markdown file to an HTML fragment via pandoc."""
    result = subprocess.run(
        [
            "pandoc", md_path,
            "-t", "html5",
            "--no-highlight",
            "--wrap=none",
            "--ext", "tables+fenced_code_blocks+backtick_code_blocks",
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def extract_title(md_path: str) -> str:
    """Extract the first H1 from a markdown file, or derive from filename."""
    with open(md_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
    # Fallback: derive from filename
    name = os.path.splitext(os.path.basename(md_path))[0]
    # Strip leading numbers: "01_getting_started" → "Getting Started"
    name = re.sub(r"^\d+[_\-]\s*", "", name)
    return name.replace("_", " ").replace("-", " ").title()


def build_single(md_path: str, output: str | None = None) -> str:
    """Convert a single markdown file to a styled HTML document."""
    title = extract_title(md_path)
    body_html = run_pandoc(md_path)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
{body_html}
<div class="page-footer">
    {ICON_MARK_SVG.replace('width="40" height="40"', 'width="20" height="20"')}
    <span style="margin-left: 6px;">SAFARI — Biota Cloud</span>
</div>
</body>
</html>"""

    if output is None:
        output = os.path.splitext(md_path)[0] + ".html"

    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    return output


def build_tutorial(directory: str, output: str | None = None, title: str | None = None) -> str:
    """Combine a directory of numbered .md files into a single HTML with TOC."""
    # Discover markdown files, sorted by name
    md_files = sorted(
        f for f in os.listdir(directory)
        if f.endswith(".md") and f.lower() != "readme.md"
    )

    if not md_files:
        print(f"❌ No .md files found in {directory}", file=sys.stderr)
        sys.exit(1)

    # Extract chapters
    chapters = []
    for i, filename in enumerate(md_files, 1):
        md_path = os.path.join(directory, filename)
        chapter_title = extract_title(md_path)
        chapter_html = run_pandoc(md_path)
        slug = re.sub(r"[^a-z0-9]+", "-", chapter_title.lower()).strip("-")
        chapters.append({
            "num": i,
            "title": chapter_title,
            "slug": slug,
            "html": chapter_html,
            "filename": filename,
        })

    # Derive tutorial title
    if title is None:
        title = os.path.basename(os.path.normpath(directory)).replace("_", " ").replace("-", " ").title()
        title = f"SAFARI — {title}"

    # Build TOC
    toc_items = "\n".join(
        f'<li><a href="#{ch["slug"]}">'
        f'<span class="chapter-num">{ch["num"]}.</span>'
        f'<span class="chapter-title">{ch["title"]}</span></a></li>'
        for ch in chapters
    )

    # Build chapter sections
    chapter_sections = "\n".join(
        f'<div class="chapter" id="{ch["slug"]}">\n{ch["html"]}\n</div>'
        for ch in chapters
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>

<div class="cover">
    <div class="logo"><img src="{_load_logo_b64()}" alt="SAFARI" style="height: 80px;"></div>
    <h1>{title}</h1>
    <div class="brand-line"></div>
    <p class="subtitle">User Guide</p>
</div>

<div class="toc-page">
    <h2>Table of Contents</h2>
    <ol class="toc-list">
        {toc_items}
    </ol>
</div>

{chapter_sections}

<div class="page-footer">
    {ICON_MARK_SVG.replace('width="40" height="40"', 'width="20" height="20"')}
    <span style="margin-left: 6px;">SAFARI — Biota Cloud</span>
</div>
</body>
</html>"""

    if output is None:
        output = os.path.join(directory, "tutorial.html")

    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Convert Markdown to styled, print-ready HTML for PDF export.",
        epilog="Opens the result in the browser. Use Cmd+P → Save as PDF.",
    )
    parser.add_argument("input", help="Markdown file or directory (with --tutorial)")
    parser.add_argument("-o", "--output", help="Output HTML path (default: alongside input)")
    parser.add_argument(
        "--tutorial", action="store_true",
        help="Tutorial mode: combine numbered .md files from a directory into one HTML with TOC",
    )
    parser.add_argument("--title", help="Override the tutorial title (tutorial mode only)")
    parser.add_argument(
        "--no-open", action="store_true",
        help="Don't open the result in the browser",
    )

    args = parser.parse_args()

    # Verify pandoc is installed
    if subprocess.run(["which", "pandoc"], capture_output=True).returncode != 0:
        print("❌ pandoc is not installed. Install with: brew install pandoc", file=sys.stderr)
        sys.exit(1)

    if args.tutorial:
        if not os.path.isdir(args.input):
            print(f"❌ --tutorial requires a directory, got: {args.input}", file=sys.stderr)
            sys.exit(1)
        output = build_tutorial(args.input, args.output, args.title)
    else:
        if not os.path.isfile(args.input):
            print(f"❌ File not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        output = build_single(args.input, args.output)

    abs_output = os.path.abspath(output)
    print(f"✅ HTML saved to: {abs_output}")

    if not args.no_open:
        webbrowser.open(f"file://{abs_output}")
        print("📄 Opened in browser. Press Cmd+P → Save as PDF.")


if __name__ == "__main__":
    main()
