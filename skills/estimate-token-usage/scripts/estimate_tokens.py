#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["tiktoken>=0.7,<1"]
# ///
"""Estimate token usage for skills, MCP definitions, and general context."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


Count = Callable[[str], int]


@dataclass(frozen=True)
class SkillUsage:
    name: str
    metadata: int
    body: int
    optional: int


@dataclass(frozen=True)
class McpUsage:
    name: str
    description: int
    schema: int
    definition: int


@dataclass(frozen=True)
class ContextUsage:
    source: str
    characters: int
    tokens: int


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--method",
        choices=("auto", "tiktoken", "heuristic"),
        default="auto",
        help="token counting method (default: auto)",
    )
    parser.add_argument(
        "--encoding",
        default="o200k_base",
        help="tiktoken encoding (default: o200k_base)",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="output format (default: table)",
    )


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    default_skills = script.parents[2]
    parser = argparse.ArgumentParser(
        description="Estimate context tokens for skills, MCP tools, or text."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    skills = subparsers.add_parser("skills", help="measure agent skills")
    skills.add_argument(
        "--skills-root",
        type=Path,
        default=default_skills,
        help=f"skills directory (default: {default_skills})",
    )
    skills.add_argument(
        "--skill",
        action="append",
        default=[],
        help="skill name to include; repeat to select multiple skills",
    )
    add_common_arguments(skills)

    mcp = subparsers.add_parser("mcp", help="measure MCP tool definitions")
    mcp.add_argument(
        "sources",
        nargs="+",
        help="JSON file containing tool definitions, or - for standard input",
    )
    add_common_arguments(mcp)

    context = subparsers.add_parser("context", help="measure general context")
    context.add_argument(
        "sources",
        nargs="*",
        help="UTF-8 file or directory, or - for standard input",
    )
    context.add_argument(
        "--text",
        action="append",
        default=[],
        help="literal context text; repeat to add multiple values",
    )
    context.add_argument(
        "--include",
        action="append",
        default=[],
        help="glob included from directory inputs; repeat for alternatives",
    )
    context.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="glob excluded from directory inputs; repeat for alternatives",
    )
    add_common_arguments(context)
    return parser.parse_args()


def heuristic_count(text: str) -> int:
    if not text:
        return 0
    by_chars = math.ceil(len(text) / 4)
    by_words = math.ceil(len(text.split()) * 1.3)
    return max(by_chars, by_words)


def make_counter(method: str, encoding: str) -> tuple[Count, str]:
    if method in ("auto", "tiktoken"):
        try:
            import tiktoken  # type: ignore[import-not-found]

            tokenizer = tiktoken.get_encoding(encoding)
            return lambda text: len(tokenizer.encode(text)), f"tiktoken:{encoding}"
        except (ImportError, ValueError) as error:
            if method == "tiktoken":
                raise RuntimeError(
                    f"cannot use tiktoken encoding {encoding!r}: {error}; "
                    "install tiktoken or choose --method heuristic"
                ) from error
    return heuristic_count, "heuristic:max(chars/4,words*1.3)"


def split_frontmatter(text: str, path: Path) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: missing YAML frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[: index + 1]), "".join(lines[index + 1 :])
    raise ValueError(f"{path}: unterminated YAML frontmatter")


def frontmatter_identity(frontmatter: str, path: Path) -> tuple[str, str]:
    values: dict[str, str] = {}
    for line in frontmatter.splitlines()[1:-1]:
        key, separator, raw_value = line.partition(":")
        if separator and key in ("name", "description"):
            value = raw_value.strip()
            if value[:1] in ('"', "'"):
                try:
                    value = ast.literal_eval(value)
                except (SyntaxError, ValueError):
                    value = value[1:-1]
            values[key] = value
    missing = [key for key in ("name", "description") if not values.get(key)]
    if missing:
        raise ValueError(f"{path}: missing frontmatter field(s): {', '.join(missing)}")
    return values["name"], values["description"]


def optional_context(skill_dir: Path) -> list[Path]:
    context_suffixes = {".json", ".md", ".rst", ".toml", ".txt", ".yaml", ".yml"}
    return sorted(
        path
        for path in skill_dir.rglob("*")
        if path.is_file()
        and path.name != "SKILL.md"
        and path.suffix.lower() in context_suffixes
        and not {".git", "agents", "assets", "scripts"}.intersection(
            path.relative_to(skill_dir).parts
        )
    )


def discover_skills(root: Path, selected: list[str]) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f"skills root does not exist: {root}")
    available = {
        path.name: path
        for path in root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    if selected:
        missing = sorted(set(selected) - available.keys())
        if missing:
            raise ValueError(f"unknown skill(s): {', '.join(missing)}")
        return [available[name] for name in sorted(set(selected))]
    return [available[name] for name in sorted(available)]


def measure_skills(args: argparse.Namespace, count: Count) -> list[SkillUsage]:
    usages = []
    for skill_dir in discover_skills(args.skills_root.resolve(), args.skill):
        skill_file = skill_dir / "SKILL.md"
        metadata_text, body_text = split_frontmatter(
            skill_file.read_text(encoding="utf-8"), skill_file
        )
        name, description = frontmatter_identity(metadata_text, skill_file)
        optional = sum(
            count(path.read_text(encoding="utf-8"))
            for path in optional_context(skill_dir)
        )
        metadata = count(name) + count(description)
        body = count(body_text)
        usages.append(
            SkillUsage(
                name=skill_dir.name,
                metadata=metadata,
                body=body,
                optional=optional,
            )
        )
    return usages


def read_json_source(source: str, stdin_cache: list[str]) -> Any:
    if source == "-":
        if not stdin_cache:
            stdin_cache.append(sys.stdin.read())
        text = stdin_cache[0]
    else:
        text = Path(source).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{source}: invalid JSON: {error}") from error


def find_tool_lists(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            return value
        return []
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("tools"), list):
        return [item for item in value["tools"] if isinstance(item, dict)]
    if "name" in value or value.get("type") == "function":
        return [value]
    for nested in value.values():
        found = find_tool_lists(nested)
        if found:
            return found
    return []


def normalize_tool(tool: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
        tool = tool["function"]
    name = tool.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("MCP tool is missing a non-empty name")
    description = tool.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"MCP tool {name!r} has a non-string description")
    schema = tool.get(
        "inputSchema", tool.get("input_schema", tool.get("parameters", {}))
    )
    if not isinstance(schema, dict):
        raise ValueError(f"MCP tool {name!r} has a non-object input schema")
    return name, description, schema


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def measure_mcp(args: argparse.Namespace, count: Count) -> list[McpUsage]:
    usages = []
    stdin_cache: list[str] = []
    for source in args.sources:
        tools = find_tool_lists(read_json_source(source, stdin_cache))
        if not tools:
            raise ValueError(f"{source}: no MCP tool definitions found")
        for raw_tool in tools:
            name, description, schema = normalize_tool(raw_tool)
            definition = {
                "name": name,
                "description": description,
                "inputSchema": schema,
            }
            usages.append(
                McpUsage(
                    name=name,
                    description=count(description),
                    schema=count(compact_json(schema)),
                    definition=count(compact_json(definition)),
                )
            )
    return usages


def matches_patterns(path: Path, root: Path, args: argparse.Namespace) -> bool:
    relative = path.relative_to(root).as_posix()
    included = not args.include or any(
        fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern)
        for pattern in args.include
    )
    excluded = any(
        fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern)
        for pattern in args.exclude
    )
    return included and not excluded


def context_files(source: str, args: argparse.Namespace) -> Iterable[Path]:
    path = Path(source)
    if path.is_file():
        yield path
    elif path.is_dir():
        yield from (
            candidate
            for candidate in sorted(path.rglob("*"))
            if candidate.is_file() and matches_patterns(candidate, path, args)
        )
    else:
        raise ValueError(f"context source does not exist: {source}")


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path}: not a UTF-8 text file") from error


def measure_context(args: argparse.Namespace, count: Count) -> list[ContextUsage]:
    if not args.sources and not args.text:
        raise ValueError("context requires a source or --text")
    usages = []
    stdin_text: str | None = None
    for source in args.sources:
        if source == "-":
            if stdin_text is None:
                stdin_text = sys.stdin.read()
            usages.append(ContextUsage("<stdin>", len(stdin_text), count(stdin_text)))
            continue
        for path in context_files(source, args):
            text = read_utf8(path)
            usages.append(ContextUsage(str(path), len(text), count(text)))
    for index, text in enumerate(args.text, start=1):
        usages.append(ContextUsage(f"<text:{index}>", len(text), count(text)))
    return usages


def print_records(
    records: list[Any], label_field: str, numeric_fields: tuple[str, ...], method: str
) -> None:
    headers = (label_field, *numeric_fields)
    rows = [tuple(str(getattr(record, field)) for field in headers) for record in records]
    totals = (
        "TOTAL",
        *(str(sum(getattr(record, field) for record in records)) for field in numeric_fields),
    )
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows), len(totals[index]))
        for index in range(len(headers))
    ]
    print(f"method: {method}")
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print(
            "  ".join(
                value.ljust(widths[index]) if index == 0 else value.rjust(widths[index])
                for index, value in enumerate(row)
            )
        )
    print(
        "  ".join(
            value.ljust(widths[index]) if index == 0 else value.rjust(widths[index])
            for index, value in enumerate(totals)
        )
    )


def main() -> int:
    args = parse_args()
    try:
        count, method = make_counter(args.method, args.encoding)
        if args.mode == "skills":
            records = measure_skills(args, count)
            label = "name"
            fields = ("metadata", "body", "optional")
        elif args.mode == "mcp":
            records = measure_mcp(args, count)
            label, fields = "name", ("description", "schema", "definition")
        else:
            records = measure_context(args, count)
            label, fields = "source", ("characters", "tokens")
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "method": method,
                    "records": [asdict(record) for record in records],
                },
                indent=2,
            )
        )
    else:
        print_records(records, label, fields, method)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
