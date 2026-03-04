# Right-Click Context Menu for Editor Labels

## Problem Description

Users need a contextual action menu when right-clicking on active (selected) labels in both the Image and Video editors. This will provide quick access to:
1. **Assign another class** — Change the label's class from a flyout submenu
2. **Use as Project thumbnail** — Generate a stylized thumbnail and set it as the project cover image
3. **Use as Dataset thumbnail** — Generate a stylized thumbnail and set it as the dataset cover image

## Design Analysis

### Existing Patterns

| Pattern | Location | Relevance |
|---------|----------|-----------|
| `selected_annotation_id` | `LabelingState`, `VideoLabelingState` | Tracks currently active label |
| `change_annotation_class()` | [state.py:L1021-1043](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/state.py#L1021-1043) | Existing class change logic to reuse |
| `update_annotation_class()` | [state.py:L1045-1065](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/state.py#L1045-1065) | Popover-style class change (alternative pattern) |
| Thumbnail Generator | [thumbnail_generator.py](file:///Users/jorge/PycharmProjects/Tyto/backend/core/thumbnail_generator.py) | Subject-centric thumbnail styling |
| Context menu prevention | [canvas.js:L124](file:///Users/jorge/PycharmProjects/Tyto/assets/canvas.js#L124) | Currently blocks right-click — needs modification |
| Annotation popover edit | [editor.py:L871-906](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/editor.py#L871-906) | Popover UI pattern for class selection |

### Thumbnail Generator Analysis

The inference playground's [thumbnail_generator.py](file:///Users/jorge/PycharmProjects/Tyto/backend/core/thumbnail_generator.py) provides:
- **Styling constants**: `PURPLE_RGB`, `OVERLAY_OPACITY`, `BORDER_THICKNESS`, `THUMBNAIL_SIZE`
- **Subject selection**: `select_largest_detection()` — finds largest bounding box
- **Cropping**: `_crop_with_padding()` — crops with 20% padding
- **Overlays**: `_apply_mask_overlay()`, `_apply_box_overlay()` — purple-tinted styling
- **Encoding**: `_square_resize()`, `_encode_jpeg()`

> [!IMPORTANT]
> **Unified Pattern Decision**: The existing thumbnail generator is designed for inference results (expects predictions with `box` key). For labeling annotations, we have `x, y, width, height` (normalized). We should:
> 1. Extract the generic styling utilities into a shared helper
> 2. Create a thin wrapper for labeling annotations that converts coordinates to the expected format

---

## Proposed Changes

### Phase 1: Foundation — Context Menu Component & State

#### [NEW] [context_menu.py](file:///Users/jorge/PycharmProjects/Tyto/components/context_menu.py)

Shared Reflex component for the context menu:

```python
def annotation_context_menu(
    is_open: rx.Var[bool],
    position_x: rx.Var[int],
    position_y: rx.Var[int],
    classes: rx.Var[list[str]],
    on_class_change: rx.EventHandler,
    on_project_thumbnail: rx.EventHandler,
    on_dataset_thumbnail: rx.EventHandler,
    on_close: rx.EventHandler,
) -> rx.Component:
    """Right-click context menu for annotations."""
```

Key UI elements:
- Fixed position popup at cursor coordinates
- "Assign Class" with submenu showing all project classes
- "Use as Project Thumbnail" action
- "Use as Dataset Thumbnail" action
- Click-outside to close

---

#### [MODIFY] [state.py](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/state.py)

Add context menu state variables:
```python
# Context menu state
context_menu_open: bool = False
context_menu_x: int = 0
context_menu_y: int = 0
context_menu_annotation_id: str = ""  # Annotation for context actions
```

Add new handlers:
```python
def open_context_menu(self, data_json: str):
    """Open context menu at given position for annotation."""
    
def close_context_menu(self):
    """Close the context menu."""
    
def set_as_project_thumbnail(self):
    """Generate thumbnail from selected annotation and set as project cover."""
    
def set_as_dataset_thumbnail(self):
    """Generate thumbnail from selected annotation and set as dataset cover."""
```

---

#### [MODIFY] [video_state.py](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/video_state.py)

Mirror the same context menu state and handlers.

---

### Phase 2: JavaScript Integration — Right-Click Detection

#### [MODIFY] [canvas.js](file:///Users/jorge/PycharmProjects/Tyto/assets/canvas.js)

Change context menu behavior:
```javascript
// L124: Replace blanket prevention with conditional
canvas.addEventListener('contextmenu', handleContextMenu);

function handleContextMenu(e) {
    e.preventDefault();
    
    // Check if right-click is on the selected annotation
    if (!selectedAnnotationId) return;
    
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    // Hit-test against selected annotation
    const hitId = hitTestAnnotations(mouseX, mouseY);
    if (hitId === selectedAnnotationId) {
        // Send context menu request to Python
        triggerContextMenu(e.clientX, e.clientY, selectedAnnotationId);
    }
}

function triggerContextMenu(x, y, annotationId) {
    const input = document.getElementById('context-menu-trigger');
    if (input) {
        const data = JSON.stringify({ x, y, annotation_id: annotationId });
        // ... dispatch event
    }
}
```

Add hidden input for Python communication:
```javascript
// In editor.py, add:
rx.input(
    id="context-menu-trigger",
    on_change=LabelingState.open_context_menu,
    type="text",
    style=HIDDEN_INPUT_STYLE,
),
```

---

#### [MODIFY] [video_canvas.js](file:///Users/jorge/PycharmProjects/Tyto/assets/video_canvas.js)

Apply same right-click detection pattern for video editor.

---

### Phase 3: Action 1 — Change Class

Wire the context menu "Assign Class" submenu to the existing `change_annotation_class()` logic:

```python
# In context_menu.py
rx.menu.sub(
    rx.menu.sub_trigger("Assign Class"),
    rx.menu.sub_content(
        rx.foreach(
            classes,
            lambda cls, idx: rx.menu.item(
                cls,
                on_click=lambda: on_class_change(cls),
            )
        ),
    ),
),
```

**Checkpoint**: Test class change from context menu in both editors.

---

### Phase 4: Thumbnail Generation

#### [NEW] Database Migration

Add `thumbnail_r2_path` column to `projects` and `datasets` tables:

```sql
-- migrations/add_project_dataset_thumbnails.sql
ALTER TABLE projects ADD COLUMN IF NOT EXISTS thumbnail_r2_path TEXT;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS thumbnail_r2_path TEXT;

COMMENT ON COLUMN projects.thumbnail_r2_path IS 'R2 path to custom project thumbnail image';
COMMENT ON COLUMN datasets.thumbnail_r2_path IS 'R2 path to custom dataset thumbnail image';
```

---

#### [MODIFY] [thumbnail_generator.py](file:///Users/jorge/PycharmProjects/Tyto/backend/core/thumbnail_generator.py)

Extract reusable utilities and add labeling-specific entry point:

```python
def generate_label_thumbnail(
    image_bytes: bytes,
    annotation: dict,  # {x, y, width, height} normalized
    output_size: int = THUMBNAIL_SIZE,
) -> Optional[bytes]:
    """
    Generate a stylized thumbnail from a labeling annotation.
    
    Converts annotation format (x, y, width, height) to box format
    and applies the same purple-tinted styling as inference thumbnails.
    """
    # Convert annotation format to box format
    x, y, w, h = annotation["x"], annotation["y"], annotation["width"], annotation["height"]
    box = [x, y, x + w, y + h]  # Convert to xyxy
    
    prediction = {"box": box}
    return generate_detection_thumbnail(image_bytes, prediction, output_size)
```

---

#### [MODIFY] [state.py](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/state.py)

Implement thumbnail generation handlers:

```python
def set_as_project_thumbnail(self):
    """Generate thumbnail from selected annotation and set as project cover."""
    if not self.context_menu_annotation_id:
        return
    
    # 1. Find annotation
    ann = next((a for a in self.annotations if a["id"] == self.context_menu_annotation_id), None)
    if not ann:
        return
    
    # 2. Download current image
    from backend.r2_storage import R2Client
    r2 = R2Client()
    current_img = next((i for i in self.images if i.id == self.current_image_id), None)
    if not current_img:
        return
    image_bytes = r2.download_file(current_img.r2_path)
    
    # 3. Generate thumbnail
    from backend.core.thumbnail_generator import generate_label_thumbnail
    thumb_bytes = generate_label_thumbnail(image_bytes, ann)
    if not thumb_bytes:
        return
    
    # 4. Upload to R2
    thumb_path = f"projects/{self.current_project_id}/thumbnail.jpg"
    r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
    
    # 5. Update database
    from backend.supabase_client import update_project
    update_project(self.current_project_id, thumbnail_r2_path=thumb_path)
    
    # 6. Close menu & notify
    self.close_context_menu()
    return rx.toast.success("Project thumbnail updated!")
```

Similar implementation for `set_as_dataset_thumbnail()`.

---

#### [MODIFY] [video_state.py](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/video_state.py)

Mirror thumbnail handlers, with additional step to extract current video frame:

```python
def set_as_project_thumbnail(self):
    """Generate thumbnail from current frame's selected annotation."""
    # 1. Extract frame from video at current timestamp
    # 2. Find annotation on current keyframe
    # 3. Generate thumbnail
    # 4. Upload and update database
```

---

### Phase 5: UI Integration

#### [MODIFY] [editor.py](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/editor.py)

Add context menu component and hidden input:

```python
# In canvas_area() function, add:
annotation_context_menu(
    is_open=LabelingState.context_menu_open,
    position_x=LabelingState.context_menu_x,
    position_y=LabelingState.context_menu_y,
    classes=LabelingState.project_classes,
    on_class_change=LabelingState.change_annotation_class,
    on_project_thumbnail=LabelingState.set_as_project_thumbnail,
    on_dataset_thumbnail=LabelingState.set_as_dataset_thumbnail,
    on_close=LabelingState.close_context_menu,
),

# Add hidden input for context menu trigger
rx.input(
    id="context-menu-trigger",
    on_change=LabelingState.open_context_menu,
    ...
),
```

---

#### [MODIFY] [video_editor.py](file:///Users/jorge/PycharmProjects/Tyto/modules/labeling/video_editor.py)

Same integration pattern as image editor.

---

## Verification Plan

### Automated Tests
- N/A (manual verification for UI feature)

### Manual Verification

| Step | Expected Result |
|------|-----------------|
| 1. Open Image Editor, draw an annotation | Annotation appears on canvas |
| 2. Click annotation to select it (orange highlight) | Annotation shows corner handles, orange border |
| 3. Right-click on selected annotation | Context menu appears at cursor |
| 4. Right-click on canvas (not on annotation) | No context menu appears |
| 5. Select "Assign Class > [new class]" | Annotation changes class immediately |
| 6. Right-click → "Use as Project Thumbnail" | Toast shows "Project thumbnail updated!", project card shows new thumbnail |
| 7. Right-click → "Use as Dataset Thumbnail" | Toast shows success, dataset card shows new thumbnail |
| 8. Repeat steps 1-7 in Video Editor | Same behavior on keyframe annotations |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Canvas hit-testing accuracy | Reuse existing `hitTestAnnotations()` — already proven |
| Thumbnail generation performance | Run in background thread, show loading spinner |
| R2 upload failures | Wrap in try/catch, show error toast |
| Database migration | Standard ALTER TABLE with IF NOT EXISTS — safe |

---

## Implementation Order

```
Phase 1 (Foundation)     → Checkpoint: Context menu appears
Phase 2 (JS Integration) → Checkpoint: Menu triggers on right-click
Phase 3 (Class Change)   → Checkpoint: Class reassignment works
Phase 4 (Thumbnails)     → Checkpoint: DB migration applied
Phase 5 (Integration)    → Checkpoint: Full flow works
Phase 6 (Verification)   → Checkpoint: Both editors tested
```

Each phase can be committed and tested independently.
