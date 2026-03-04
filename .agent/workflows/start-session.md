---
description: Start of session routine — orient agent and show next steps
---

# Start Session Workflow

Run this at the beginning of each work session to get oriented.

## Steps

1. **Read Current Focus from the active roadmap** (`.agent/architecture-roadmap-v2.md`):
   - Identify the current Phase and Active Steps
   - Note any blockers listed
   - Check the Progress Tracking table at the bottom

2. **Read `.agent/context.md`** (CRITICAL):
   - Review key architecture decisions and their *nuances* (why a decision was made)
   - Check "Anti-Patterns" to avoid repeating specific past mistakes
   - Note any user preferences or specific "gotchas" recorded in Session Notes

3. **Scan `.agent/common-pitfalls.md`**:
   - Quick review before writing code
   - File grows over time — always check for new entries

4. **Consult `docs/architecture_reference.md`** (for architectural work):
   - Reference tables for inference flows, training, model loading patterns
   - Check common gotchas section before debugging
   - Verify any compute target or model backbone decisions

5. **Show the user a brief status**:
   ```
   📍 Current Focus: Phase X — [Name]
   📋 Next Steps: X.Y.Z → X.Y.W
   ⚠️ Blockers: [None / List them]
   
   Ready to continue. What would you like to tackle?
   ```

6. **If resuming mid-step**:
   - Check if there's any partially completed work
   - Ask user if they want to continue from where they left off or start fresh

## ⚠️ Critical Rules

> [!CAUTION]
> **DO NOT use browser_subagent for testing.** The user handles all testing at checkpoints to save tokens. If testing is needed, notify the user and wait for them to test and provide feedback/screenshots.
> **Do NOT update roadmap during start-session** — roadmap updates (checkboxes, Current Focus) happen only during `/wrap-up`

## Notes

- Don't start coding immediately — wait for user confirmation
- If the Current Focus seems outdated, ask user to confirm before proceeding
- **Review conversation history summary** — check for relevant context from previous sessions to maintain continuity and avoid revisiting resolved decisions or repeating past mistakes