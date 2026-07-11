# Shared C++ Agent Guidance

Reusable C++ agent skills, MCPs and related commands for research and engineering
workflows.

## Skill Summary

Token counts use `tiktoken:o200k_base`. Metadata is the skill name and
description, body is the post-frontmatter `SKILL.md` content, and optional is
additional bundled readable context. Project-local overlays are excluded.

| Skill | Description | Metadata | Body | Optional |
|---|---|---:|---:|---:|
| `benchmarks` | Run and interpret Google Benchmark suites. | 17 | 1,772 | 0 |
| `benchmarks-affected` | Find benchmarks affected by branch changes. | 25 | 615 | 0 |
| `benchmarks-compare-revisions` | Compare benchmark performance across Git revisions. | 31 | 2,000 | 0 |
| `capture-learnings` | Preserve durable research engineering learnings. | 51 | 1,206 | 0 |
| `cmake` | Configure, build, and test CMake projects. | 21 | 740 | 0 |
| `diagnose-segfault` | Diagnose C++ crashes and memory errors. | 71 | 1,188 | 0 |
| `estimate-token-usage` | Measure skill, MCP, and general context usage. | 47 | 725 | 0 |
| `optimization-experiment` | Run validated C++ optimization experiments. | 40 | 1,604 | 0 |
| `paper-search` | Search academic literature and manage references. | 88 | 1,062 | 314 |
| `pdf` | Read, create, and combine PDF files. | 31 | 680 | 0 |
| `setup-cpp-repo` | Scaffold a modern C++20 repository. | 65 | 1,047 | 1,161 |
| **Total** | | **487** | **12,639** | **1,475** |

## Recommended MCP Servers

Tool metadata counts use `tiktoken:o200k_base` over each canonical tool name,
description, and input schema. Client-specific wrappers are excluded. We keep the link to a specific commit for reproducibility but in general it is reommended to use the latest version. 

| MCP | Description | Commit | Tools | Tool metadata |
|---|---|---:|---:|---:|
| [Clang Index](https://github.com/kandrwmrtn/cplusplus_mcp/tree/4f009b7d7b39ae09893d9c67cd9bd8b31e6d7e86) | Index and query C++ symbols, inheritance, and call graphs with libclang. | `4f009b7` | 14 | 1,017 |
