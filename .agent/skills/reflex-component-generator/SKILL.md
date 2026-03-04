---
name: reflex-component-generator
description: Use this skill when creating Reflex UI components, building modals, implementing state handlers, adding foreach loops, creating tooltips, building scrollable lists, or working with Reflex reactive variables. Activates for new UI components, state management, or Reflex-specific patterns.
---

# Reflex Component Generator

## Goal
Generate Reflex UI components that follow Tyto Design System patterns and avoid common Reflex pitfalls.

## Instructions

### Step 1: Define State Variables with Explicit Types
Reflex requires explicit type hints for `rx.foreach`:

```python
# WRONG - will cause UntypedVarError
items: list = []

# CORRECT - explicit inner type
items: list[dict] = []

# BEST - TypedDict or Pydantic for nested access
from typing import TypedDict

class ProjectItem(TypedDict):
    id: str
    name: str
    count: int

items: list[ProjectItem] = []
```

### Step 2: Use rx.foreach Correctly
```python
# In component
rx.foreach(
    MyState.items,
    lambda item: rx.hstack(
        rx.text(item["name"]),  # Works because ProjectItem is typed
        rx.badge(item["count"]),
    )
)
```

### Step 3: Handle Nested Clickables
Use `rx.stop_propagation` to prevent event bubbling:

```python
rx.box(
    rx.icon_button(
        rx.icon("trash"),
        on_click=[rx.stop_propagation, State.delete_item(item["id"])]
    ),
    on_click=rx.redirect(f"/items/{item['id']}"),
)
```

### Step 4: Tooltips Must Be Strings
```python
# WRONG - TypeError
rx.tooltip(rx.badge("Info"), content=rx.vstack(...))

# CORRECT - string only
rx.tooltip(rx.badge("Info"), content="Additional information here")
```

### Step 5: Pre-compute Complex Data
Use `@rx.var` for derived/sorted data:

```python
@rx.var
def sorted_items(self) -> list[list]:
    """Sort items by count descending."""
    return sorted(self.data.items(), key=lambda x: x[1], reverse=True)
```

### Step 6: CSS Hover Effects for Lists
Avoid per-item state variables—use CSS descendant selectors:

```python
rx.hstack(
    rx.text("Item Name"),
    rx.icon_button(
        rx.icon("pencil"),
        style={"opacity": "0", "transition": "opacity 0.2s"},
        class_name="edit-pencil",
    ),
    style={
        "&:hover .edit-pencil": {"opacity": "1"},
    },
)
```

### Step 7: Scrollable Containers
For dashboard widgets with growing content:

```python
rx.scroll_area(
    rx.vstack(
        rx.foreach(State.items, item_row),
        width="100%",
        spacing="1",
    ),
    style={"max_height": "200px"},
    scrollbars="vertical",
)
```

### Step 8: Dynamic Labels with rx.cond
```python
rx.button(
    rx.cond(
        State.is_editing,
        rx.text("Save"),
        rx.text("Edit"),
    ),
    on_click=State.toggle_edit,
)
```

## Constraints
- Never use `len()` or Python slice `[:]` on `rx.Var` in templates—use CSS or backend formatting
- Never nest `<div>` inside `rx.alert_dialog.description` (it renders as `<p>`)
- Always convert RGBA images to RGB before saving as JPEG
- Use `rows="3"` (string) not `rows=3` (int) for `rx.text_area`

## Design Tokens (Tyto Design System)
```python
# Colors
"--accent": "#3B82F6"      # Primary blue
"--success": "#22C55E"     # Green
"--error": "#EF4444"       # Red
"--bg-secondary": "#141415"
"--border": "#27272A"

# Radius
"--radius-sm": "4px"
"--radius-md": "6px"
"--radius-lg": "8px"
```

## Resources
- See `examples/modal_pattern.py` for complete modal dialog pattern
