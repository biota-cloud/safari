# SAFARI Demo Design Analysis

## The Demo at a Glance

````carousel
![Login — Split-panel with hero wildlife photo](/Users/jorge/.gemini/antigravity/brain/4e0ba04a-ca5c-4c7d-88a1-f7dab7f5e796/demo_login.png)
<!-- slide -->
![Projects list — Sidebar with company branding](/Users/jorge/.gemini/antigravity/brain/4e0ba04a-ca5c-4c7d-88a1-f7dab7f5e796/demo_projects.png)
<!-- slide -->
![Create Project — Material-outlined form inputs](/Users/jorge/.gemini/antigravity/brain/4e0ba04a-ca5c-4c7d-88a1-f7dab7f5e796/demo_create_project.png)
<!-- slide -->
![Upload wizard — Step indicators with green active state](/Users/jorge/.gemini/antigravity/brain/4e0ba04a-ca5c-4c7d-88a1-f7dab7f5e796/demo_upload.png)
<!-- slide -->
![Image Gallery — Card grid with tags and selection tray](/Users/jorge/.gemini/antigravity/brain/4e0ba04a-ca5c-4c7d-88a1-f7dab7f5e796/demo_gallery.png)
````

---

## Extracted Design Tokens

### Color Palette — "Warm Naturalist"

| Role | Demo Value | Current SAFARI | Delta |
|---|---|---|---|
| **Page BG** | `#F5F0EB` (warm cream) | `#0A0A0B` (near-black) | Full inversion — light mode |
| **Card BG** | `#FFFFFF` or `#F9F5F0` | `#141415` | White/off-white cards on cream |
| **Header bar** | `#4A3728` (dark chocolate) | n/a (borderless) | Solid brown top bar — brand anchor |
| **Primary accent** | `#5FAD56` (leaf green) | `#3B82F6` (blue) | Green replaces blue |
| **Accent hover / CTA** | `#4E9A47` (darker green) | `#2563EB` | — |
| **Active text on green BG** | `#5FAD56` on sidebar highlight | — | Green text on subtle green wash |
| **Text primary** | `#333333` (near-black) | `#FAFAFA` (white) | Dark text on light BG |
| **Text secondary** | `#888888` (grey) | `#A1A1AA` | Similar weight, warmer grey |
| **Border** | `#CCCCCC` / `#D5D0CB` | `#27272A` | Light grey, visible outlines |
| **Success** | Same green `#5FAD56` | `#22C55E` | Could unify with accent |
| **Error / destructive** | Red (project color swatch) | `#EF4444` | Similar |

### Typography

| Property | Demo | Current SAFARI |
|---|---|---|
| Headings | Light/Regular weight serif-adjacent (possibly Roboto Slab or custom) | Inter 600 |
| Logo font | **Custom `[ • ] S A F A R I`** — wide letter-spacing, all-caps | "SAFARI" in Inter |
| Body | Clean sans-serif (Roboto/Open Sans family) | Inter 400 |
| Labels | ALL-CAPS for buttons ("SIGN IN", "SEARCH", "UPLOAD") | Sentence case |

### Component Patterns

| Component | Demo Style | Current SAFARI |
|---|---|---|
| **Form inputs** | Material-style **outlined** with floating labels — border turns green on focus | Solid background inputs (#1C1C1E) |
| **Buttons (primary)** | Solid green, pill-ish `border-radius: ~4px`, ALL-CAPS text | Solid blue, 6px radius |
| **Buttons (secondary)** | Ghost/outlined with green or grey border | Ghost with accent text |
| **Cards** | White on cream, thin `1px` grey border, minimal shadow | Dark cards, no visible border |
| **Sidebar** | Fixed left, company logo + categorized nav ("WORK" / "COMPANY"), green highlight bar | Horizontal nav with breadcrumbs |
| **Top navbar** | Solid dark brown bar, logo left, avatar + bell right | Transparent with border-bottom |
| **Modals** | Full-viewport overlay, cream backdrop, centered white card | Dark overlay, dark card |
| **Selection tray** | Bottom bar with thumbnails, count, Edit/Delete/Download | Our dataset has similar pattern |
| **Step wizard** | Numbered circles (brown=pending, green=active/done) with connecting lines | Not currently used |
| **Tags** | Rounded pill chips below images (`#Day`, `#Serra`) | Badges in cards |

---

## What to Adopt vs. Not — My Recommendation

### ✅ Adopt (high-impact, preserves your navigation)

1. **Warm light-mode color scheme** — The cream/beige + green palette is the single biggest visual identity shift. It screams "outdoor / ecological" and differentiates from generic dark-mode SaaS tools
2. **Brown header bar with SAFARI logo** — Instant brand recognition, clean visual anchor
3. **Green accent color** — Replace blue with leaf green. Use for CTAs, active states, focus rings, checkboxes, progress bars. One color change touches everything
4. **Material-outlined inputs** with floating labels — Much more polished than solid-bg inputs. The green-on-focus animation feels premium
5. **ALL-CAPS button labels** — Small change, big identity impact. Pairs well with wider letter-spacing
6. **Warm card borders** instead of borderless dark cards — Defines boundaries without heavy shadows

### ⚠️ Adapt (keep your version, inspired by demo)

7. **Sidebar navigation** — The demo has a fixed left sidebar with company branding. You already have a navigation system that works well. **Don't change navigation structure**, but consider adopting the visual style: the sectioned groups ("WORK" / "COMPANY"), the green highlight for active item, and the organizational logo/avatar
8. **Image gallery selection** — Your grid + selection tray pattern is similar to theirs. Adopt the green checkbox overlays and the thumbnail preview carousel at the bottom
9. **Modal styling** — Yours work fine. Just retheme with cream backdrop + white card + outlined inputs

### ❌ Skip (not relevant or would break your app)

10. Calendar, Inventory, Team pages — Different app structure, not applicable
11. Project color picker — Nice detail but out of scope for core migration
12. LinkedIn sign-in — Auth provider decisions are separate from styling

---

## "SAFARI Naturalist" Style Family — Our Interpretation

The idea: take the demo's **warm organic aesthetic** and apply it as a **re-skin** of your existing layout. Same page structure, same navigation philosophy, same data density — new color scheme, input style, and typography.

### Implementation Approach

```
styles.py changes (Phase 3 scope):
├── Color palette: dark→light inversion + green accent
├── Typography: keep Inter, adopt ALL-CAPS buttons + wider spacing
├── Card system: white cards on cream bg, thin borders
├── Input style: outlined with floating labels (green focus)
└── Header: brown solid bar with SAFARI logo
```

### Phasing

This naturally fits into the existing roadmap:
- **Step 0.2 (UI Branding)**: Can already adopt the logo and green accent for the header
- **Step 3.1–3.3 (Style Migration)**: The full light-mode color swap lives here
- **Step 3.4 (Component Refresh)**: Material-outlined inputs, ALL-CAPS buttons

> [!TIP]
> The biggest bang-for-buck is updating `styles.py` color tokens — since all components already import from there, a single file change propagates everywhere.
