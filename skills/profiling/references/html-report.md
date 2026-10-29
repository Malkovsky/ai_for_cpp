# Optional HTML export

Generate this artifact when the user asks for a navigable flame graph or HTML
profile. Use perf text and assembly for normal agent analysis.

## Presentation continuity

`assets/viewer.html` and `assets/viewer.js` are the canonical report template.
Generate through `scripts/export_html.py` and use its interactive `index.html`
as the primary deliverable. If a destination requires `report.html`, expose
the same viewer there with working relative links. Do not replace the entry
point with a custom summary dashboard unless the user asks for that format.

Preserve these defaults across workloads:

- Light neutral background, white bordered panels, warm flame bars, restrained
  typography and spacing.
- Header with workload title, scope, capture metadata and export links.
- Flame graph first, followed by the frame/source panel, sortable function
  hotspots, and expandable capture details.
- Zoom, breadcrumbs, Back/Reset, regex search, top-down/bottom-up and
  flame/icicle controls; global Total/Self metrics and source navigation.
- Standalone offline HTML with embedded scripts, styles, data and source.

Customize titles, concise symbol labels, units, workload descriptions and
measured metadata without redesigning the viewer. Retain full symbols for
inspection. Never copy another workload's seeds, query-pool description,
hardware or timing claims. Extra findings and source heatmaps may be companion
artifacts linked from the viewer; they should not displace it.

When a user supplies an earlier report as a reference, compare its template
with the bundled assets before making changes. Reuse the shared template when
it already matches. Keep project-specific branding and reference locations in
the consuming project's local overlay, not in this shared skill.

Source-resolution failures are data limitations, not a reason to change report
style. Keep unresolved definitions and call edges visible. If a matching
captured source body is supplied separately, label its provenance and distinguish
sampled instruction locations from resolved call-line costs; do not invent
missing attribution to make the panel look complete.

Before delivery, check the primary link opens the viewer, export links resolve,
capture weights are unchanged, and zoom/back, search, direction/layout switching,
hotspot sorting and available source rendering work. Use a browser when available;
otherwise run viewer logic checks and disclose the lack of browser validation.
Update any portable report bundle after changing the viewer.

## Inputs and tools

- Python 3.10+; standard library only.
- GNU `objdump` supplies annotated assembly around sampled instruction addresses.
  If unavailable, the report retains addresses and explicitly labels missing
  disassembly.
- `perf` to decode a capture, plus GNU `nm`, `addr2line`, and `c++filt` for the
  matching ELF. `llvm-dwarfdump` enables complete definitions and inline call
  sites. When it is unavailable, the exporter retains line contexts and labels
  unavailable definitions; `--no-source` skips source collection entirely.
- The exact optimized binary recorded by perf, its debug information and the
  corresponding source. The supplied binary is source-resolved; other DSOs
  remain visible in the stacks but are not resolved against that binary.

```sh
python3 <skill>/scripts/export_html.py \
  --perf-data /tmp/profile/perf.data --binary /path/to/matching/binary \
  --source-root /path/to/source --output-dir /tmp/profile/html \
  --title 'Workload profile' --metadata /tmp/profile/capture.json
```

Existing perf-script text is also supported, with the fields below. Do not
replace a real capture with fabricated stacks for a performance claim.

```sh
perf script -i /tmp/profile/perf.data --ns --inline \
  -F comm,pid,time,period,event,ip,sym,symoff,dso > /tmp/profile/perf.script
python3 <skill>/scripts/export_html.py \
  --perf-script /tmp/profile/perf.script --binary /path/to/matching/binary \
  --source-root /path/to/source --output-dir /tmp/profile/html
```

`--event` selects one event when the input contains several. Different event
periods are never added together. `--root '<full symbol>'` selects stacks that
contain that exact frame and trims its callers. This changes the percentage
denominator to the selected stacks; it does not prove setup was excluded.
Without `--root`, startup and library callers are retained. Periods weight the
stacks; raw sample counts are also shown.

If the preserved executable was renamed, use `--dso /original/recorded/path`
to identify its module in the capture. Native recursive frames are retained;
adjacent duplicate inline frames emitted by perf are normalized.

For moved sources, repeat `--source-map OLD=NEW` to replace the longest matching
path prefix. `--source-root` makes relative paths readable and supplies a base
for relative debug paths. Source file hashes are recorded, but no exporter can
prove that current source matches an old binary; use the captured source revision.

## Output and interpretation

Open `index.html` directly. JavaScript, styles, data and source excerpts are
embedded; there are no network assets or package dependencies. `profile.folded`,
`flamegraph.svg`, `model.json` and `summary.json` are companion exports.

- Click a frame to zoom, use breadcrumbs/Back/Reset, search by regex, switch
  stack direction or flame/icicle layout, and sort the hotspot table.
- Hover/select a function for its complete contiguous body when DWARF resolves
  a definition. Otherwise see grouped contiguous source contexts per path.
- Total and Self are global shares of the selected period weights. Total counts
  a function once per sample; Self is the deepest counted frame. Recursive
  stacks remain in the graph; call-cost accounting uses the innermost occurrence
  per symbol per sample to avoid counting recursive ancestry twice.
- A call-line badge includes its direct counted callees and their descendants.
  Click it to inspect the largest callee. Unresolved edges stay separately
  listed; a missing badge does not mean the call is free.
- The source panel separates **Self %** (sampled leaf instruction weight at that
  source line) from **Callees %** (inclusive direct-callee costs). Both use the
  global selected-period denominator. Self source costs plus unmapped self
  weight equal the function's Self total; never substitute callee costs for
  work inside a large loop.
- Annotated assembly shows sampled ELF addresses, Self %, sample counts and
  three neighboring instructions on each side. Context instructions with no
  attributed samples show a dash, not a claim of zero execution cost. Source
  lines and assembly are alternative views of the same samples, not additive
  measurements. This supplies useful detail even when one kernel occupies the
  entire flame graph.
- C++ function extents use DWARF declaration lines and a comment/string-aware
  brace scan, not a full C++ parser. Macros, generated code, function-try-blocks
  and unusual declarators may yield incomplete or unavailable definitions.
  Out-of-line calls may remain unresolved when perf's caller PC is a return
  address. Do not infer exact source call timing from such cases.

The metadata panel shows event, scope, binary hash and supplied capture details.
Missing/lost samples, truncated DWARF stacks and unavailable sources limit the
report. Ordinary cycles attribute stalls/skid to sampled instructions; this is
neither a per-query timeline nor a measurement of individual instruction latency.
