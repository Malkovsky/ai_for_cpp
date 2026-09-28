import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze_scope as scope


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.a = self.root / "include/a.h"
        self.b = self.root / "include/b.h"
        self.a.parent.mkdir()
        self.a.write_text("// a\n")
        self.b.write_text("// b\n")
        commands = []
        for target, source, header in [
            ("alpha_tests", "tests/alpha.cpp", self.a),
            ("alpha_benchmarks", "bench/alpha.cpp", self.a),
            ("beta_tests", "tests/beta.cpp", self.b),
        ]:
            src = self.root / source
            src.parent.mkdir(exist_ok=True)
            src.write_text("// fixture\n")
            obj = self.build / f"CMakeFiles/{target}.dir/{src.name}.o"
            obj.parent.mkdir(parents=True)
            Path(str(obj) + ".d").write_text(f"{obj}: {src} {header}\n{header}:\n")
            commands.append({"directory": str(self.build), "file": str(src),
                             "arguments": ["c++", "-o", str(obj), "-c", str(src)]})
        self.database = self.build / "compile_commands.json"
        self.database.write_text(json.dumps(commands))
        scope.modification_time.cache_clear()
        scope.dependency_path.cache_clear()

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        argv = ["scope", "--compile-commands", str(self.database), "--format", "json", *args]
        with patch.object(sys, "argv", argv), patch.object(scope, "git_repo_root", return_value=self.root), \
                patch.object(scope, "git_changed_files", side_effect=AssertionError("unexpected branch scan")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = scope.main()
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_explicit_file_uses_cache_without_compiler_or_ast(self):
        with patch.object(scope, "run_command", side_effect=AssertionError("unexpected process")), \
                patch.object(scope, "discover_clangxx", side_effect=AssertionError("unexpected AST")):
            code, report, _ = self.invoke("--changed-file", "include/a.h", "--baseline", "missing-ref")
        self.assertEqual(code, 0)
        self.assertEqual(report["affected_targets"], ["alpha_benchmarks", "alpha_tests"])
        self.assertEqual(report["affected_test_targets"], ["alpha_tests"])
        self.assertEqual(report["affected_benchmark_targets"], ["alpha_benchmarks"])
        self.assertEqual(report["dependency_cache_hits"], 3)
        self.assertEqual(report["compiler_dependency_scans"], 0)
        self.assertEqual(report["ast_entries_scanned"], 0)

    def test_stale_graph_is_refreshed_and_new_include_is_seen(self):
        entry = scope.load_compile_commands(self.database, self.root)[0]
        depfile = Path(str(entry.output) + ".d")
        stamp = depfile.stat().st_mtime_ns + 1_000_000
        os.utime(self.a, ns=(stamp, stamp))
        added = self.root / "include/new.h"
        added.write_text("// new\n")
        proc = subprocess.CompletedProcess([], 0, f"x: {entry.source} {self.a} {added}\n", "")
        with patch.object(scope, "run_command", return_value=proc) as run:
            scope.compute_tu_dependencies(entry, timeout=3)
        self.assertEqual(entry.dependency_origin, "preprocessor")
        self.assertIn(added, entry.dependencies)
        self.assertEqual(run.call_args.kwargs["timeout"], 3)

    def test_failed_scans_keep_uncertain_targets(self):
        proc = subprocess.CompletedProcess([], 1, "", "missing generated header")
        with patch.object(scope, "cached_tu_dependencies", return_value=False), \
                patch.object(scope, "run_command", return_value=proc):
            code, report, _ = self.invoke("--changed-file", "include/a.h")
        self.assertEqual(code, 0)
        self.assertIn("beta_tests", report["affected_targets"])
        self.assertEqual(len(report["dependency_scan_failures"]), 3)

    def test_source_change_needs_no_header_scan(self):
        code, report, _ = self.invoke("--changed-file", "tests/alpha.cpp")
        self.assertEqual(code, 0)
        self.assertEqual(report["affected_targets"], ["alpha_tests"])
        self.assertEqual(report["dependency_entries_scanned"], 0)

    def test_documentation_does_not_request_a_build(self):
        code, report, _ = self.invoke("--changed-file", "README.md")
        self.assertEqual(code, 0)
        self.assertIsNone(report["build_command"])

    def test_explicit_target_bounds_infrastructure_scope(self):
        code, report, _ = self.invoke("--changed-file", "CMakeLists.txt", "--target", "alpha_tests")
        self.assertEqual(code, 0)
        self.assertEqual(report["affected_targets"], ["alpha_tests"])
        self.assertEqual(report["analysis_limited_to_targets"], ["alpha_tests"])

    def test_unknown_target_fails(self):
        code, _, error = self.invoke("--changed-file", "include/a.h", "--target", "typo")
        self.assertEqual(code, 2)
        self.assertIn("Unknown targets", error)

    def inventory(self):
        path = self.root / "ctest.json"
        path.write_text(json.dumps({"tests": [
            {"name": "Alpha.Boundary", "properties": [{"name": "LABELS", "value": ["alpha_tests"]}]},
            {"name": "Alpha.Random", "command": ["/build/alpha_tests"]},
            {"name": "Beta.Boundary", "command": ["/build/beta_tests"]},
        ]}))
        return str(path)

    def test_ctest_filter_only_selects_verified_owner(self):
        code, report, _ = self.invoke("--changed-file", "include/a.h",
                                      "--ctest-json", self.inventory(), "--test-regex", "Boundary")
        self.assertEqual(code, 0)
        self.assertEqual(report["selected_tests"], ["Alpha.Boundary"])
        self.assertIn("-R", report["ctest_command"])

    def test_zero_test_selection_fails(self):
        code, _, error = self.invoke("--changed-file", "include/a.h",
                                     "--ctest-json", self.inventory(), "--test-regex", "NoSuchCase")
        self.assertEqual(code, 2)
        self.assertIn("zero tests", error)

    def test_untracked_working_tree_file_is_included(self):
        outputs = [subprocess.CompletedProcess([], 0, "", ""),
                   subprocess.CompletedProcess([], 0, "", ""),
                   subprocess.CompletedProcess([], 0, "include/new.h\0", "")]
        with patch.object(scope, "run_command", side_effect=outputs):
            self.assertEqual(scope.git_working_tree_changed_files(self.root),
                             {self.root / "include/new.h"})

    def test_depfile_escaped_space_and_phony_rule(self):
        self.assertEqual(scope.parse_makefile_dependencies("x.o: a\\ b.h \\\n c.h\na\\ b.h:\nc.h:\n"),
                         ["a b.h", "c.h"])

    def file_api(self, targets, config="Release"):
        reply = self.build / ".cmake/api/v1/reply"
        reply.mkdir(parents=True)
        refs = []
        for target in targets:
            filename = target["name"] + ".json"
            (reply / filename).write_text(json.dumps(target))
            refs.append({"jsonFile": filename})
        (reply / "model.json").write_text(json.dumps({
            "paths": {"source": str(self.root), "build": str(self.build)},
            "configurations": [{"name": config, "targets": refs}]}))
        (reply / "inputs.json").write_text(json.dumps({"inputs": []}))
        (reply / "index-1.json").write_text(json.dumps({"objects": [
            {"kind": "codemodel", "version": {"major": 2}, "jsonFile": "model.json"},
            {"kind": "cmakeFiles", "version": {"major": 1}, "jsonFile": "inputs.json"}]}))
        return reply

    def test_file_api_overrides_object_path_and_propagates_consumers(self):
        self.file_api([
            {"name": "core", "id": "core-id", "sources": [{"path": "tests/alpha.cpp"}]},
            {"name": "runner", "id": "runner-id", "dependencies": [{"id": "core-id"}],
             "artifacts": [{"path": "bin/custom-test-name"}]},
        ])
        inventory = self.root / "inventory.json"
        inventory.write_text(json.dumps({"tests": [{"name": "Core.Boundary",
            "command": [str(self.build / "bin/custom-test-name")]}]}))
        code, report, _ = self.invoke("--changed-file", "tests/alpha.cpp",
                                      "--ctest-json", str(inventory))
        self.assertEqual(code, 0)
        self.assertEqual(report["affected_targets"], ["core", "runner"])
        self.assertEqual(report["selected_tests"], ["Core.Boundary"])
        self.assertEqual(report["affected_test_targets"], ["core", "runner"])
        self.assertEqual(report["target_metadata"], "cmake_file_api_partial")

    def test_file_api_source_shared_by_targets_keeps_each_compile_command(self):
        self.file_api([
            {"name": name, "id": name, "sources": [{"path": "tests/alpha.cpp"}]}
            for name in ["first", "second"]])
        model = scope.load_model(self.build, "Release")
        entries = scope.load_compile_commands(self.database, self.root)[:1]
        from dataclasses import replace
        entries.append(replace(entries[0], arguments=["c++", "-DOTHER", "-c", str(entries[0].source)]))
        mapped, missing = scope.map_entries(entries, model)
        self.assertFalse(missing)
        self.assertEqual(len(scope.dedupe_entries_by_target_source(mapped)), 4)

    def test_file_api_missing_or_wrong_configuration_reports_fallback(self):
        self.file_api([], config="Debug")
        code, report, _ = self.invoke("--changed-file", "tests/alpha.cpp")
        self.assertEqual(code, 0)
        self.assertEqual(report["target_metadata"], "object_path_fallback")
        self.assertTrue(any("configuration" in w for w in report["warnings"]))

    def test_stale_file_api_reports_fallback(self):
        reply = self.file_api([])
        cmake = self.root / "CMakeLists.txt"
        cmake.write_text("# changed")
        (reply / "inputs.json").write_text(json.dumps({"inputs": [{"path": "CMakeLists.txt"}]}))
        stamp = (reply / "index-1.json").stat().st_mtime_ns + 1_000_000
        os.utime(cmake, ns=(stamp, stamp))
        code, report, _ = self.invoke("--changed-file", "tests/alpha.cpp")
        self.assertEqual(code, 0)
        self.assertEqual(report["target_metadata"], "object_path_fallback")
        self.assertTrue(any("configure input changed" in w for w in report["warnings"]))

    def test_file_api_transitive_consumers_and_cycles(self):
        from cmake_model import CMakeModel
        model = CMakeModel(dependents={"core": {"middle"}, "middle": {"runner", "core"}})
        self.assertEqual(model.consumers({"core"}), {"core", "middle", "runner"})

    def test_summary_omits_long_case_lists_and_commands(self):
        code, report, _ = self.invoke("--changed-file", "include/a.h",
                                      "--ctest-json", self.inventory(), "--format", "summary")
        self.assertEqual(code, 0)
        self.assertEqual(report["selected_test_count"], 2)
        self.assertNotIn("selected_tests", report)
        self.assertNotIn("ctest_command", report)
        self.assertEqual(report["target_metadata"], "object_path_fallback")

    def test_test_kind_scans_library_prerequisites_but_skips_benchmarks(self):
        source = self.root / "lib/core.cpp"
        source.parent.mkdir()
        source.write_text("// library fixture\n")
        commands = json.loads(self.database.read_text())
        commands[0]["file"] = str(source)
        commands[0]["arguments"][-1] = str(source)
        self.database.write_text(json.dumps(commands))
        obj = commands[0]["arguments"][2]
        Path(obj + ".d").write_text(f"{obj}: {source} {self.a}\n")
        self.file_api([
            {"name": "core", "id": "core", "sources": [{"path": "lib/core.cpp"}]},
            {"name": "beta_tests", "id": "beta", "sources": [{"path": "tests/beta.cpp"}],
             "dependencies": [{"id": "core"}]},
            {"name": "alpha_benchmarks", "id": "bench",
             "sources": [{"path": "bench/alpha.cpp"}]},
        ])
        code, report, _ = self.invoke("--changed-file", "include/a.h", "--kind", "tests")
        self.assertEqual(code, 0)
        self.assertEqual(report["target_metadata"], "cmake_file_api")
        self.assertEqual(report["dependency_entries_scanned"], 2)
        self.assertEqual(report["affected_targets"], ["beta_tests"])
        self.assertNotIn("alpha_benchmarks", report["selected_targets"])

    def test_large_ctest_selection_uses_verified_labels(self):
        inventory = {"tests": [{"name": f"LongTypedTest.Case{i}." + "x" * 100,
                                "properties": [{"name": "LABELS", "value": ["suite"]}]}
                               for i in range(100)]}
        args, method = scope.ctest_selection(inventory,
            [t["name"] for t in inventory["tests"]], {"suite"})
        self.assertEqual(method, "labels")
        self.assertEqual(args, ["-L", "^(suite)$"])

    def test_large_partial_selection_uses_exact_inventory_indices(self):
        inventory = {"tests": [{"name": f"LongTypedTest.Case{i}." + "x" * 100,
                                "properties": [{"name": "LABELS", "value": ["suite"]}]}
                               for i in range(100)]}
        args, method = scope.ctest_selection(inventory,
            [t["name"] for t in inventory["tests"][::2]], {"suite"})
        self.assertEqual(method, "indices")
        self.assertEqual(args, ["-I", "0,0,0," + ",".join(str(i) for i in range(1, 101, 2))])


if __name__ == "__main__":
    unittest.main()
