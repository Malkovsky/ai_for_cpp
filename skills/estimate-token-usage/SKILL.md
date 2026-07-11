---
name: estimate-token-usage
description: Measure or estimate the context-token cost of agent skills, MCP tool descriptions, or general text and files. Use when auditing context budgets, comparing reusable instructions, inspecting MCP schema overhead, or checking additional project-local context.
---

# Estimate Token Usage

Use the bundled script for three distinct accounting tasks. Preserve the
reported method and encoding whenever results will be compared later.

## 1. Skills

Measure one, several, or every skill in a shared skills directory:

```bash
python3 agentic/cpp/skills/estimate-token-usage/scripts/estimate_tokens.py skills

python3 agentic/cpp/skills/estimate-token-usage/scripts/estimate_tokens.py skills \
  --skill benchmarks --skill cmake
```

The skills report intentionally excludes project-local overlays. Its columns
are:

- `metadata`: only the `name` and `description` values used for discovery.
- `body`: triggered `SKILL.md` instructions after frontmatter.
- `optional`: other bundled readable context, excluding scripts, assets, and
  UI metadata; it enters context only when read.

Use the `context` mode separately when a project-local `EXAMPLES.md`,
repository rule, or other additional file is relevant to the task.

## 2. MCP Descriptions

Measure MCP tool definitions exported as JSON:

```bash
python3 agentic/cpp/skills/estimate-token-usage/scripts/estimate_tokens.py mcp \
  list-tools.json

some-mcp-list-command | \
  python3 agentic/cpp/skills/estimate-token-usage/scripts/estimate_tokens.py mcp -
```

Accepted shapes include an MCP `tools/list` result with a `tools` array, an
array of tools, a single `{name, description, inputSchema}` tool, and OpenAI
function-tool objects. The report separates description text, input schema,
and a compact canonical definition. The canonical definition is a stable
comparison estimate, not a guarantee of a particular client's prompt wrapper.

## 3. General Context

Measure arbitrary UTF-8 files, directory trees, literal text, or standard
input:

```bash
python3 agentic/cpp/skills/estimate-token-usage/scripts/estimate_tokens.py context \
  AGENTS.md agentic/local/cpp/skills/benchmarks/EXAMPLES.md

python3 agentic/cpp/skills/estimate-token-usage/scripts/estimate_tokens.py context \
  agentic/local/cpp/skills --include 'EXAMPLES.md'

printf '%s' 'candidate prompt text' | \
  python3 agentic/cpp/skills/estimate-token-usage/scripts/estimate_tokens.py context -
```

Use `--text` for a literal argument. Directory inputs are recursive; restrict
them with repeatable `--include` and `--exclude` glob patterns when needed.
Binary and non-UTF-8 files are rejected rather than guessed.

## Counting Method

The default `--method auto` uses `tiktoken` with `o200k_base` when installed.
For a repeatable tokenizer-level audit, use the embedded dependency metadata:

```bash
uv run agentic/cpp/skills/estimate-token-usage/scripts/estimate_tokens.py \
  skills --method tiktoken --encoding o200k_base
```

Without `uv`, install `tiktoken` or use the explicitly labeled
`--method heuristic` fallback. Tokenizer counts are exact for the selected text
and encoding, not for a complete model request. Model hosts may add chat
templates, tool wrappers, and other instructions.

All three modes support `--format json` for automation.

Read `agentic/local/cpp/skills/estimate-token-usage/EXAMPLES.md` when present
for project-specific invocations and interpretation.
