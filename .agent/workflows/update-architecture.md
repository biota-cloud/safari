---
description: Manually update documentation after implementing architectural changes
---

# Update Architecture Reference Workflow

Run this **manually** after implementing architectural changes that should be documented.

## Boundaries

> [!CAUTION]
> - **ADD only** what is new or changed — never modify unrelated sections
> - **Quote the exact change** you're documenting before making edits
> - **Do NOT "clean up" or "improve"** existing content unless explicitly asked
> - If unsure whether something should change, **ASK first**

## Steps

1. **State what changed** (before touching the file):
   - List the specific files/features that were implemented
   - What new pattern or behavior should be documented?

2. **Find where it belongs**:
   - Search for the relevant section header
   - If no section exists, propose a location

3. **Propose the exact addition** (show to user):
   - Write out the markdown you plan to add
   - Keep it minimal — only document what's new
   - Wait for approval if the change is non-trivial

4. **Add content only**:
   - Insert new sections/rows/info
   - Do NOT edit or remove existing content (even if it seems obsolete)

5. **Update revision history**:
   - Add one concise line to the Revision History table
   - Format: `| YYYY-MM-DD | Added: [brief description] |`

6. **Review for accidental changes**:
   ```bash
   git diff docs/architecture_reference.md
   ```
   - Verify only intended lines changed
   - Revert any accidental modifications

7. **Identify obsolete content** (ask user before removing):
   - Search for references to code/patterns that were replaced
   - List any sections that may now be outdated
   - **DO NOT delete** — present findings to user for approval
   - Example: "The new shared core may obsolete the 'Manual Parity' warning in section X — should I update?"

## Anti-Patterns

- ❌ "While I'm here, let me also update this table..."
- ❌ "I'll clean up this section to be more accurate"
- ❌ "This row seems outdated, I'll fix it"

## When to Ask Instead of Act

- Changing existing values in tables
- Removing content
- Restructuring sections
- Any edit beyond **pure addition**
