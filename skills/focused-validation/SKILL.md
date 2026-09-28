---
name: focused-validation
description: Scope focused C++ builds, CTest tests, and Google Benchmark runs to changed files or a structure/family. Use during experiments to avoid broad integration builds, or before integration to map affected targets.
---

# Affected Build, Test, and Benchmark Scope

Select the smallest useful validation for the current change. The analyzer
is read-only: it emits candidates
and commands; it does not build or run tests/benchmarks.

Read the project instructions and
`agentic/local/cpp/skills/focused-validation/EXAMPLES.md` when present.

## Choose scope before building

- **Experiment:** repeat `--changed-file` for the implementation and shared
  headers actually being changed. This replaces branch/working-tree scope, so
  unrelated dirty files and older feature work do not pull in integration targets.
- **Working change:** `--working-tree-only` includes staged, unstaged, and
  untracked files without branch history.
- **Integration:** `--baseline main` (or the project baseline) uses
  `<baseline>...HEAD` plus local changes. Broaden once a candidate is selected
  or the user requests finalization, not after each local edit.

Reuse a compatible build tree and pass its compile database explicitly.
Configure the project's preset only if needed; do not build everything just to
find affected targets. Analyze separate test/benchmark databases if applicable.
Automatic newest-database selection remains for compatibility but may choose
an unrelated configuration.

```sh
python3 agentic/cpp/skills/focused-validation/analyze_scope.py \
  --compile-commands build/release/compile_commands.json \
  --changed-file include/project/structure.h --format json
```

## Prefer automated metadata; inspect manually only when unresolved

For CMake projects, request native target metadata once in the existing build
tree, then reconfigure with its existing options/preset (no compilation):

```sh
mkdir -p build/release/.cmake/api/v1/query/client-focused-validation
touch build/release/.cmake/api/v1/query/client-focused-validation/codemodel-v2
touch build/release/.cmake/api/v1/query/client-focused-validation/cmakeFiles-v1
cmake -S . -B build/release
```

