# Right-Click Context Menu for Active Labels

## Goal
Implement a right-click context menu for the currently active (selected) annotation in both Image and Video editors with three actions:
1. Assign another class
2. Use as Project thumbnail
3. Use as Dataset thumbnail

## Phases

### Phase 1: Foundation ✅
- [x] Created `components/context_menu.py` - fixed-position popup with class submenu
- [x] Added context menu state vars to `LabelingState` and `VideoLabelingState`
- [x] Added `generate_label_thumbnail()` to `thumbnail_generator.py`

### Phase 2: JavaScript Integration ✅
- [x] Added `handleContextMenu` and `triggerContextMenu` to `canvas.js`
- [x] Right-click on selected annotation triggers Python context menu via hidden input

### Phase 3: UI Integration ✅
- [x] Added import for `annotation_context_menu` to both editors
- [x] Added `context-menu-trigger` hidden input to both editors
- [x] Added context menu component to `editor_layout` and video editor page

### Phase 4: Database Migration (for thumbnails)
- [ ] Create migration: add `thumbnail_r2_path` to `projects` and `datasets` tables
- [ ] Run migration in Supabase

### Phase 5: Verification
- [ ] Manual testing: right-click context menu appears correctly
- [ ] Manual testing: change class works
- [ ] Manual testing: project thumbnail updates (requires Phase 4)
- [ ] Manual testing: dataset thumbnail updates (requires Phase 4)

## Ready to Test
The context menu is now wired up. Test by:
1. Open the image labeling editor
2. Draw or select an annotation (orange highlight)
3. Right-click on the highlighted annotation
4. Context menu should appear at cursor

**Note**: Thumbnail actions will fail until the database migration is run.
