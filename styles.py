# styles.py — SAFARI NATURALIST DESIGN SYSTEM — THEME SOURCE OF TRUTH
# Import from here only — never hardcode hex values in components.
#
# Migrated from Tyto dark mode to SAFARI warm light-mode palette.
# Reference: docs/design/safari_design_reference.md

# =============================================================================
# COLOR PALETTE (SAFARI Naturalist — Warm Light Mode)
# =============================================================================

# Backgrounds
BG_PRIMARY = "#F5F0EB"       # Warm cream — main page background
BG_SECONDARY = "#FFFFFF"     # White — cards, modals, sidebars
BG_TERTIARY = "#F0EBE5"      # Warm hover — subtle elevation

# Accent Colors
ACCENT = "#5FAD56"           # Leaf green — primary actions
ACCENT_HOVER = "#4E9A47"     # Darker green — button hover
ACCENT_MUTE = "rgba(95, 173, 86, 0.1)"  # Muted green background
ACCENT_MUTE_GREEN = "rgba(95, 173, 86, 0.15)"  # Active nav item wash

# Header Bar
HEADER_BG = "#4A3728"        # Chocolate brown — nav header background
HEADER_TEXT = "#FFFFFF"       # White — header text
HEADER_TEXT_DIM = "rgba(255, 255, 255, 0.7)"  # Dimmed header text

# Secondary Palette — Earth Tones (only 2 needed)
EARTH_TAUPE = "#8B7355"      # Warm taupe — secondary icons, muted info
EARTH_SIENNA = "#A0785A"     # Sienna — data categories (video type), tertiary

# Backwards-compatible aliases (consolidated — will be removed after sweep)
EARTH_SAGE = ACCENT          # Was #7BA896 — merged into green accent
EARTH_CLAY = EARTH_SIENNA    # Was #C4956A — merged into sienna
EARTH_OLIVE = EARTH_TAUPE    # Was #6B7F5E — merged into taupe

# Status Colors
SUCCESS = "#22C55E"          # Completed states, positive feedback
WARNING = "#F59E0B"          # Alerts, training in progress (NOT for data categories)
ERROR = "#EF4444"            # Destructive actions, errors
PURPLE = "#A855F7"           # ONLY for ML concept: Hybrid/Classification badges

# Text Colors
TEXT_PRIMARY = "#333333"     # Near-black — headings, important text
TEXT_SECONDARY = "#888888"   # Warm grey — body text, descriptions

# Code / Terminal — keep dark for readability
CODE_BG = "#1E1E1E"          # Dark terminal background
CODE_TEXT = "#D4D4D4"        # Light terminal text

# Borders
BORDER = "#D5D0CB"           # Warm grey — borders, dividers


# =============================================================================
# CARD STYLES (Single Source of Truth)
# =============================================================================
# Use these semantic constants instead of BG_* directly for cards/items

# Standard card on page background
CARD_BG = BG_SECONDARY          # White — main content cards

# Interactive items inside cards (list items, dropdown entries)
CARD_ITEM_BG = BG_TERTIARY      # Warm hover — clickable items within cards

# Popover/Modal backgrounds (same as cards)
POPOVER_BG = BG_SECONDARY       # White — dropdowns, dialogs, tooltips

# Items inside popovers
POPOVER_ITEM_BG = BG_TERTIARY   # Warm hover — clickable items within popovers


# =============================================================================
# TYPOGRAPHY
# =============================================================================

FONT_FAMILY = "'Poppins', system-ui, -apple-system, sans-serif"
FONT_FAMILY_HEADING = FONT_FAMILY  # Same family, heavier weights
FONT_FAMILY_MONO = "JetBrains Mono, monospace"

# Font Weights
FONT_WEIGHT_REGULAR = "400"
FONT_WEIGHT_MEDIUM = "500"
FONT_WEIGHT_SEMIBOLD = "600"

# Font Sizes
FONT_SIZE_XS = "12px"
FONT_SIZE_SM = "13px"
FONT_SIZE_BASE = "14px"
FONT_SIZE_LG = "16px"
FONT_SIZE_XL = "24px"
FONT_SIZE_2XL = "32px"

# Button Typography (SAFARI ALL-CAPS style)
BUTTON_TEXT_TRANSFORM = "uppercase"
BUTTON_LETTER_SPACING = "0.08em"


# =============================================================================
# SPACING (4px Grid)
# =============================================================================

SPACING_1 = "4px"
SPACING_2 = "8px"
SPACING_3 = "12px"
SPACING_4 = "16px"
SPACING_6 = "24px"
SPACING_8 = "32px"
SPACING_12 = "48px"


# =============================================================================
# LAYOUT
# =============================================================================

SIDEBAR_WIDTH = "240px"
MAX_CONTENT_WIDTH = "1280px"


# =============================================================================
# BORDER RADIUS
# =============================================================================

RADIUS_SM = "4px"   # Inputs
RADIUS_MD = "6px"   # Buttons
RADIUS_LG = "8px"   # Cards


# =============================================================================
# ANIMATION
# =============================================================================

TRANSITION_FAST = "150ms cubic-bezier(0.4, 0, 0.2, 1)"
TRANSITION_DEFAULT = "300ms cubic-bezier(0.4, 0, 0.2, 1)"


# =============================================================================
# INTERACTIVE STATES (Common Style Dicts)
# =============================================================================

# Focus ring style
FOCUS_RING = {
    "outline": f"2px solid {ACCENT}",
    "outline_offset": "2px",
}

# Disabled state
DISABLED_STYLE = {
    "opacity": "0.5",
    "cursor": "not-allowed",
}

# Mini badge style (for inline class counts, etc.)
BADGE_MINI = {
    "font_size": "10px",
    "padding": "1px 5px",
    "border_radius": RADIUS_SM,
    "line_height": "1.2",
}

# Material-outlined input style (reusable across all forms)
INPUT_OUTLINED = {
    "width": "100%",
    "padding": "12px 16px",
    "background": "transparent",
    "border": f"1px solid {BORDER}",
    "border_radius": RADIUS_SM,
    "color": TEXT_PRIMARY,
    "font_size": FONT_SIZE_BASE,
    "outline": "none",
    "box_sizing": "border-box",
    "transition": "border-color 0.2s",
    "&:focus": {
        "border_color": ACCENT,
        "border_width": "2px",
        "padding": "11px 15px",
    },
    "&::placeholder": {
        "color": TEXT_SECONDARY,
    },
}


# =============================================================================
# SHADOWS (tuned for light backgrounds)
# =============================================================================

SHADOW_SM = "0 1px 3px 0 rgba(0, 0, 0, 0.06), 0 1px 2px 0 rgba(0, 0, 0, 0.04)"
SHADOW_MD = "0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -1px rgba(0, 0, 0, 0.04)"
SHADOW_LG = "0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.03)"


# =============================================================================
# BUTTON STYLES (use instead of relying on Radix color_scheme)
# =============================================================================

BUTTON_PRIMARY = {
    "background": ACCENT,
    "color": "#FFFFFF",
    "&:hover": {"background": ACCENT_HOVER},
}

BUTTON_SECONDARY = {
    "background": "transparent",
    "color": TEXT_PRIMARY,
    "border": f"1px solid {BORDER}",
    "&:hover": {"background": BG_TERTIARY},
}

BUTTON_DANGER = {
    "background": "transparent",
    "color": ERROR,
    "border": f"1px solid {ERROR}",
    "&:hover": {"background": f"{ERROR}10"},
}
