---
name: capture-learnings
description: Capture durable, evidence-backed learnings from exploratory C++ research engineering, especially immediately before requested context compaction, including experiments, benchmarks, literature-driven implementations, failed approaches, and unexpected behavior, then propose the smallest appropriate documentation or skill update.
---

# Capture Learnings Skill

Use this skill near the end of research-heavy engineering work, or when the
user asks to preserve lessons from a task. When the user requests context
compaction, run this workflow immediately before producing the compaction
checkpoint. The goal is to retain knowledge that will prevent repeated
investigation or improve future decisions without turning temporary
observations into permanent rules.

## Compaction Trigger

Treat an explicit request to compact, summarize for compaction, or prepare for
context loss as a trigger for this skill. Complete the learning capture before
writing the session handoff:

1. Extract and route durable learnings using the workflow below.
2. Validate any approved durable updates.
3. Write a separate compaction checkpoint containing transient task state,
   pending work, relevant identifiers, and verification status.

Do not mix branch hashes, temporary paths, uncommitted-file inventories, or
next-step checklists into durable skills merely because they are important to
the handoff. Conversely, do not leave reusable research lessons only in the
compaction checkpoint when an appropriate durable surface exists.

If compaction is imminent and there is not enough time to update durable
surfaces safely, record candidate learnings with their evidence and proposed
destinations in the checkpoint. Mark them as pending rather than writing
unverified rules.

## Inputs

Inspect the strongest available evidence from the completed work:

- source and test diffs
- benchmark commands, raw results, and comparison tables
- profiler or hardware-counter output
- failed attempts and the evidence that rejected them
- papers, specifications, and implementation references
- build, platform, compiler, and feature-gate context
- user corrections and review findings

Do not treat the conversation summary alone as evidence when repository state or
raw artifacts are available.

## Step 1 - Extract Candidate Learnings

Identify non-obvious observations that could change future work. Useful
candidates include:

- a reusable algorithmic or implementation technique
- a correctness invariant, edge case, or tie-breaking rule
- a benchmark or profiling method that materially improved signal quality
- a negative result that rules out an attractive but ineffective approach
- a toolchain, compiler, architecture, or feature-gate constraint
- a workflow failure that a small procedural change would prevent
- a literature-to-implementation detail not obvious from the cited source

Exclude ordinary task narration, facts obvious from the current code, and
preferences that applied only to one transient request.

## Step 2 - Verify and Bound Each Claim

For every candidate, record:

1. **Claim**: the smallest statement supported by the evidence.
2. **Evidence**: tests, measurements, source locations, or references.
3. **Scope**: general C++, a narrower domain or platform, or one project.
4. **Confidence**: established, provisional, or unresolved.
5. **Reuse value**: what future mistake, repeated work, or poor decision it
   prevents.

Do not generalize a single machine measurement into a universal performance
rule. Preserve workload, compiler, CPU, build mode, data shape, and sample-size
conditions when they affect the conclusion.

## Step 3 - Choose the Durable Destination

Route each accepted learning to the narrowest appropriate surface:

| Learning type | Destination |
|---|---|
| Cross-project workflow or technique | Shared skill or shared reference |
| Project-specific command, path, or architecture rule | Project skill overlay or `AGENTS.md` |
| Public API contract or invariant | API documentation and tests |
| Accepted performance baseline | Relevant source, benchmark file, or maintained performance document |
| Detailed experiment history or negative result | Experiment log or research note |
| Uncertain but promising hypothesis | Research backlog or explicitly provisional note |
| Temporary diagnostic detail | Do not persist |

Prefer updating an existing skill or document over creating a parallel source of
truth. Keep project-specific names, paths, benchmark binaries, and configuration
out of shared skills; place them in the consuming project's overlay.

## Step 4 - Propose Before Writing

Present a compact learning proposal containing:

- the candidate learning
- its evidence and scope
- the proposed destination
- whether it updates an existing rule or adds a new one

Do not modify durable instructions merely because a task completed. Require
explicit user approval unless the user already asked to capture all supported
learnings as part of the task.

## Step 5 - Write Minimal Updates

After approval:

- state the rule before its rationale
- keep claims falsifiable and scoped
- link or name the evidence needed to re-evaluate the rule
- preserve useful negative results without copying full failed implementations
- remove superseded guidance instead of appending contradictory guidance
- keep shared instructions generic and place concrete project examples in the
  local overlay

Add a new skill only when the learning defines a repeatable multi-step workflow.
Use `AGENTS.md` for durable repository conventions, not detailed research
reports.

## Step 6 - Validate the Capture

Before finishing:

1. Re-read the updated surface in context and check for contradiction or
   duplication.
2. Confirm every new claim is supported by accessible evidence.
3. Confirm project-local details did not leak into shared guidance.
4. Run any repository skill validator or formatting check that applies.
5. Report what was captured, where it was stored, and which candidates were
   intentionally rejected.

## Guardrails

1. Evidence is required; repetition in a conversation is not validation.
2. Preserve conditions around performance conclusions.
3. Separate established results from hypotheses.
4. Prefer the smallest existing durable surface.
5. Never store secrets, private data, credentials, or machine-specific paths.
6. Do not turn every completed task into new process documentation.
7. Do not retain failed probes unless the negative result has clear reuse value.
8. Do not rewrite production code solely to make a learning easier to document.
