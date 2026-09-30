"""Repository layout and validation contracts, also run by the update verifier."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import check


ROOT = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
    def test_real_workspace_and_production_import_boundaries(self):
        workspace = check.load_workspace(ROOT)
        check.check_import_boundaries(ROOT, workspace)
        self.assertIn("backend", workspace["components"])
        self.assertIn("dashboard", workspace["components"])

    def test_map_works_outside_repository_and_returns_json(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools/check.py"), "--map"],
                cwd=directory, capture_output=True, text=True, timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["name"], "SiLing")

    def test_invalid_workspace_is_rejected(self):
        data = json.loads((ROOT / "workspace.json").read_text(encoding="utf-8"))
        variants = []
        item = copy.deepcopy(data)
        item["schema_version"] = 999
        variants.append(item)
        for field, value in [("root", "missing-component"), ("root", "../outside"),
                             ("guide", "missing-guide.md"), ("tests", ["tests/missing_test.py"]),
                             ("forbidden_imports", "tools")]:
            item = copy.deepcopy(data)
            item["components"]["backend"][field] = value
            variants.append(item)
        item = copy.deepcopy(data)
        item["components"]["duplicate"] = copy.deepcopy(item["components"]["backend"])
        variants.append(item)
        for item in variants:
            with self.subTest(item=item), patch.object(check.json, "loads", return_value=item):
                with self.assertRaises(ValueError):
                    check.load_workspace(ROOT)

    @unittest.skipUnless(shutil.which("make"), "make required")
    def test_make_map_is_machine_readable_and_does_not_run_the_app(self):
        result = subprocess.run(
            ["make", "--no-print-directory", "map", f"PYTHON={sys.executable}"],
            cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["schema_version"], 1)

    def test_relative_paths_cannot_escape_or_follow_external_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            (root / "external").symlink_to(Path(directory), target_is_directory=True)
            for value in ("../secret", "/secret", ".", "external/secret", "..\\secret"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    check.local_path(root, value)

    def test_empty_patterns_fail_and_overlaps_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("pass\n", encoding="utf-8")
            self.assertEqual(check.matching_files(root, ["*.py", "a.py"]), [root / "a.py"])
            with self.assertRaises(ValueError):
                check.matching_files(root, ["*.sh"])

    def test_static_runtime_imports_cannot_depend_on_development_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            source = root / "backend/example.py"
            workspace = {"components": {"backend": {"root": "backend", "forbidden_imports": ["tools", "tests"]}}}
            for text in ("import tools.check", "from tools import check", "import os, tests.fixture"):
                source.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(ValueError):
                    check.check_import_boundaries(root, workspace)
            source.write_text("from . import tools\nimport json", encoding="utf-8")
            check.check_import_boundaries(root, workspace)

    def minimal_source_tree(self, root):
        for name, content in {"app.py": "pass\n", "one.sh": "echo ok\n", "two.sh": "echo ok\n",
                              "app.js": "const ok = true;\n", "data.json": "{}",
                              "index.html": "<script>const ok = true;</script>"}.items():
            (root / name).write_text(content, encoding="utf-8")
        return {"components": {}, "checks": {"python": ["*.py"], "shell": ["*.sh"],
                "javascript": ["*.js"], "json": ["*.json"], "inline_script": "index.html"}}

    def test_checker_invokes_each_shell_file_and_does_not_import_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.minimal_source_tree(root)
            (root / "app.py").write_text("raise RuntimeError('must not import')\n", encoding="utf-8")
            with patch.object(check, "run") as run:
                check.check_sources(root, workspace)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([c for c in commands if c[0] == "bash"], [
                ["bash", "-n", str(root / "one.sh")], ["bash", "-n", str(root / "two.sh")]])
            self.assertFalse((root / "__pycache__").exists())

    @unittest.skipUnless(shutil.which("bash"), "bash required")
    def test_syntax_error_in_second_shell_file_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.minimal_source_tree(root)
            (root / "two.sh").write_text("if then\n", encoding="utf-8")
            with self.assertRaises(subprocess.CalledProcessError) as error:
                check.check_sources(root, workspace)
            self.assertEqual(error.exception.cmd[-1], str(root / "two.sh"))

    def test_main_reports_failed_checks_with_nonzero_exit(self):
        with patch.object(check, "load_workspace", side_effect=ValueError("broken layout")):
            self.assertEqual(check.main(["--structure"]), 1)


if __name__ == "__main__":
    unittest.main()
