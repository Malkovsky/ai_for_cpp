"""Attach complete definitions and sampled caller/callee costs to perf stacks."""

from pathlib import Path
import collections
import hashlib
import re
import subprocess
import shutil


def parse_dwarf(binary, dwarfdump="llvm-dwarfdump"):
    output = subprocess.check_output(
        [dwarfdump, "--debug-info", str(binary)], text=True
    )
    dies = {}
    stack = []
    current = None
    for line in output.splitlines():
        header = re.match(r"^0x([0-9a-f]+):(\s+)(DW_TAG_\w+|NULL)", line)
        if header:
            offset = int(header[1], 16)
            indent = len(header[2])
            tag = header[3]
            while stack and stack[-1]["indent"] >= indent:
                stack.pop()
            if tag == "NULL":
                current = None
                continue
            current = dict(
                offset=offset,
                indent=indent,
                tag=tag,
                parent=stack[-1]["offset"] if stack else None,
                attrs={},
                ranges=[],
            )
            dies[offset] = current
            stack.append(current)
            continue
        if current is None:
            continue
        attr = re.match(r"\s*(DW_AT_\w+)\s+\((.*)", line)
        if attr:
            current["attrs"][attr[1]] = attr[2]
            continue
        interval = re.search(r"\[0x([0-9a-f]+), 0x([0-9a-f]+)\)", line)
        if interval:
            current["ranges"].append((int(interval[1], 16), int(interval[2], 16)))

    def attribute(die, name, seen=None):
        seen = set() if seen is None else seen
        if die is None or die["offset"] in seen:
            return None
        seen.add(die["offset"])
        if name in die["attrs"]:
            return die["attrs"][name]
        for link in ["DW_AT_specification", "DW_AT_abstract_origin"]:
            m = re.match(r"0x([0-9a-f]+)", die["attrs"].get(link, ""))
            if m:
                value = attribute(dies.get(int(m[1], 16)), name, seen)
                if value is not None:
                    return value
        return None

    def string(value):
        m = re.match(r'"(.*)"\)', value or "")
        return m[1] if m else None

    def integer(value):
        m = re.match(r"(0x[0-9a-f]+|[0-9]+)", value or "")
        return int(m[1], 0) if m else None

    linkage = {
        string(attribute(d, "DW_AT_linkage_name"))
        for d in dies.values()
        if d["tag"] in ["DW_TAG_subprogram", "DW_TAG_inlined_subroutine"]
    }
    linkage.discard(None)
    linkage = sorted(linkage)
    demangled = subprocess.check_output(
        ["c++filt"], input="\n".join(linkage) + "\n", text=True
    ).splitlines()
    names = dict(zip(linkage, demangled))
    for d in dies.values():
        if d["tag"] not in ["DW_TAG_subprogram", "DW_TAG_inlined_subroutine"]:
            continue
        link = string(attribute(d, "DW_AT_linkage_name"))
        d["name"] = names.get(link, string(attribute(d, "DW_AT_name")))
        d["decl_file"] = string(attribute(d, "DW_AT_decl_file"))
        d["decl_line"] = integer(attribute(d, "DW_AT_decl_line"))
        d["call_file"] = string(d["attrs"].get("DW_AT_call_file"))
        d["call_line"] = integer(d["attrs"].get("DW_AT_call_line"))
        low = integer(d["attrs"].get("DW_AT_low_pc"))
        high = integer(d["attrs"].get("DW_AT_high_pc"))
        if low is not None and high is not None:
            d["ranges"].append((low, high))
        parent = dies.get(d["parent"])
        while parent is not None and parent["tag"] not in [
            "DW_TAG_subprogram",
            "DW_TAG_inlined_subroutine",
        ]:
            parent = dies.get(parent["parent"])
        d["function_parent"] = parent
    return dies


def masked_code(text):
    # Preserve positions/newlines while ignoring braces in comments and literals.
    token = re.compile(
        r'//[^\n]*|/\*[\s\S]*?\*/|R"([^ ()\\\t\r\n]{0,16})\([\s\S]*?\)\1"|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
    )
    return token.sub(lambda m: "".join("\n" if c == "\n" else " " for c in m[0]), text)


