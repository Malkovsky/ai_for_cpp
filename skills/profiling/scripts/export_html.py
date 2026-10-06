#!/usr/bin/env python3
"""Export one perf event as an offline, source-aware interactive flame graph."""

import argparse
import collections
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys

from source_analysis import attach_sources


HEADER = re.compile(
    r"^\s*(.*?)\s+(\d+(?:/\d+)?)\s+(?:\[\d+\]\s+)?"
    r"(\d+\.\d+):\s+(\d+)\s+(\S+):\s*(.*)$"
)
FRAME = re.compile(r"^\s*([0-9a-fA-F]+)\s+(.*?)\s+\((.*)\)\s*$")
OFFSET = re.compile(r"\+0x([0-9a-fA-F]+)$")


def parse_samples(text, event=None, root=None):
    """perf script fields: comm,pid,time,period,event,ip,sym,symoff,dso."""
    samples, events = [], set()
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if not lines or lines[0].lstrip().startswith("#"):
            continue
        header = HEADER.match(lines[0])
        if not header:
            raise ValueError(
                "Unsupported perf-script sample header; export the documented fields"
            )
        comm, pid, timestamp, period, sampled_event, tail = header.groups()
        events.add(sampled_event)
        if event and sampled_event != event:
            continue
        frames = []
        for line in ([tail] if tail else []) + lines[1:]:
            match = FRAME.match(line)
            if not match:
                raise ValueError(f"Unsupported perf-script frame: {line!r}")
            address, name, dso = match.groups()
            offset = OFFSET.search(name)
            entry = dict(
                name=name[: offset.start()] if offset else name,
                ip=int(address, 16),
                offset=int(offset[1], 16) if offset else 0,
                dso=dso,
                source="",
                address=None,
            )
            if (
                frames
                and frames[-1]["dso"] == entry["dso"] == "inlined"
                and (frames[-1]["name"], frames[-1]["ip"])
                == (entry["name"], entry["ip"])
            ):
                continue
            frames.append(entry)
        # Collapse perf's raw outer-symbol wrapper only when the same PC/symbol
        # reappears around inline frames. Real recursive calls remain intact.
        if frames:
            repeated = next(
                (
                    i
                    for i, f in enumerate(frames[1:], 1)
                    if (f["name"], f["ip"]) == (frames[0]["name"], frames[0]["ip"])
                ),
                None,
            )
            if (
                repeated
                and repeated > 1
                and frames[0]["dso"] != "inlined"
                and frames[repeated]["dso"] == frames[0]["dso"]
                and all(
                    f["dso"] == "inlined" and f["ip"] == frames[0]["ip"]
                    for f in frames[1:repeated]
                )
            ):
                frames = frames[1:]
        if not frames:
            frames = [
                dict(
                    name="[unresolved sample]",
                    ip=0,
                    offset=0,
                    dso="[unknown]",
                    source="",
                    address=None,
                )
            ]
        if root:
            boundary = next(
                (i for i, f in enumerate(frames) if f["name"] == root), None
            )
            if boundary is None:
                continue
            frames = frames[: boundary + 1]
        if int(period) <= 0:
            raise ValueError("Sample period must be positive")
        samples.append(
            dict(
                weight=int(period),
                time=float(timestamp),
                pid=int(pid.split("/")[0]),
                comm=comm,
                event=sampled_event,
                frames=list(reversed(frames)),
            )
        )
    if not event and len(events) > 1:
        raise ValueError("Multiple events in input; select exactly one with --event")
    if not samples or not sum(s["weight"] for s in samples):
        raise ValueError("No positive-weight samples match the event/root selection")
    return samples


