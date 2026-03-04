

```markdown
# Developer Guide: Building Custom Skills for Google Antigravity

## 1. Concept Overview
In Google Antigravity, a **Skill** is a directory-based package that extends the agent's capabilities using **Progressive Disclosure**. 

- **Purpose:** To provide specialized knowledge or workflows (e.g., database migration, code style enforcement) without overloading the global context window.
- **Trigger Mechanism:** Skills are **Agent-Triggered**. The agent scans the `description` in the skill's metadata to determine semantic relevance to a user's prompt.
- **Scope:**
    - **Workspace Scope:** `<workspace-root>/.agent/skills/` (Project-specific).
    - **Global Scope:** `~/.gemini/antigravity/skills/` (User-wide utilities).

## 2. Directory Structure
A Skill must adhere to a strict directory structure to be parsed correctly.

```text
my-skill-name/
├── SKILL.md            # [REQUIRED] Definitions, triggers, and instructions
├── scripts/            # [OPTIONAL] Python, Bash, Node scripts for execution
│   └── run_task.py
├── resources/          # [OPTIONAL] Static templates, text files, or headers
│   └── template.txt
└── examples/           # [OPTIONAL] Few-shot input/output examples
    ├── input.json
    └── output.py

```

## 3. The `SKILL.md` Definition File

This is the "brain" of the skill. It consists of YAML Frontmatter and a Markdown Body.

### 3.1 YAML Frontmatter (Metadata)

This section is indexed by the agent's high-level router.

```yaml
---
name: unique-skill-name
description: A detailed description of when to use this skill. This acts as the SEMANTIC TRIGGER. It must be verbose enough for the LLM to recognize intent (e.g., "Use this skill to validate SQL schema files against company safety policies").
---

```

### 3.2 Markdown Body (Instructions)

This content is injected into the context window *only* when the skill is activated.

**Required Sections:**

1. **Goal:** What defines success?
2. **Instructions:** Step-by-step logic for the agent.
3. **Constraints:** What is strictly forbidden?
4. **Examples (Optional):** Few-shot patterns.

## 4. Implementation Patterns

### Pattern A: Pure Instruction (The "Router")

Used for enforcing text-based rules (e.g., Commit Messages, Documentation Style).

* **Mechanism:** The `SKILL.md` body contains formatting rules. No scripts required.

### Pattern B: Asset Utilization (The "Reference")

Used for injecting static boilerplate to save context tokens.

* **Mechanism:** Place text in `resources/`.
* **Instruction:** "Read `resources/HEADER.txt` and prepend content to the target file."

### Pattern C: Learning by Example (The "Few-Shot")

Used for complex transformations (e.g., JSON to Pydantic, Code Migration).

* **Mechanism:** Place "before" and "after" files in `examples/`.
* **Instruction:** "Analyze `examples/input.json` and `examples/output.py` to understand the coding style and structure, then apply this pattern to the user's input."

### Pattern D: Tool Use (The "Executor")

Used for deterministic logic, validation, or dangerous operations (e.g., DB Schema Validation).

* **Mechanism:** Place logic in `scripts/` (e.g., `validate.py`).
* **Instruction:** "Do not guess. Execute `python scripts/validate.py <args>` and interpret the Exit Code (0 = Success, 1 = Error)."

## 5. Master Template

When creating a new skill, use the following template structure:

### File: `<skill-name>/SKILL.md`

```markdown
---
name: <skill-name>
description: <SEMANTIC_TRIGGER_PHRASE>
---

# <Skill Name>

## Goal
<One sentence summary of the objective.>

## Instructions
1. **Analyze Context**: <Instruction on what to look for in user input>
2. **Execute Logic**: 
   - <Instruction step>
   - <Instruction step>
   *(If using scripts)*: "Run the script located at `scripts/my_script.py` using the command..."

## Constraints
- <Constraint 1>
- <Constraint 2>

## Resources & Examples
- Refer to `examples/` for structure patterns.
- Refer to `resources/` for templates.

```

## 6. Distinctions for the Agent

* **vs. Rules:** Rules are always active constraints (Guardrails). Skills are loaded on demand.
* **vs. Workflows:** Workflows are user-triggered (`/command`). Skills are agent-triggered by reasoning.
* **vs. MCP:** MCP servers are for persistent connections (DBs, Slack). Skills are for ephemeral tasks (Code formatting, file generation).

```

### Next Step
Would you like me to act as the agent now and create a specific skill (e.g., a "Code Reviewer" or "Test Generator") using this guide?

```