def function_extent(text, line):
    lines = text.splitlines(keepends=True)
    if line is None or not 1 <= line <= len(lines):
        return None
    offset = sum(map(len, lines[: line - 1]))
    code = masked_code(text)
    # A definition must have a parameter list and then a body, not a prototype.
    opening = code.find("(", offset)
    if opening < 0:
        return None
    level = 0
    end_signature = None
    for i in range(opening, len(code)):
        if code[i] == "(":
            level += 1
        elif code[i] == ")":
            level -= 1
            if level == 0:
                end_signature = i + 1
                break
    if end_signature is None:
        return None
    brace = code.find("{", end_signature)
    semicolon = code.find(";", end_signature)
    if brace < 0 or (semicolon >= 0 and semicolon < brace):
        return None
    level = 0
    end = None
    for i in range(brace, len(code)):
        if code[i] == "{":
            level += 1
        elif code[i] == "}":
            level -= 1
            if level == 0:
                end = code.count("\n", 0, i) + 1
                break
    if end is None:
        return None
    start = line
    # Include split return types, attributes and template declarations.
    while start > 1:
        previous = lines[start - 2].strip()
        if (
            not previous
            or previous.startswith(("#", "//", "/*", "*"))
            or previous.endswith(("}", ";", "{"))
        ):
            break
        start -= 1
    return start, end