def resolve_sources(samples, binary, dso, warnings, collect=True):
    output = subprocess.check_output(["nm", "-n", "-C", str(binary)], text=True)
    symbols = {}
    for line in output.splitlines():
        match = re.match(r"([0-9a-fA-F]+)\s+[tTwWiI]\s+(.*)", line)
        if match:
            symbols[match[2]] = int(match[1], 16)

    def target(module):
        return module == dso or Path(module).name == Path(dso).name

    pid_bases = collections.defaultdict(collections.Counter)
    for sample in samples:
        frames = sample["frames"]
        for i, frame in enumerate(frames):
            frame["target"] = target(frame["dso"])
            frame["module"] = frame["dso"]
            if frame["dso"] == "inlined":
                anchor = next(
                    (f for f in reversed(frames[:i]) if f["dso"] != "inlined"), None
                )
                frame["target"] = bool(
                    anchor and target(anchor["dso"]) and anchor["ip"] == frame["ip"]
                )
                frame["module"] = (
                    anchor["dso"] if anchor and anchor["ip"] == frame["ip"] else None
                )
        candidates = collections.Counter(
            f["ip"] - symbols[f["name"]] - f["offset"]
            for f in frames
            if target(f["dso"]) and f["name"] in symbols
        )
        sample["base"] = candidates.most_common(1)[0][0] if candidates else None
        if candidates:
            pid_bases[sample["pid"]].update(candidates)
    addresses = set()
    for sample in samples:
        base = sample["base"]
        if base is None and len(pid_bases[sample["pid"]]) == 1:
            base = next(iter(pid_bases[sample["pid"]]))
        for frame in sample["frames"]:
            if frame["target"] and base is not None and frame["ip"] >= base:
                frame["address"] = frame["ip"] - base
                addresses.add(frame["address"])
            elif frame["dso"] == "inlined" and not frame["target"]:
                module = (
                    Path(frame["module"]).name
                    if frame["module"]
                    else "unresolved module"
                )
                frame["name"] += f" [{module}]"
            elif frame["dso"] != "[unknown]" and not frame["target"]:
                # Prevent another DSO's identically named function from inheriting
                # the supplied executable's source definition.
                frame["name"] += f" [{Path(frame['dso']).name}]"
    if not addresses:
        warnings.append(
            "No load bias resolved for supplied binary; source PCs remain unavailable"
        )
    chains = {}
    # Keep argv bounded even for captures with many unique instruction PCs.
    ordered = sorted(addresses) if collect else []
    for start in range(0, len(ordered), 2048):
        debug = subprocess.check_output(
            [
                "addr2line",
                "-a",
                "-f",
                "-C",
                "-i",
                "-e",
                str(binary),
                *[hex(a) for a in ordered[start : start + 2048]],
            ],
            text=True,
        )
        address = None
        for line in debug.splitlines():
            if re.fullmatch(r"0x[0-9a-fA-F]+", line):
                address = int(line, 16)
                chains[address] = []
            elif address is not None:
                chains[address].append(line)
    for sample in samples:
        for frame in sample["frames"]:
            chain = chains.get(frame["address"], [])
            for i in range(0, len(chain) - 1, 2):
                if chain[i] == frame["name"] and chain[i + 1] != "??:0":
                    frame["source"] = chain[i + 1]
                    break


def label(name):
    short = name.split("(", 1)[0]
    return short if len(short) <= 100 else "…" + short[-99:]


def node(name):
    return dict(
        name=name,
        weight=0,
        self_weight=0,
        samples=0,
        self_samples=0,
        sources=set(),
        children={},
    )


def add_stack(root, frames, weight):
    current = root
    current["weight"] += weight
    current["samples"] += 1
    for frame in frames:
        current = current["children"].setdefault(frame["name"], node(frame["name"]))
        current["weight"] += weight
        current["samples"] += 1
        if frame["source"]:
            current["sources"].add(frame["source"])
    current["self_weight"] += weight
    current["self_samples"] += 1


def build_model(samples, metadata):
    root, reverse = (
        node("All selected samples"),
        node("All selected samples · bottom-up"),
    )
    folded, hotspots = collections.Counter(), {}
    for sample in samples:
        frames, weight = sample["frames"], sample["weight"]
        add_stack(root, frames, weight)
        add_stack(reverse, list(reversed(frames)), weight)
        folded[
            ";".join(f["name"].replace(";", ":").replace("\n", " ") for f in frames)
        ] += weight
        seen = set()
        for frame in frames:
            if frame["name"] in seen:
                continue
            seen.add(frame["name"])
            hotspot = hotspots.setdefault(frame["name"], node(frame["name"]))
            hotspot["weight"] += weight
            hotspot["samples"] += 1
            if frame["source"]:
                hotspot["sources"].add(frame["source"])
        leaf = hotspots[frames[-1]["name"]]
        leaf["self_weight"] += weight
        leaf["self_samples"] += 1
    next_id = 0

    def finish(current):
        nonlocal next_id
        current["id"] = next_id
        next_id += 1
        current["label"] = label(current["name"])
        current["sources"] = sorted(current["sources"])
        current["children"] = [
            finish(c)
            for c in sorted(
                current["children"].values(), key=lambda c: (-c["weight"], c["name"])
            )
        ]
        return current

    root, reverse = finish(root), finish(reverse)
    for hotspot in hotspots.values():
        hotspot.pop("children")
        hotspot["sources"] = sorted(hotspot["sources"])
        hotspot["label"] = label(hotspot["name"])
    metadata.update(
        samples=len(samples), period_weight=root["weight"], event=samples[0]["event"]
    )
    return dict(
        root=root,
        reverse=reverse,
        hotspots=sorted(
            hotspots.values(), key=lambda h: (-h["self_weight"], h["name"])
        ),
        meta=metadata,
    ), folded


def validate(model):
    ids = set()

    def check(current):
        if current["id"] in ids:
            raise ValueError("Duplicate graph node")
        ids.add(current["id"])
        for field, own in [("weight", "self_weight"), ("samples", "self_samples")]:
            if current[field] != current[own] + sum(
                c[field] for c in current["children"]
            ):
                raise ValueError("Graph weights are not conserved")
        for child in current["children"]:
            check(child)

    check(model["root"])
    check(model["reverse"])
    total = model["root"]["weight"]
    if total != model["reverse"]["weight"] or total != sum(
        h["self_weight"] for h in model["hotspots"]
    ):
        raise ValueError("Global weights are not conserved")
    for function in model["functions"].values():
        if function["total_weight"] != function["self_weight"] + sum(
            c["weight"] for c in function["calls"]
        ):
            raise ValueError(f"Function costs are not conserved: {function['name']}")