The analyzer first consumes the [CMake File API](https://cmake.org/cmake/help/latest/manual/cmake-file-api.7.html):
source ownership, executable artifacts, and transitive target dependents.
It checks configuration and configure-input freshness. A source compiled into
multiple targets conservatively selects all owners; no object-path guessing is
needed for those entries. CTest inventory verifies runtime test ownership.

If native metadata is missing, stale, or incomplete, refresh it first when
practical. Otherwise the automated fallback infers target names from compilation
output paths and reports `target_metadata` plus warnings. Link consumers remain
unresolved in fallback mode. Agent inspection is the last resort for reported
gaps, custom test launchers, or unsupported builds—not the default discovery
mechanism. Use `--format summary` for inspection; save `--format json` outside
the source tree when executing its exact commands. Do not load raw CMake/CTest
inventories or script source into context for normal use.

Both paths reuse fresh GCC/Clang `.o.d` dependencies. Missing/stale depfiles
fall back to bounded preprocessing, not C++ compilation or AST construction.
`--jobs` defaults to 2 and `--timeout` to 15 seconds per compiler invocation.
Generators that discard depfiles may need preprocessing again. Report cache
hits, compiler scans, elapsed time, and failures.

Use `--kind tests` or `--kind benchmarks` when only that validation is needed
(default `all`). With native metadata, scans include that kind's transitive
library prerequisites and skip unrelated targets. In inference fallback mode,
dependency scanning stays conservative. Supply the CTest inventory for custom
test names; naming conventions alone yield candidates, not complete ownership.

`--target` restricts analysis and explicitly selects known targets when the
family is already established. Other targets are unexamined, not proven
unaffected. Without a restriction, File API target dependencies propagate impact
to consumers automatically. These include build-order dependencies, so selection
may be conservative. Metadata cannot establish runtime benchmark case coverage.

## Build and test the chosen slice

Review `affected_targets`, `affected_test_targets`, and
`affected_benchmark_targets`. `build_command` uses explicit `--target` values
and `--config` (default Release). Preserve project presets and use the sanitizer
build for relevant fallback checks. Unknown targets are errors. Infrastructure
changes produce conservative scope, not an instruction to build everything.

Runtime filters reduce execution, **not compilation**. A family translation
unit instantiating every implementation can still take minutes. During
iteration, prefer an existing narrow target or a temporary minimal probe that
includes only the concrete header and instantiates relevant types/operations.
Match the real target's compiler, definitions, language/ISA flags, and sanitizer
settings. Check a reference and boundaries; compile-only probes do not prove
correctness. Avoid adding every speculative variant to every integration suite
on every edit. Before promotion, run the shared family specification and
registered comparison benchmarks; probes do not replace that gate.

CTest is the normal test entry point. After building the selected targets,
capture the available runtime inventory:

```sh
ctest --test-dir build/release -C Release --show-only=json-v1 > /tmp/ctest-scope.json
python3 agentic/cpp/skills/focused-validation/analyze_scope.py \
  --compile-commands build/release/compile_commands.json \
  --changed-file include/project/structure.h \
  --ctest-json /tmp/ctest-scope.json --test-regex 'Structure|Boundary' --format json
```

The analyzer maps File API executable artifacts, target labels, or fallback
executable basenames to CTest names and emits an exact `ctest_command`.
Review reported unmapped targets and custom launchers.
Zero-match filters are errors. Refresh inventories after adding/building tests.
Large selections use labels only when the inventory proves an exact match;
otherwise they use inventory indices to avoid CTest's regex-size limit. Recreate
index-based plans after any registration/build change. Commands use
`--no-tests=error`; also verify the executed test count against the plan.
Typed-test numeric suffixes are not stable implementation IDs: verify their
types before filtering. Keep relevant ownership, exception, boundary, and
fallback cases when narrowing.

## Benchmark the hypothesis

Use the `benchmarks` skill for timing methodology. List runtime registrations
with `--benchmark_list_tests=true`. Select the operation, candidate and controls,
and a few representative sizes with comparable work/semantics. Count rows
before running: one binary may register thousands. Choose a bounded exploratory
duration and wall-clock timeout, accounting for setup and fixed iterations.
Run serial pinned Release timings after builds/tests finish; save JSON outside
the source tree and check actual cases, units, repetitions, skips, and noise.

`--benchmark-regex` records an explicit candidate filter; the analyzer does not
runtime-verify it. List with the same filter and reject zero matches. Missing
function-level mapping is not a reason to run a whole binary. Select a small
defensible operation/variant/size slice and state coverage uncertainty. Inspect
prerequisite/memory skips instead of counting them as measurements. Broaden only
for failures, unresolved risks, selected-candidate validation, or a broader request.

## Deeper analysis and limits

`--ast` opts into the older Clang call-graph heuristic; `--clangxx` selects Clang.
It can be expensive for templates and can miss dynamic registrations, overload
distinctions, or macro-generated names. It does not prove an exact runtime case
set. Normal analysis needs no Clang. Dependency failures conservatively retain
their targets, and an incomplete AST cannot erase a known affected target.

If rebuilds remain broad, inspect target compile commands/dependencies before
another run. Separate configure, compile/link, test, and fixture/timing costs.
Check clock-skew warnings and repeated no-op rebuilds, especially on mounted
filesystems. Do not repeatedly delete caches, create build trees, or increase
parallelism as a substitute for selecting scope.

Report files/targets, selected test/benchmark counts, commands, stage timings,
and deferred integration coverage. Do not describe a filtered run as validating
the entire affected family.

When comparing validation costs, use the same configuration and parallelism.
Separate first/forced compilation, edit-triggered rebuilds, warm no-op builds,
and CTest execution. State which targets actually recompiled. A runtime filter
cannot reduce a large translation unit's compilation cost. Do not invalidate
the whole build just to measure a local edit; use the build tool's dry run to
verify its rebuild set, and measure a controlled rebuild only when needed.
