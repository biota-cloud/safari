#!/usr/bin/env python3
"""
build.py — Build the SAFARI Onboarding Documentation Portal.

Reads markdown files from docs/onboard/content/, converts them to HTML via
pandoc, wraps each in a shared template with sidebar navigation, and writes
the output to assets/onboard/ for Reflex static serving.

Usage:
    python docs/onboard/build.py              # Build + open index in browser
    python docs/onboard/build.py --no-open    # Build only (for CI / scripting)

Requires: pandoc (brew install pandoc)
"""

import os
import re
import shutil
import sys
import webbrowser

# ── Path resolution ──────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", ".."))
_CONTENT_DIR = os.path.join(_SCRIPT_DIR, "content")
_SCREENSHOTS_SRC = os.path.join(_SCRIPT_DIR, "assets", "screenshots")
_BRANDING_SRC = os.path.join(_SCRIPT_DIR, "assets", "branding")
_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "assets", "onboard")

# ── Import shared utilities from md_to_pdf ───────────────────────────────────
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "scripts"))
from md_to_pdf import (  # noqa: E402
    run_pandoc,
    extract_title,
    ICON_MARK_SVG,
    ICON_MARK_SVG_LIGHT,
    _load_logo_b64,
    _ACCENT,
    _ACCENT_HOVER,
    _ACCENT_MUTE,
    _BG_PRIMARY,
    _BG_SECONDARY,
    _BG_TERTIARY,
    _BORDER,
    _CODE_BG,
    _CODE_TEXT,
    _EARTH_TAUPE,
    _HEADER_BG,
    _HEADER_TEXT,
    _RADIUS_LG,
    _RADIUS_MD,
    _RADIUS_SM,
    _TEXT_PRIMARY,
    _TEXT_SECONDARY,
)

# ── Override logo for portal: use normal-color version (inverted is unreadable
#    on the brown header background) ───────────────────────────────────────────
import base64
_PORTAL_LOGO_PATH = os.path.join(_PROJECT_ROOT, "assets", "branding", "safari_logo_horizontal.png")

