# AGENTS.md - Shared C++ Agent Guidance

## Scope

This repository contains reusable C++ agent skills and commands. Keep all
content generic across C++ projects.

- Do not add consuming-project benchmark names, build options, architecture
  details, or absolute project paths.
- Keep reusable scripts and references beside the skill that owns them.
- Put project-specific examples and notes in the consuming repository under
  `agentic/local/cpp/skills/<skill>/EXAMPLES.md` or
  `agentic/local/cpp/commands/`.
- Commands should defer to skills for reusable workflow details rather than
  duplicate them.

## Skill Context

Design skills for progressive disclosure:

1. `name` and `description` are the minimum discovery metadata.
2. The post-frontmatter `SKILL.md` content is the skill body and is read when
   the skill applies.
3. Additional readable references are optional context and should be read only
   when relevant.
4. Scripts should normally be executed without loading their source into
   context. Read script source only when inspection or modification is needed.
5. Assets and UI metadata are not normal reasoning context.

In a consuming project, also read
`agentic/local/cpp/skills/<skill>/EXAMPLES.md` when its `AGENTS.md` requires a
local overlay. Do not treat local overlays as part of the shared skill's default
token cost.

## Skill Authoring

- Keep `SKILL.md` concise and procedural. Assume the agent already knows
  general C++ and software-engineering concepts.
- Make descriptions specific enough to select the skill without reading its
  body.
- Move conditional or detailed material into directly linked references.
- Use deterministic scripts for repeated or fragile mechanics.
- Keep reference links one level deep from `SKILL.md`.
- Add a new skill only for a reusable workflow with a distinct trigger.
- Do not add per-skill README files, changelogs, or setup guides.
- Validate new and modified skills with the available Codex skill validator and
  exercise bundled scripts on representative inputs.

## Token Accounting

Use the `estimate-token-usage` skill for skill, MCP, and general-context token
accounting. Do not duplicate its invocation or counting logic in guidance.

Keep the `Skill Summary` and `Recommended MCP Servers` tables descriptive. Do
not duplicate numeric token or tool counts there; the README badge links to the
current generated token report. Keep descriptions short and human-facing, and
do not add operational instructions or command examples to those tables.

For the `Recommended MCP Servers` table, include the measured version or short
commit in the linked MCP name, with the link targeting that pinned official
source revision. Do not add a separate version or commit column.

## Change Discipline

- Preserve existing skill interfaces unless a broader change is intentional.
- Keep edits scoped to the owning skill or command.
- Check for stale names and paths after renaming a skill.
- Keep generated caches, bytecode, environment files, and consuming-project
  artifacts out of this repository.
