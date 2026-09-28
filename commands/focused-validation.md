---
description: Scope affected build targets, CTest cases, and benchmark candidates for an experiment or integration review.
---

# Affected Build, Test, and Benchmark Scope

Use the `focused-validation` skill as the canonical workflow. Prefer native
CMake File API metadata, then automated inference, then manual inspection of
reported gaps. Pass through its
analyzer options, including `--changed-file`, `--working-tree-only`, `--baseline`,
`--compile-commands`, `--kind`, `--target`, `--ctest-json`, `--test-regex`,
`--benchmark-regex`, `--config`, `--jobs`, `--timeout`, and optional `--ast`.

Report affected/selected targets, the build command, verified CTest selection,
candidate benchmark filter, cache/scan counts, elapsed time, and uncertainty.
Distinguish explicit restrictions from complete impact analysis.

This command performs discovery only. Do not automatically build integration
targets or run whole test/benchmark suites because function mapping is partial.