def attach_sources(model, samples, binary, source_root, source_maps=(), collect=True):
    dwarfdump = shutil.which("llvm-dwarfdump")
    dies = parse_dwarf(binary, dwarfdump) if collect and dwarfdump else {}
    if collect and not dwarfdump:
        model["meta"]["warnings"].append(
            "llvm-dwarfdump unavailable: full definitions and inline call sites omitted"
        )
    names = {h["name"] for h in model["hotspots"]}
    hotspots = {h["name"]: h for h in model["hotspots"]}
    declarations = collections.defaultdict(list)
    inline = collections.defaultdict(list)
    for d in dies.values():
        if d["tag"] == "DW_TAG_subprogram" and d.get("name"):
            declarations[d["name"]].append(d)
        if (
            d["tag"] == "DW_TAG_inlined_subroutine"
            and d.get("name")
            and d.get("call_line")
        ):
            parent = d.get("function_parent")
            if parent:
                inline[(parent.get("name"), d["name"])].append(d)
    files = {}
    texts = {}
    definitions = {}

    def load(filename):
        if filename in texts:
            return texts[filename]
        path = Path(filename)
        for old, new in sorted(
            source_maps, key=lambda item: len(item[0]), reverse=True
        ):
            if filename == old or filename.startswith(old.rstrip("/") + "/"):
                path = Path(new + filename[len(old) :])
                break
        if not path.is_absolute():
            path = source_root / path
        try:
            text = path.read_text() if collect else None
        except (OSError, UnicodeError):
            text = None
        texts[filename] = text
        return text

    for name in names:
        candidates = declarations.get(name, [])
        # Non-template demangling sometimes omits an explicit return type.
        if not candidates:
            matches = [key for key in declarations if name.endswith(" " + key)]
            if len(matches) == 1:
                candidates = declarations[matches[0]]
        for d in sorted(
            candidates, key=lambda d: ("DW_AT_declaration" in d["attrs"], d["offset"])
        ):
            filename = d.get("decl_file")
            text = load(filename) if filename else None
            extent = (
                function_extent(text, d.get("decl_line")) if text is not None else None
            )
            if extent:
                definitions[name] = dict(
                    path=filename,
                    start=extent[0],
                    end=extent[1],
                    decl_line=d["decl_line"],
                )
                break
    for name in names:
        h = hotspots[name]
        definition = definitions.get(name)
        model.setdefault("functions", {})[name] = dict(
            name=name,
            total_weight=h["weight"],
            self_weight=h["self_weight"],
            samples=h["samples"],
            sources=h["sources"],
            definition=definition,
            calls=[],
            unresolved_call_weight=0,
        )
    edges = collections.Counter()
    edge_samples = collections.Counter()
    mapping = collections.Counter()
    cache = {}

    def callsite(caller, callee):
        key = (
            caller["name"],
            callee["name"],
            caller["ip"],
            callee["ip"],
            caller["source"],
        )
        if key in cache:
            return cache[key]
        parent_name, child_name = caller["name"], callee["name"]
        definition = definitions.get(parent_name)
        candidates = inline.get((parent_name, child_name), [])
        if not candidates:
            keys = [
                pair
                for pair in inline
                if parent_name.endswith(" " + str(pair[0]))
                and child_name.endswith(" " + str(pair[1]))
            ]
            if len(keys) == 1:
                candidates = inline[keys[0]]
        address = callee.get("address")
        sites = {
            (d["call_file"], d["call_line"])
            for d in candidates
            if address is not None and any(lo <= address < hi for lo, hi in d["ranges"])
        }
        method = "DWARF inline call site"
        if not sites:
            # Return-address attribution may use the instruction just before PC.
            sites = {
                (d["call_file"], d["call_line"])
                for d in candidates
                if address is not None
                and any(lo <= address - 1 < hi for lo, hi in d["ranges"])
            }
        site = next(iter(sites)) if len(sites) == 1 else None
        if site is None and definition:
            location = re.match(r"^(.*):(\d+)(?:\s.*)?$", caller["source"])
            if (
                location
                and location[1] == definition["path"]
                and definition["start"] <= int(location[2]) <= definition["end"]
            ):
                # Only accept a caller-line fallback when it contains a call to
                # this callee; otherwise retain an unresolved edge.
                line = int(location[2])
                code = load(location[1]).splitlines()[line - 1]
                namepart = child_name.split("(")[0]
                match = re.search(
                    r"([~A-Za-z_][A-Za-z_0-9]*)(?:<[^<>]*>)?\s*$", namepart
                )
                if match and re.search(
                    r"\b" + re.escape(match[1]) + r"\s*(?:<[^;{}]*>)?\s*\(", code
                ):
                    site = (location[1], line)
                    method = "Caller source line"
        if (
            site
            and definition
            and (
                site[0] != definition["path"]
                or not definition["start"] <= site[1] <= definition["end"]
            )
        ):
            site = None
        cache[key] = (site, method if site else "Unresolved")
        return cache[key]

    for sample in samples:
        frames = sample["frames"]
        # Global inclusive weights count each symbol once, including recursion.
        # Use its innermost occurrence so self + direct callees is conserved.
        last = {frame["name"]: i for i, frame in enumerate(frames)}
        for i in last.values():
            if i == len(frames) - 1:
                continue
            caller, callee = frames[i : i + 2]
            site, method = callsite(caller, callee)
            key = (
                caller["name"],
                callee["name"],
                site[0] if site else None,
                site[1] if site else None,
            )
            edges[key] += sample["weight"]
            edge_samples[key] += 1
            mapping[method] += sample["weight"]
    for (caller, callee, path, line), weight in edges.items():
        if path is None:
            model["functions"][caller]["unresolved_call_weight"] += weight
        model["functions"][caller]["calls"].append(
            dict(
                callee=callee,
                label=hotspots[callee]["label"],
                path=path,
                line=line,
                weight=weight,
                samples=edge_samples[(caller, callee, path, line)],
            )
        )
    # Embed complete definitions plus contexts for any remaining source locations.
    refs = collections.defaultdict(set)
    for h in model["hotspots"]:
        for location in h["sources"]:
            match = re.match(r"^(.*):(\d+)(?:\s.*)?$", location)
            if match and int(match[2]) > 0:
                refs[match[1]].add(int(match[2]))
    for definition in definitions.values():
        refs.setdefault(definition["path"], set())
    repo = source_root
    for filename, points in sorted(refs.items()):
        text = load(filename)
        path = Path(filename)
        try:
            display = str(path.relative_to(repo))
        except ValueError:
            display = filename
        entry = dict(
            path=filename, display=display, available=text is not None, lines={}
        )
        if text is not None:
            lines = text.splitlines()
            wanted = {
                i
                for point in points
                for i in range(max(1, point - 3), min(len(lines), point + 3) + 1)
            }
            for definition in definitions.values():
                if definition["path"] == filename:
                    wanted.update(range(definition["start"], definition["end"] + 1))
            entry.update(
                line_count=len(lines),
                lines={
                    str(i): lines[i - 1] for i in sorted(wanted) if 1 <= i <= len(lines)
                },
                sha256=hashlib.sha256(text.encode()).hexdigest(),
            )
        files[filename] = entry
    model["source_files"] = files
    model["meta"]["source_annotation"] = dict(
        full_definitions=len(definitions),
        functions=len(names),
        call_edge_mapping=dict(mapping),
        percentage_denominator="All selected period weights",
        line_cost="Inclusive cost of direct counted callees; nested callees are not added twice",
    )