def _load_logo_b64():
    """Load the normal-color SAFARI logo (override for portal header)."""
    if not os.path.exists(_PORTAL_LOGO_PATH):
        return ""
    with open(_PORTAL_LOGO_PATH, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ─────────────────────────────────────────────────────────────────────────────
# Portal-specific CSS (extends md_to_pdf tokens)
# ─────────────────────────────────────────────────────────────────────────────

PORTAL_CSS = f"""
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
    --sidebar-width: 260px;
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
    font-family: 'Poppins', system-ui, -apple-system, sans-serif;
    font-size: 14px;
    color: var(--text-primary);
    line-height: 1.7;
    background: var(--bg-primary);
    display: flex;
    flex-direction: column;
    min-height: 100vh;
}}

/* ═══════════════════════════════════════════
   Header
   ═══════════════════════════════════════════ */

.portal-header {{
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 100;
    height: 56px;
    background: var(--header-bg);
    display: flex;
    align-items: center;
    padding: 0 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}}

.portal-header .logo {{
    height: 36px;
    margin-right: 16px;
}}

.portal-header .header-title {{
    color: var(--header-text);
    font-size: 15px;
    font-weight: 500;
    letter-spacing: 0.03em;
    opacity: 0.9;
}}

.portal-header .header-sep {{
    color: var(--earth-taupe);
    margin: 0 12px;
    font-size: 18px;
    font-weight: 300;
    opacity: 0.5;
}}

.portal-header .header-brand {{
    margin-left: auto;
    color: var(--earth-taupe);
    font-size: 12px;
    font-weight: 400;
    letter-spacing: 0.05em;
    opacity: 0.7;
}}

.hamburger {{
    display: none;
    background: none;
    border: none;
    color: var(--header-text);
    font-size: 22px;
    cursor: pointer;
    margin-right: 12px;
    padding: 4px 8px;
    border-radius: {_RADIUS_SM};
}}
.hamburger:hover {{ background: rgba(255,255,255,0.1); }}

/* ═══════════════════════════════════════════
   Layout: Sidebar + Main
   ═══════════════════════════════════════════ */

.portal-layout {{
    display: flex;
    margin-top: 56px;
    flex: 1;
}}

/* ── Sidebar ── */
.portal-sidebar {{
    position: fixed;
    top: 56px;
    left: 0;
    bottom: 0;
    width: var(--sidebar-width);
    background: var(--header-bg);
    overflow-y: auto;
    padding: 20px 0;
    z-index: 50;
}}

.sidebar-section {{
    padding: 0 16px;
    margin-bottom: 8px;
}}

.sidebar-section-label {{
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--earth-taupe);
    padding: 12px 12px 6px;
}}

.sidebar-link {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    color: rgba(255,255,255,0.7);
    text-decoration: none;
    font-size: 13px;
    font-weight: 400;
    border-radius: {_RADIUS_MD};
    transition: all 0.15s ease;
    margin-bottom: 2px;
}}

.sidebar-link svg {{
    flex-shrink: 0;
    width: 16px;
    height: 16px;
    stroke-width: 1.5;
}}

.sidebar-link:hover {{
    color: #fff;
    background: rgba(255,255,255,0.08);
}}

.sidebar-link.active {{
    color: #fff;
    background: var(--accent);
    font-weight: 500;
}}

.sidebar-sub {{
    display: none;
    padding-left: 12px;
    margin-bottom: 6px;
}}

.sidebar-link.active + .sidebar-sub {{
    display: block;
}}

.sidebar-sub a {{
    display: block;
    padding: 4px 12px;
    color: rgba(255,255,255,0.5);
    text-decoration: none;
    font-size: 12px;
    border-left: 2px solid rgba(255,255,255,0.1);
    transition: all 0.15s ease;
}}

.sidebar-sub a:hover {{
    color: rgba(255,255,255,0.85);
    border-left-color: var(--accent);
}}

/* ── Main Content ── */
.portal-main {{
    margin-left: var(--sidebar-width);
    flex: 1;
    padding: 40px 48px 60px;
    max-width: calc(800px + var(--sidebar-width) + 96px);
    min-height: calc(100vh - 56px);
}}

.content-wrap {{
    max-width: 800px;
}}

/* ═══════════════════════════════════════════
   Content Typography
   ═══════════════════════════════════════════ */

.content-wrap h1 {{
    font-size: 28px;
    font-weight: 600;
    border-bottom: 2px solid var(--accent);
    padding-bottom: 10px;
    margin: 0 0 8px;
    color: var(--header-bg);
}}

.content-wrap h2 {{
    font-size: 20px;
    font-weight: 500;
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
    margin-top: 32px;
    color: var(--header-bg);
}}

.content-wrap h3 {{
    font-size: 16px;
    font-weight: 600;
    margin-top: 24px;
    color: var(--text-primary);
}}

.content-wrap h4 {{ font-size: 14px; font-weight: 600; margin-top: 20px; }}

.content-wrap p {{ margin: 12px 0; }}

.content-wrap a {{ color: var(--accent); text-decoration: none; }}
.content-wrap a:hover {{ text-decoration: underline; color: var(--accent-hover); }}

/* ── Code ── */
.content-wrap code {{
    font-family: 'JetBrains Mono', 'SF Mono', 'Menlo', monospace;
    background: var(--bg-tertiary);
    padding: 2px 6px;
    border-radius: {_RADIUS_SM};
    font-size: 12.5px;
    color: var(--header-bg);
}}

.content-wrap pre {{
    background: var(--code-bg);
    color: var(--code-text);
    padding: 16px 20px;
    border-radius: {_RADIUS_LG};
    overflow-x: auto;
    font-size: 12px;
    line-height: 1.5;
    margin: 16px 0;
}}

.content-wrap pre code {{
    background: none;
    padding: 0;
    border-radius: 0;
    color: inherit;
}}

/* ── Tables ── */
.content-wrap table {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 13px;
}}

.content-wrap th, .content-wrap td {{
    border: 1px solid var(--border);
    padding: 8px 12px;
    text-align: left;
}}

.content-wrap th {{
    background: var(--bg-tertiary);
    font-weight: 600;
    color: var(--header-bg);
}}

.content-wrap tr:nth-child(even) {{ background: #fff; }}

/* ── Blockquotes / alerts ── */
.content-wrap blockquote {{
    border-left: 4px solid var(--accent);
    margin: 16px 0;
    padding: 10px 16px;
    background: var(--accent-mute);
    border-radius: 0 {_RADIUS_MD} {_RADIUS_MD} 0;
    color: var(--text-secondary);
}}

/* ── Horizontal rules ── */
.content-wrap hr {{
    border: none;
    border-top: 1px solid var(--border);
    margin: 28px 0;
}}

/* ── Lists ── */
.content-wrap ul, .content-wrap ol {{ padding-left: 24px; margin: 12px 0; }}
.content-wrap li {{ margin: 4px 0; }}

/* ── Screenshots ── */
.content-wrap img {{
    max-width: 100%;
    border: 1px solid var(--border);
    border-radius: {_RADIUS_LG};
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    margin: 16px auto;
    display: block;
}}

/* Compact screenshots — modals, cards, dropdowns */
.content-wrap img.img-compact {{
    max-width: 420px;
}}

/* Image captions (figcaption from Pandoc) */
.content-wrap figure {{
    margin: 16px 0 24px 0;
    text-align: center;
}}
.content-wrap figure img {{
    margin-bottom: 6px;
}}
.content-wrap figcaption {{
    font-style: italic;
    font-size: 0.9em;
    color: var(--text-secondary);
    text-align: center;
    margin-top: 4px;
}}

/* Inline icon buttons — mimic SAFARI toolbar buttons in docs text */
.icon-btn {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: {_RADIUS_SM};
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
    vertical-align: middle;
    line-height: 1.4;
    white-space: nowrap;
}}
.icon-btn svg {{
    width: 14px;
    height: 14px;
    stroke-width: 1.5;
}}
/* Icon-only: square button, no text label */
.icon-btn.icon-only {{
    padding: 4px;
    gap: 0;
}}
/* Outline green — matches Auto-Label sparkles button (variant=outline, color_scheme=green) */
.icon-btn.outline-green {{
    background: transparent;
    border-color: {_ACCENT};
    color: {_ACCENT};
}}
/* Solid green — matches confirm/start buttons (variant=solid, color_scheme=green) */
.icon-btn.solid-green {{
    background: {_ACCENT};
    border-color: {_ACCENT};
    color: #fff;
}}
.icon-btn.solid-green svg {{ stroke: #fff; }}
/* Solid blue — matches active tool buttons (variant=solid, color_scheme=blue) */
.icon-btn.solid-blue {{
    background: #3e63dd;
    border-color: #3e63dd;
    color: #fff;
}}
.icon-btn.solid-blue svg {{ stroke: #fff; }}
/* Solid gray — matches inactive tool buttons (variant=solid, color_scheme=gray) */
.icon-btn.solid-gray {{
    background: #696e77;
    border-color: #696e77;
    color: #fff;
}}
.icon-btn.solid-gray svg {{ stroke: #fff; }}
/* Outline purple — matches Autolabel button (variant=outline, color_scheme=purple) */
.icon-btn.outline-purple {{
    background: transparent;
    border-color: #8e4ec6;
    color: #8e4ec6;
}}
.icon-btn.outline-purple svg {{ stroke: #8e4ec6; }}

/* ═══════════════════════════════════════════
   Index Page — Card Grid
   ═══════════════════════════════════════════ */

.card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
    margin: 20px 0;
}}

.card {{
    background: #fff;
    border: 1px solid var(--border);
    border-radius: {_RADIUS_LG};
    padding: 20px;
    text-decoration: none;
    color: var(--text-primary);
    transition: all 0.2s ease;
    display: block;
}}

.card:hover {{
    border-color: var(--accent);
    box-shadow: 0 4px 16px rgba(95, 173, 86, 0.12);
    transform: translateY(-2px);
    text-decoration: none;
}}

.card .card-icon {{
    margin-bottom: 10px;
    color: var(--accent);
}}

.card .card-icon svg {{
    width: 22px;
    height: 22px;
    stroke-width: 1.5;
}}

.card .card-title {{
    font-size: 14px;
    font-weight: 600;
    color: var(--header-bg);
    margin-bottom: 4px;
}}

.card .card-desc {{
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.5;
}}

/* ═══════════════════════════════════════════
   Page Navigation (Prev / Next)
   ═══════════════════════════════════════════ */

.page-nav {{
    display: flex;
    justify-content: space-between;
    margin-top: 48px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    gap: 16px;
}}

.page-nav a {{
    display: flex;
    flex-direction: column;
    padding: 12px 16px;
    border: 1px solid var(--border);
    border-radius: {_RADIUS_MD};
    text-decoration: none;
    color: var(--text-primary);
    transition: all 0.15s ease;
    min-width: 0;
    max-width: 48%;
}}

.page-nav a:hover {{
    border-color: var(--accent);
    background: var(--accent-mute);
    text-decoration: none;
}}

.page-nav .nav-label {{
    font-size: 11px;
    color: var(--text-secondary);
    margin-bottom: 2px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}

.page-nav .nav-title {{
    font-size: 14px;
    font-weight: 500;
    color: var(--header-bg);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.page-nav .next {{ margin-left: auto; text-align: right; }}

/* ═══════════════════════════════════════════
   Footer
   ═══════════════════════════════════════════ */

.portal-footer {{
    margin-left: var(--sidebar-width);
    padding: 16px 48px;
    border-top: 1px solid var(--border);
    text-align: center;
    font-size: 11px;
    color: var(--earth-taupe);
}}

/* ═══════════════════════════════════════════
   Responsive — collapse sidebar < 768px
   ═══════════════════════════════════════════ */

@media (max-width: 768px) {{
    .hamburger {{ display: block; }}

    .portal-sidebar {{
        transform: translateX(-100%);
        transition: transform 0.25s ease;
    }}
    .portal-sidebar.open {{
        transform: translateX(0);
        box-shadow: 4px 0 20px rgba(0,0,0,0.3);
    }}

    .portal-main, .portal-footer {{
        margin-left: 0;
        padding: 24px 20px 40px;
    }}

    .portal-footer {{ padding: 16px 20px; }}
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Page metadata
# ─────────────────────────────────────────────────────────────────────────────

# Lucide icon names per page (matching SAFARI app icon vocabulary)
PAGE_ICONS = {
    "00_index": "home",
    "01_getting-started": "rocket",
    "02_image-labeling": "image",
    "03_video-labeling": "video",
    "04_autolabeling": "sparkles",
    "05_training": "brain",
    "06_playground": "zap",
    "07_api": "plug",
    "08_architecture": "blocks",
    "09_deployment": "cloud",
    "10_development": "code",
}


def _lucide(name: str) -> str:
    """Return an HTML element that Lucide CDN will replace with an SVG icon."""
    return f'<i data-lucide="{name}"></i>'

# Sidebar section grouping
USER_GUIDE_PAGES = [
    "01_getting-started",
    "02_image-labeling",
    "03_video-labeling",
    "04_autolabeling",
    "05_training",
    "06_playground",
    "07_api",
]

TECHNICAL_PAGES = [
    "08_architecture",
    "09_deployment",
    "10_development",
]


def _extract_h2s(md_path: str) -> list[str]:
    """Extract all H2 headings from a markdown file for sub-navigation."""
    h2s = []
    with open(md_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                h2s.append(line[3:].strip())
    return h2s


def _slug(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _discover_pages() -> list[dict]:
    """Discover and parse all content markdown files."""
    md_files = sorted(
        f for f in os.listdir(_CONTENT_DIR)
        if f.endswith(".md") and f.lower() != "readme.md"
    )

    pages = []
    for filename in md_files:
        md_path = os.path.join(_CONTENT_DIR, filename)
        stem = os.path.splitext(filename)[0]
        title = extract_title(md_path)
        h2s = _extract_h2s(md_path)

        # HTML filename: 00_index -> index, others keep stem
        if stem == "00_index":
            html_name = "index.html"
        else:
            html_name = f"{stem}.html"

        pages.append({
            "stem": stem,
            "filename": filename,
            "md_path": md_path,
            "html_name": html_name,
            "title": title,
            "h2s": h2s,
            "icon": PAGE_ICONS.get(stem, "file-text"),
        })

    return pages


def _build_sidebar_html(pages: list[dict], active_stem: str) -> str:
    """Build the sidebar navigation HTML."""
    lines = []

    # Home link
    home = next((p for p in pages if p["stem"] == "00_index"), None)
    if home:
        active = "active" if active_stem == "00_index" else ""
        lines.append(
            f'<a href="{home["html_name"]}" class="sidebar-link {active}">'
            f'{_lucide("home")} Home</a>'
        )

    # User Guide section
    lines.append('<div class="sidebar-section-label">User Guide</div>')
    for p in pages:
        if p["stem"] not in USER_GUIDE_PAGES:
            continue
        active = "active" if p["stem"] == active_stem else ""
        lines.append(
            f'<a href="{p["html_name"]}" class="sidebar-link {active}">'
            f'{_lucide(p["icon"])} {p["title"]}</a>'
        )
        # Sub-navigation (H2 anchors) for active page
        if active and p["h2s"]:
            lines.append('<div class="sidebar-sub">')
            for h2 in p["h2s"]:
                slug = _slug(h2)
                lines.append(f'<a href="#{slug}">{h2}</a>')
            lines.append("</div>")

    # Technical section
    lines.append('<div class="sidebar-section-label">Technical</div>')
    for p in pages:
        if p["stem"] not in TECHNICAL_PAGES:
            continue
        active = "active" if p["stem"] == active_stem else ""
        lines.append(
            f'<a href="{p["html_name"]}" class="sidebar-link {active}">'
            f'{p["icon"]} {p["title"]}</a>'
        )
        if active and p["h2s"]:
            lines.append('<div class="sidebar-sub">')
            for h2 in p["h2s"]:
                slug = _slug(h2)
                lines.append(f'<a href="#{slug}">{h2}</a>')
            lines.append("</div>")

    return "\n    ".join(lines)


def _build_page_nav(pages: list[dict], current_idx: int) -> str:
    """Build previous/next navigation links."""
    parts = []
    parts.append('<div class="page-nav">')

    if current_idx > 0:
        prev_p = pages[current_idx - 1]
        parts.append(
            f'<a href="{prev_p["html_name"]}" class="prev">'
            f'<span class="nav-label">← Previous</span>'
            f'<span class="nav-title">{prev_p["title"]}</span></a>'
        )
    else:
        parts.append("<span></span>")

    if current_idx < len(pages) - 1:
        next_p = pages[current_idx + 1]
        parts.append(
            f'<a href="{next_p["html_name"]}" class="next">'
            f'<span class="nav-label">Next →</span>'
            f'<span class="nav-title">{next_p["title"]}</span></a>'
        )

    parts.append("</div>")
    return "\n".join(parts)


def _build_index_cards(pages: list[dict]) -> str:
    """Build the card grid HTML for the index/welcome page."""
    # Short descriptions from page subtitles (first blockquote line)
    descriptions = {}
    for p in pages:
        if p["stem"] == "00_index":
            continue
        with open(p["md_path"], "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("> ") and not line.startswith("> [!"):
                    descriptions[p["stem"]] = line[2:].strip()
                    break

    user_cards = []
    tech_cards = []

    for p in pages:
        if p["stem"] == "00_index":
            continue
        desc = descriptions.get(p["stem"], "")
        card = (
            f'<a href="{p["html_name"]}" class="card">'
            f'<div class="card-icon">{_lucide(p["icon"])}</div>'
            f'<div class="card-title">{p["title"]}</div>'
            f'<div class="card-desc">{desc}</div>'
            f"</a>"
        )
        if p["stem"] in USER_GUIDE_PAGES:
            user_cards.append(card)
        elif p["stem"] in TECHNICAL_PAGES:
            tech_cards.append(card)

    html = '<div class="card-grid">\n' + "\n".join(user_cards) + "\n</div>"
    html += '\n<h2>Technical Reference</h2>\n'
    html += '<div class="card-grid">\n' + "\n".join(tech_cards) + "\n</div>"
    return html


def _wrap_page(body_html: str, page: dict, pages: list[dict], idx: int) -> str:
    """Wrap a pandoc HTML fragment in the full portal template."""
    sidebar = _build_sidebar_html(pages, page["stem"])
    page_nav = _build_page_nav(pages, idx)
    logo_b64 = _load_logo_b64()

    # For index page, replace the content lists with card grid
    if page["stem"] == "00_index":
        # Insert the card grid after the first <hr> in the body
        card_html = _build_index_cards(pages)
        # Replace everything after the blockquote with cards
        # The markdown will produce: <h1>, <blockquote>, <hr>, then content
        # We replace the list sections with cards
        parts = body_html.split("<hr />", 1)
        if len(parts) == 2:
            body_html = parts[0] + "<hr />\n" + card_html
        else:
            body_html += "\n" + card_html

    icon_small = ICON_MARK_SVG.replace('width="40" height="40"', 'width="20" height="20"')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page["title"]} — SAFARI Documentation</title>
<style>{PORTAL_CSS}</style>
</head>
<body>

<!-- Header -->
<header class="portal-header">
    <button class="hamburger" onclick="document.querySelector('.portal-sidebar').classList.toggle('open')" aria-label="Menu">☰</button>
    <img src="{logo_b64}" alt="SAFARI" class="logo">
    <span class="header-sep">|</span>
    <span class="header-title">Documentation</span>
    <span class="header-brand">Biota Cloud</span>
</header>

<!-- Layout -->
<div class="portal-layout">

    <!-- Sidebar -->
    <nav class="portal-sidebar">
        <div class="sidebar-section">
            {sidebar}
        </div>
    </nav>

    <!-- Main Content -->
    <main class="portal-main">
        <div class="content-wrap">
            {body_html}
            {page_nav}
        </div>
    </main>

</div>

<!-- Footer -->
<footer class="portal-footer">
    {icon_small}
    <span style="margin-left: 6px;">SAFARI — Biota Cloud</span>
</footer>

<script src="https://unpkg.com/lucide@latest"></script>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({{ startOnLoad: false, theme: 'neutral', themeVariables: {{ primaryColor: '#ddd4c8', primaryBorderColor: '#8B7355', primaryTextColor: '#2d2a26', lineColor: '#8B7355', secondaryColor: '#f5f0eb', tertiaryColor: '#ede8e1' }} }});
// Convert Pandoc code blocks to mermaid divs.
// Pandoc may output: <pre class="mermaid"><code>...</code></pre>
// or: <pre><code class="language-mermaid">...</code></pre>
// Either way, we need a clean <div class="mermaid">text</div>
document.querySelectorAll('pre.mermaid, pre:has(> code.language-mermaid)').forEach(function(pre) {{
    var code = pre.querySelector('code');
    var text = code ? code.textContent : pre.textContent;
    var div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = text;
    pre.parentNode.replaceChild(div, pre);
}});
await mermaid.run();
</script>
<script>
// Initialize Lucide icons
lucide.createIcons();

// Restore images from Reflex placeholder spans.
// Reflex's build pipeline replaces <img> tags with <span class="image placeholder"
// data-original-image-src="..."> in static HTML files it serves from assets/.
// This converts them back to proper <img> tags at runtime.
document.querySelectorAll('span.image.placeholder[data-original-image-src]').forEach(function(span) {{
    var img = document.createElement('img');
    var src = span.getAttribute('data-original-image-src');
    img.src = src;
    img.alt = span.textContent || '';
    if (span.getAttribute('data-original-image-title')) {{
        img.title = span.getAttribute('data-original-image-title');
    }}
    // Auto-detect compact screenshots (modals, cards, dropdowns, popovers)
    var lowerSrc = src.toLowerCase();
    if (/modal|card|dropdown|popover|menu|results|compact|key_|confirmation/.test(lowerSrc) || img.classList.contains('compact')) {{
        img.classList.add('img-compact');
    }}
    span.parentNode.replaceChild(img, span);
}});

// Close sidebar on mobile when a link is clicked
document.querySelectorAll('.sidebar-link').forEach(function(link) {{
    link.addEventListener('click', function() {{
        if (window.innerWidth <= 768) {{
            document.querySelector('.portal-sidebar').classList.remove('open');
        }}
    }});
}});
</script>

</body>
</html>"""
    return html


def build_portal(no_open: bool = False) -> str:
    """Build the entire documentation portal."""
    # 1. Discover pages
    pages = _discover_pages()
    if not pages:
        print(f"❌ No .md files found in {_CONTENT_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"📄 Found {len(pages)} pages:")
    for p in pages:
        print(f"   {p['stem']} → {p['title']}")

    # 2. Ensure output directory exists
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    # 3. Copy screenshots to output
    screenshots_dst = os.path.join(_OUTPUT_DIR, "screenshots")
    if os.path.exists(_SCREENSHOTS_SRC):
        if os.path.exists(screenshots_dst):
            shutil.rmtree(screenshots_dst)
        shutil.copytree(_SCREENSHOTS_SRC, screenshots_dst)
        print(f"📷 Copied {len(os.listdir(screenshots_dst))} screenshots")

    # 4. Copy branding
    branding_dst = os.path.join(_OUTPUT_DIR, "branding")
    if os.path.exists(_BRANDING_SRC):
        if os.path.exists(branding_dst):
            shutil.rmtree(branding_dst)
        shutil.copytree(_BRANDING_SRC, branding_dst)
        print("🎨 Copied branding assets")

    # 5. Build each page
    for i, page in enumerate(pages):
        body_html = run_pandoc(page["md_path"])

        # Fix image paths: ../assets/screenshots/X.png → screenshots/X.png
        body_html = re.sub(
            r'src="\.\.\/assets\/screenshots\/',
            'src="screenshots/',
            body_html,
        )
        # Also handle relative paths from content dir
        body_html = re.sub(
            r'src="assets/screenshots/',
            'src="screenshots/',
            body_html,
        )

        full_html = _wrap_page(body_html, page, pages, i)
        output_path = os.path.join(_OUTPUT_DIR, page["html_name"])

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        print(f"   ✅ {page['html_name']}")

    index_path = os.path.join(_OUTPUT_DIR, "index.html")
    print(f"\n🎉 Portal built → {_OUTPUT_DIR}/")
    print(f"   {len(pages)} pages generated")

    if not no_open:
        abs_path = os.path.abspath(index_path)
        webbrowser.open(f"file://{abs_path}")
        print("🌐 Opened in browser")

    return index_path


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build the SAFARI Onboarding Documentation Portal.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open the result in the browser",
    )
    args = parser.parse_args()

    build_portal(no_open=args.no_open)


if __name__ == "__main__":
    main()
