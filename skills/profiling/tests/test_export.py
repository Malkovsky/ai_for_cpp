"""Offline regression checks; run with python3 -m unittest discover -s <tests>."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_html import build_model, parse_samples, resolve_sources, validate
from source_analysis import attach_sources, function_extent


def sample(frames, period=10, event="cycles:u", pid=7):
    # Frames supplied leaf first, as emitted by perf script.
    return f"work {pid} 1.000000001: {period} {event}:\n" + "\n".join(
        f"    {ip:x} {name} ({dso})" for name, ip, dso in frames
    )


def model_for(text):
    samples = parse_samples(text)
    model, _ = build_model(samples, {"warnings": []})
    attach_sources(model, samples, Path("unused"), Path.cwd(), collect=False)
    validate(model)
    return samples, model


class ExportTests(unittest.TestCase):
    def test_periods_not_counts_and_unknown_leaves(self):
        _, model = model_for(
            sample([("leaf+0x4", 0x104, "/work"), ("main+0x8", 0x208, "/work")], 70)
            + "\n\n"
            + sample([], 30)
        )
        self.assertEqual(model["root"]["weight"], 100)
        self.assertEqual(model["root"]["samples"], 2)
        self.assertEqual(model["functions"]["leaf"]["self_weight"], 70)
        self.assertEqual(model["functions"]["[unresolved sample]"]["self_weight"], 30)
        self.assertEqual(model["functions"]["main"]["unresolved_call_weight"], 70)

    def test_recursive_machine_frames_and_cost_conservation(self):
        frames = [
            ("leaf", 0x140, "/work"),
            ("recurse", 0x120, "/work"),
            ("recurse", 0x120, "/work"),
            ("main", 0x100, "/work"),
        ]
        samples, model = model_for(sample(frames, 70) + "\n\n" + sample(frames[1:], 30))
        self.assertEqual(
            [f["name"] for f in samples[0]["frames"]],
            ["main", "recurse", "recurse", "leaf"],
        )
        self.assertEqual(model["functions"]["recurse"]["total_weight"], 100)
        self.assertEqual(model["functions"]["recurse"]["self_weight"], 30)
        self.assertEqual(
            sum(c["weight"] for c in model["functions"]["recurse"]["calls"]), 70
        )

    def test_inline_wrapper_and_duplicate_normalization(self):
        frames = [
            ("outer", 0x123, "/work"),
            ("inner", 0x123, "inlined"),
            ("inner", 0x123, "inlined"),
            ("outer", 0x123, "/work"),
        ]
        parsed = parse_samples(sample(frames))
        self.assertEqual([f["name"] for f in parsed[0]["frames"]], ["outer", "inner"])

    def test_event_and_root_filters_change_denominator(self):
        text = (
            sample([("leaf", 0x120, "/work"), ("main", 0x100, "/work")], 30)
            + "\n\n"
            + sample([], 70)
            + "\n\n"
            + sample([], 5, "instructions:u")
        )
        with self.assertRaisesRegex(ValueError, "Multiple events"):
            parse_samples(text)
        chosen = parse_samples(text, "cycles:u", "main")
        self.assertEqual(sum(s["weight"] for s in chosen), 30)
        with self.assertRaisesRegex(ValueError, "No positive"):
            parse_samples(text, "missing")
        with self.assertRaisesRegex(ValueError, "positive"):
            parse_samples(sample([], 0))

    def test_malformed_input_is_not_silently_dropped(self):
        for text in ["not a sample", sample([]) + "\ninvalid frame"]:
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                parse_samples(text)

    def test_per_process_load_bias_and_foreign_dso(self):
        text = (
            sample(
                [("leaf+0x4", 0x1104, "/old/work"), ("main+0x8", 0x1208, "/old/work")],
                pid=7,
            )
            + "\n\n"
            + sample([("leaf+0x4", 0x9104, "/old/work")], pid=8)
            + "\n\n"
            + sample([("leaf+0x4", 0xA104, "/lib/foreign.so")])
        )
        samples = parse_samples(text)
        with patch(
            "export_html.subprocess.check_output",
            return_value="100 T leaf\n200 T main\n",
        ):
            resolve_sources(samples, Path("work"), "/old/work", [], collect=False)
        self.assertEqual(samples[0]["frames"][0]["address"], 0x208)
        self.assertEqual(samples[0]["frames"][1]["address"], 0x104)
        self.assertEqual(samples[1]["frames"][0]["address"], 0x104)
        self.assertIsNone(samples[2]["frames"][0]["address"])
        self.assertEqual(samples[2]["frames"][0]["name"], "leaf [foreign.so]")

    def test_full_extent_ignores_comments_and_string_braces(self):
        code = (
            "template<class T>\nint\nfunction(T x) {\n"
            '  const char* s = R"tag( } ")tag"; // }\n'
            "  /* { */ if (x) { return 1; }\n  return 0;\n}\n"
        )
        self.assertEqual(function_extent(code, 3), (1, 7))
        self.assertIsNone(function_extent("int function();\n", 1))

    def test_foreign_inline_symbols_do_not_inherit_binary_sources(self):
        samples = parse_samples(
            sample(
                [
                    ("child+0x4", 0xA104, "inlined"),
                    ("parent+0x4", 0xA104, "/lib/foreign.so"),
                ]
            )
        )
        with patch(
            "export_html.subprocess.check_output", return_value="100 T parent\n"
        ):
            resolve_sources(samples, Path("work"), "/work", [], collect=False)
        self.assertEqual(samples[0]["frames"][1]["name"], "child [foreign.so]")
        self.assertIsNone(samples[0]["frames"][1]["address"])

    def test_source_mapping_and_inline_call_badge(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code = "int parent() {\n  return child();\n}\n\nint child() { return 1; }\n"
            (root / "source.cc").write_text(code)
            parent = dict(
                tag="DW_TAG_subprogram",
                name="parent",
                decl_file="/old/source.cc",
                decl_line=1,
                attrs={},
                offset=1,
            )
            child = dict(
                tag="DW_TAG_subprogram",
                name="child",
                decl_file="/old/source.cc",
                decl_line=5,
                attrs={},
                offset=2,
            )
            inline = dict(
                tag="DW_TAG_inlined_subroutine",
                name="child",
                call_line=2,
                call_file="/old/source.cc",
                function_parent=parent,
                ranges=[(0x100, 0x110)],
            )
            frames = parse_samples(
                sample([("child", 0x104, "inlined"), ("parent", 0x104, "/work")])
            )
            frames[0]["frames"][1]["address"] = 0x104
            model, _ = build_model(frames, {"warnings": []})
            with (
                patch("source_analysis.shutil.which", return_value="llvm-dwarfdump"),
                patch(
                    "source_analysis.parse_dwarf",
                    return_value={1: parent, 2: child, 3: inline},
                ),
            ):
                attach_sources(model, frames, Path("work"), root, [("/old", str(root))])
                validate(model)
                self.assertEqual(model["functions"]["parent"]["calls"][0]["line"], 2)
                self.assertEqual(model["functions"]["parent"]["definition"]["end"], 3)
                self.assertEqual(
                    model["source_files"]["/old/source.cc"]["lines"]["2"],
                    "  return child();",
                )
                unresolved = copy.deepcopy(frames)
                unresolved[0]["frames"][1]["address"] = None
                missing, _ = build_model(unresolved, {"warnings": []})
                attach_sources(
                    missing, unresolved, Path("work"), root, [("/old", str(root))]
                )
                self.assertIsNone(missing["functions"]["parent"]["calls"][0]["line"])


if __name__ == "__main__":
    unittest.main()
