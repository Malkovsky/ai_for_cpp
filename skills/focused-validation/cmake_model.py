"""Read authoritative CMake File API metadata without configuring or building."""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass
class CMakeModel:
    sources: dict = field(default_factory=dict)
    dependents: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)
    targets: set = field(default_factory=set)
    index: str = ""

    def consumers(self, targets):
        result = set(targets)
        pending = list(targets)
        while pending:
            for target in self.dependents.get(pending.pop(), ()):
                if target not in result:
                    result.add(target)
                    pending.append(target)
        return result

    def prerequisites(self, targets):
        dependencies = {}
        for dependency, consumers in self.dependents.items():
            for consumer in consumers:
                dependencies.setdefault(consumer, set()).add(dependency)
        return CMakeModel(dependents=dependencies).consumers(targets)


def load_model(build_dir, config):
    """Use only index-referenced replies, rejecting stale or incomplete models."""
    reply = build_dir / ".cmake/api/v1/reply"
    indexes = sorted(reply.glob("index-*.json"))
    if not indexes:
        raise ValueError("CMake File API reply missing")
    index_path = indexes[-1]
    index = json.loads(index_path.read_text())
    objects = {o["kind"]: o for o in index["objects"]}
    reference = objects["codemodel"]
    if reference["version"]["major"] != 2:
        raise ValueError("Unsupported CMake codemodel major version")
    model = json.loads((reply / reference["jsonFile"]).read_text())
    source_root = Path(model["paths"]["source"]).resolve()
    if Path(model["paths"]["build"]).resolve() != build_dir.resolve():
        raise ValueError("CMake File API belongs to a different build tree")
    configs = [c for c in model["configurations"] if c["name"] == config]
    if not configs:
        configs = [c for c in model["configurations"] if not c["name"]]
    if len(configs) != 1:
        raise ValueError(f"CMake File API has no unique {config} configuration")
    # Configure inputs are the authoritative freshness boundary. Compile-only
    # edits need dependency refresh, not CMake regeneration.
    inputs = json.loads((reply / objects["cmakeFiles"]["jsonFile"]).read_text())
    stamp = index_path.stat().st_mtime_ns
    for item in inputs["inputs"]:
        if item.get("isGenerated") or item.get("isCMake"):
            continue
        path = (source_root / item["path"]).resolve()
        if not path.exists() or path.stat().st_mtime_ns > stamp:
            raise ValueError(f"CMake configure input changed: {path}")
    result = CMakeModel(index=str(index_path))
    targets = [json.loads((reply / t["jsonFile"]).read_text())
               for t in configs[0]["targets"]]
    by_id = {t["id"]: t["name"] for t in targets}
    result.targets = set(by_id.values())
    for target in targets:
        name = target["name"]
        for src in target.get("sources", []):
            path = (source_root / src["path"]).resolve()
            result.sources.setdefault(path, set()).add(name)
        for dep in target.get("dependencies", []):
            if dep["id"] not in by_id:
                raise ValueError(f"Unresolved CMake dependency: {dep['id']}")
            result.dependents.setdefault(by_id[dep["id"]], set()).add(name)
        result.artifacts[name] = {
            (build_dir / a["path"]).resolve()
            for a in target.get("artifacts", [])
        }
    return result


def map_entries(entries, model):
    """A source shared by targets conservatively belongs to every listed owner.

    Keep each command/owner combination: differing flags may expose different
    include graphs. Do not disambiguate using object-path naming conventions.
    """
    mapped, missing = [], []
    for entry in entries:
        owners = model.sources.get(entry.source, set())
        if owners:
            mapped.extend(replace(entry, target=name) for name in sorted(owners))
        else:
            mapped.append(entry)
            missing.append(str(entry.source))
    return mapped, sorted(set(missing))