def svg(model):
    root = model["root"]

    def depth(current):
        return 1 + max((depth(c) for c in current["children"]), default=0)

    height = depth(root) * 26 + 60
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="{height}" viewBox="0 0 1500 {height}">',
        "<style>text{font:12px monospace}rect:hover{stroke:#111;stroke-width:2}</style>",
        f'<text x="10" y="22">{html.escape(model["meta"]["title"])}</text>',
    ]

    def draw(current, x, y, width):
        hue = (
            20 + int(hashlib.sha256(current["name"].encode()).hexdigest()[:6], 16) % 40
        )
        tip = f"{current['name']}: total {100 * current['weight'] / root['weight']:.3f}%, self {100 * current['self_weight'] / root['weight']:.3f}%"
        parts.append(
            f'<g><title>{html.escape(tip)}</title><rect x="{x:.4f}" y="{y}" width="{width:.4f}" height="24" fill="hsl({hue},85%,68%)" stroke="white" stroke-width="0.5"/>'
        )
        if width > 28:
            text = current["label"][: max(0, int(width / 7) - 2)]
            parts.append(
                f'<text x="{x + 4:.4f}" y="{y + 16}">{html.escape(text)}</text>'
            )
        parts.append("</g>")
        left = x
        for child in current["children"]:
            child_width = width * child["weight"] / current["weight"]
            draw(child, left, y - 26, child_width)
            left += child_width

    draw(root, 10, height - 28, 1480)
    return "\n".join(parts + ["</svg>"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--perf-data", type=Path)
    source.add_argument("--perf-script", type=Path)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--dso", help="Recorded binary path/name if the preserved binary was renamed"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-map", action="append", default=[], metavar="OLD=NEW")
    parser.add_argument("--event")
    parser.add_argument(
        "--root", help="Exact root frame; also filters samples and changes denominator"
    )
    parser.add_argument("--title", default="Native perf profile")
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--perf-bin", default="perf")
    parser.add_argument("--no-source", action="store_true")
    args = parser.parse_args()
    maps = []
    for mapping in args.source_map:
        old, separator, new = mapping.partition("=")
        if not separator or not old or not new:
            parser.error("Source maps must have the form OLD=NEW")
        maps.append((old.rstrip("/"), new.rstrip("/")))
    binary = args.binary.resolve(strict=True)
    capture = json.loads(args.metadata.read_text()) if args.metadata else {}
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if capture.get("binary_sha256") and capture["binary_sha256"] != digest:
        parser.error("Binary hash differs from supplied capture metadata")
    warnings = []
    if capture.get("lost_samples"):
        warnings.append(f"Capture reports {capture['lost_samples']} lost samples")
    if args.perf_data:
        text = subprocess.check_output(
            [
                args.perf_bin,
                "script",
                "-i",
                str(args.perf_data),
                "--ns",
                "--inline",
                "-F",
                "comm,pid,time,period,event,ip,sym,symoff,dso",
            ],
            text=True,
        )
        header = subprocess.check_output(
            [
                args.perf_bin,
                "report",
                "-i",
                str(args.perf_data),
                "--stdio",
                "--header-only",
            ],
            text=True,
        )
        lost = re.search(r"Total Lost Samples:\s*(\d+)", header)
        if lost:
            capture["lost_samples"] = int(lost[1])
            if int(lost[1]):
                warnings.append(f"Capture reports {lost[1]} lost samples")
    else:
        text = args.perf_script.read_text()
    samples = parse_samples(text, args.event, args.root)
    resolve_sources(
        samples, binary, args.dso or str(binary), warnings, not args.no_source
    )
    metadata = dict(
        title=args.title,
        binary=str(binary),
        binary_sha256=digest,
        root_filter=args.root,
        scope=capture.get("scope", "capture scope not specified"),
        warnings=warnings,
        capture=capture,
    )
    model, folded = build_model(samples, metadata)
    attach_sources(
        model, samples, binary, args.source_root.resolve(), maps, not args.no_source
    )
    metadata["functions_resolved"] = metadata["source_annotation"]["full_definitions"]
    validate(model)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assets = Path(__file__).resolve().parent.parent / "assets"
    page = (
        (assets / "viewer.html")
        .read_text()
        .replace("__TITLE__", html.escape(args.title))
    )
    script = (
        (assets / "viewer.js")
        .read_text()
        .replace(
            "__MODEL__",
            json.dumps(model, separators=(",", ":")).replace("<", "\\u003c"),
        )
    )
    page = page.replace("__SCRIPT__", script)
    (out / "index.html").write_text(page)
    (out / "model.json").write_text(json.dumps(model, indent=2) + "\n")
    (out / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (out / "profile.folded").write_text(
        "\n".join(f"{stack} {weight}" for stack, weight in sorted(folded.items()))
        + "\n"
    )
    (out / "flamegraph.svg").write_text(svg(model))
    print(
        f"HTML report: {out / 'index.html'} ({len(samples)} samples, {model['root']['weight']} period weights)"
    )
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"HTML export failed: {error}") from error
