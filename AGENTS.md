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

For the shared skill summary:

- `Metadata` counts only the `name` and `description` values.
- `Body` counts only post-frontmatter `SKILL.md` content.
- `Optional` counts additional bundled readable context, excluding scripts,
  assets, UI metadata, and consuming-project overlays.

When shared skill metadata, bodies, or optional context change, regenerate the
token counts and update the single `Skill Summary` table in `README.md`. Keep
its descriptions short and human-facing. Do not add operational instructions
or command examples to that README section.

For the `Recommended MCP Servers` table, link the MCP name directly to its
official source, pin the measured version or commit, and count the exact
recommended tool set. `Tool metadata` includes each tool name, description,
and input schema, but not client-specific wrappers.

## Change Discipline

- Preserve existing skill interfaces unless a broader change is intentional.
- Keep edits scoped to the owning skill or command.
- Check for stale names and paths after renaming a skill.
- Keep generated caches, bytecode, environment files, and consuming-project
  artifacts out of this repository.
