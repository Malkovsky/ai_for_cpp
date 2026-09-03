# Shared C++ Agent Guidance

[![Token summary](https://how-much-tokens.onrender.com/badge/github/Malkovsky/ai_for_cpp.svg?metric=summary&encoding=o200k_base&v=repo-inventory-v14-badge3)](https://how-much-tokens.onrender.com/github/Malkovsky/ai_for_cpp/latest?encoding=o200k_base)

Reusable C++ agent skills, MCPs and related commands for research and engineering
workflows.

## Skill Summary

Current token usage for skills and MCP tools is available through the
[token summary report](https://how-much-tokens.onrender.com/github/Malkovsky/ai_for_cpp/latest?encoding=o200k_base)
linked by the badge above.

| Skill | Description |
|---|---|
| `benchmarks` | Run and interpret Google Benchmark suites. |
| `benchmarks-affected` | Find benchmarks affected by branch changes. |
| `benchmarks-compare-revisions` | Compare benchmark performance across Git revisions. |
| `capture-learnings` | Preserve durable research engineering learnings. |
| `cmake` | Configure, build, and test CMake projects. |
| `diagnose-segfault` | Diagnose C++ crashes and memory errors. |
| `estimate-token-usage` | Measure skill, MCP, and general context usage. |
| `optimization-experiment` | Run validated C++ optimization experiments. |
| `paper-search` | Search academic literature and manage references. |
| `pdf` | Read, create, and combine PDF files. |
| `setup-cpp-repo` | Scaffold a modern C++20 repository. |

## Recommended MCP Servers

Pinned links identify the measured upstream revisions. Use the latest compatible
version when installing.

| MCP | Description |
|---|---|
| [Clang Index @ 4f009b7](https://github.com/kandrwmrtn/cplusplus_mcp/tree/4f009b7d7b39ae09893d9c67cd9bd8b31e6d7e86) | Index and query C++ symbols, inheritance, and call graphs with libclang. |
| [LLDB MCP @ llvmorg-22.1.8](https://github.com/llvm/llvm-project/tree/llvmorg-22.1.8/lldb) | Bridge an MCP client to a local LLDB command session. |
