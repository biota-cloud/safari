---
description: Add a feature request or idea to the wishlist with expanded details
---

# Add Wishlist Item Workflow

Use this when the user provides a brief feature request or idea.

## Steps

1. **Parse the user's brief description**
   - Identify the core feature/change requested
   - Determine which module(s) are impacted

2. **Expand with details**
   - Add reasoning/context if not obvious
   - List potential implementation considerations
   - Note any dependencies or blockers

3. **Add to `.agent/wishlist.md`**
   - Assign the next sequential number (W001, W002, etc.)
   - Place in the appropriate category section
   - Use the standard format below

4. **Confirm to user**
   - Show the formatted entry
   - Mention the item number for future reference

## Wishlist Entry Format

```markdown
### W### — [Short Title]

**Description**: [Expanded description of the feature]

**Rationale**: [Why this is useful, what problem it solves]

**Impacted Modules**:
- `module/path.py` — [what changes]
- `another/module.py` — [what changes]

**Considerations**:
- [Dependencies, edge cases, or implementation notes]

**Priority**: Low / Medium / High
**Added**: YYYY-MM-DD
```

## Categories in wishlist.md

| Section | Description |
|---------|-------------|
| **🎨 UI/UX** | Visual improvements, user experience |
| **🧠 Training & Models** | Training pipeline, model management |
| **🏷️ Labeling & Editor** | Image/video editor, annotations |
| **🔧 Infrastructure** | Backend, storage, performance |
| **📱 Desktop Client** | Tauri/native app features |
| **❓ Questions** | Things to investigate or clarify |

## Notes

- Keep entries concise but complete
- Link related items if applicable (e.g., "Related: W003")
- Move completed items to **✅ Completed** section with completion date
