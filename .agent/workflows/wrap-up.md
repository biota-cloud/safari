---
description: End of session wrap-up routine — update roadmap progress and summarize work
---

# Wrap-Up Workflow

Run this at the end of each work session to keep the roadmap current.

## Steps

1. **Update Progress Tracking in the active roadmap** (`.agent/architecture-roadmap-v2.md`):
   - Update the Progress Tracking table at the bottom
   - Set **Status** to current phase status (⬜/🟡/✅)
   - Set **Started/Completed** dates as applicable

2. **Mark completed checkboxes in the active roadmap** (`.agent/architecture-roadmap-v2.md`):
   - Change `[ ]` to `[x]` for any steps that were fully completed
   - Change `[ ]` to `[/]` for any steps that are in progress but not finished

3. **Update `.agent/context.md` (Session Log)**:
   - Check the last session number in `## 📝 Session Notes` and increment it (e.g. Session 3 -> Session 4)
   - Add a new entry: `### Session N — [Short Title] (YYYY-MM-DD)`
   - Bullets:
     - **Key Findings**: Discovery of new patterns, bugs fixed, or system behaviors.
     - **Decisions**: Architectural choices made (e.g., "Use Canvas instead of rx.image").
     - **Anti-Patterns**: "Wrong solutions" attempted that failed (e.g., "Don't use `crossOrigin` with cached images").
   - Move the new session to the top of the Notes list.

4. **Update `.agent/tech_debt.md`** (if applicable):
   - Add any deprecation warnings encountered during the session
   - Add any refactoring opportunities or cleanup tasks identified
   - Move resolved items to the "Resolved ✅" section

5. **Skill Maintenance** (proactive):
   - Review the session for recurring patterns that could become skills
   - If a new pattern was solved 2+ times, propose creating a skill
   - If an existing skill gave outdated guidance, update it
   - Skills: `.agent/skills/` (workspace) or `~/.gemini/antigravity/skills/` (global)

6. **Summarize to user**:
   - List what was accomplished this session (2-4 bullet points)
   - Note any blockers or decisions that need user input
   - Suggest what to tackle next session
   - **Remind**: If architecture changed, trigger `/update-architecture` manually