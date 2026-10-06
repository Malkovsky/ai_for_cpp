---
name: profiling
description: Profile native C++ workloads with Linux perf to identify hot paths, stalls, and memory or branch costs. Use for hotspot analysis, sampled call stacks, or hardware-counter investigations; optionally export an interactive source-aware HTML report when the user requests it.
---

# Native profiling with perf

Use native perf data to explain a performance problem. Default to text reports,
counters, annotated assembly, and a short interpretation. **Generate the HTML
report only when the user requests an HTML/flame-graph artifact.** It is a
human navigation aid, not a prerequisite for agent analysis.

## Establish a trustworthy capture

- Use the workload's optimized build with debug information (`-O3 -g` or its
  equivalent), actual target flags, and matching source. Avoid sanitizers and
  per-query timestamp/stage instrumentation when diagnosing native timing.
- Preserve the exact binary with its capture. Record compiler/options, input,
  seed/query generator, CPU, event, command, and capture scope. Use existing
  profiling/benchmark modes rather than changing the operation's semantics.
- Pin runs when supported. Separate setup, construction, validation and warmup
  from the measured query phase when that is the question. Perf control FIFOs
  can use an existing workload boundary; merely filtering for a function does
  not exclude calls made during construction.
- Check `perf --version`, `perf list` and a small capture. Permissions and PMU
  support vary, including under virtualization. Use a supported event or clearly
  label a fallback. Do not claim precise load attribution from ordinary cycles.
- Keep timing/counter runs sequential. Compare an unsampled run with the same
  binary and workload to gauge sampling disturbance; one pair is not a reliable
  universal overhead estimate.

A minimal capture helper records commands, a binary hash, text output and loss
information. It does **not** generate HTML:

```sh
python3 <skill>/scripts/record_perf.py --output-dir /tmp/profile \
  --cpu 0 --event cycles:u --frequency 999 --call-graph dwarf,4096 \
  -- ./build/profile/my_workload <workload arguments>
```

Use `--perf-bin /path/to/perf` when the PATH wrapper cannot service the running
kernel. For an existing workload-controlled window, add
`--control-prefix WORKLOAD_PERF`: the helper supplies `WORKLOAD_PERF_CTL` and
`WORKLOAD_PERF_ACK`. The workload must implement perf's FIFO protocol and report
its own phase/query counts; check them before treating the capture as query-only.
Otherwise the scope is the whole command, including setup.

## Analyze before building a viewer

```sh
perf report -i /tmp/profile/perf.data --stdio --no-children
perf report -i /tmp/profile/perf.data --stdio --children
perf annotate -i /tmp/profile/perf.data --stdio --symbol '<hot symbol>'
```

Interpret self and inclusive costs together. Inspect inlined ancestry and the
instructions around hot PCs, not just a source line. Ordinary sampling has skid;
a consuming popcount, compare or arithmetic instruction can receive a preceding
load's stall cost. Source percentages are attribution, not isolated operation
latencies. Flame-graph horizontal positions are not a timeline.

To explain a suspected bottleneck, use fixed equal work and small event groups:

```sh
perf stat -e '{cycles:u,instructions:u}' -- taskset -c 0 <fixed-work command>
perf stat -e '{branches:u,branch-misses:u}' -- taskset -c 0 <fixed-work command>
```

Reject unsupported, uncounted or multiplexed measurements; split groups or
select available events. Query-only timing needs a query-only counter window
as well. Distinguish demand loads from speculative prefetches, distinct touched
lines from cache misses, and independent-query throughput from dependent latency.
Use [the benchmarks skill](../benchmarks/SKILL.md) for Google Benchmark timing
and comparison conventions rather than duplicating its workflow.

## Optional user-requested HTML report

Read [the report reference](references/html-report.md) only for this mode.
`export_html.py` creates a standalone offline report with zoom/search, top-down
and bottom-up stacks, contiguous function bodies, total/self percentages and
resolved call-line costs. It also exports folded stacks for other viewers.

```sh
python3 <skill>/scripts/export_html.py \
  --perf-data /tmp/profile/perf.data --binary ./build/profile/my_workload \
  --source-root . --output-dir /tmp/profile/html --title 'Query profile'
```

The exporter reports weights for one event, preserves unknown leaves and cannot
invent missing debug/source information. Preserve capture provenance and inspect
lost samples, stack truncation, unresolved symbols and source freshness before
using the report to support a conclusion.
