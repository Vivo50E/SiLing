"""Offline checks for the checked-in Spec Kit integration and living UI/UX spec."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

from agent_orchestrator import speckit_plugin


ROOT = Path(__file__).resolve().parents[1]
FEATURE = "specs/001-uiux-improvements"


class SpecKitRepositoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="siling-spec-kit-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "project with spaces"
        shutil.copytree(ROOT / ".specify", self.root / ".specify",
                        ignore=shutil.ignore_patterns("feature.json"))
        (self.root / FEATURE).mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("SPECIFY_")}

    def run_script(self, name, *args, feature=True):
        env = self.env.copy()
        if feature:
            env["SPECIFY_FEATURE_DIRECTORY"] = FEATURE
        return subprocess.run(
            ["bash", str(self.root / ".specify/scripts/bash" / name), *args],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=15,
        )

    def test_fresh_checkout_resolves_explicit_feature_without_writing_pointer(self):
        result = self.run_script("check-prerequisites.sh", "--json", "--paths-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        paths = json.loads(result.stdout)
        self.assertEqual(Path(paths["FEATURE_SPEC"]).resolve(),
                         (self.root / FEATURE / "spec.md").resolve())
        self.assertFalse((self.root / ".specify/feature.json").exists())

    def test_missing_feature_fails_instead_of_selecting_an_unrelated_directory(self):
        result = self.run_script("check-prerequisites.sh", "--json", "--paths-only",
                                 feature=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SPECIFY_FEATURE_DIRECTORY", result.stderr)
        self.assertFalse((self.root / ".specify/feature.json").exists())

    def test_paths_only_keeps_an_existing_local_pointer_unchanged(self):
        pointer = self.root / ".specify/feature.json"
        original = '{"feature_directory":"specs/999-another-feature"}\n'
        pointer.write_text(original)
        result = self.run_script("check-prerequisites.sh", "--json", "--paths-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(pointer.read_text(), original)
        self.assertTrue(json.loads(result.stdout)["FEATURE_DIR"].endswith(FEATURE))

    def test_bundled_templates_resolve_without_global_cli(self):
        for name in ("spec-template", "constitution-template"):
            with self.subTest(template=name):
                result = self.run_script("resolve-template.sh", name, "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["TEMPLATE_CONTENT"],
                                 (ROOT / ".specify/templates" / f"{name}.md").read_text())

    def test_dashboard_plugin_detects_the_bundled_codex_stages(self):
        result = speckit_plugin.prepare({"cwd": str(ROOT), "agent": "codex",
                                         "stage": "clarify", "request": "Review only"})
        for stage in ("constitution", "specify", "clarify", "plan", "tasks",
                      "analyze", "checklist", "implement"):
            self.assertEqual(result["project"]["stages"][stage],
                             f".agents/skills/speckit-{stage}/SKILL.md")

    def test_requirement_ids_are_unique_and_cross_references_resolve(self):
        text = (ROOT / FEATURE / "spec.md").read_text()
        for prefix in ("FR", "SC"):
            defined = re.findall(rf"^\- \*\*({prefix}-\d{{3}})\*\*:", text, re.M)
            self.assertTrue(defined)
            self.assertEqual(len(defined), len(set(defined)))
            referenced = set(re.findall(rf"\b{prefix}-\d{{3}}\b", text))
            self.assertEqual(referenced, set(defined))
        self.assertNotIn("[NEEDS CLARIFICATION", text)

    def test_authored_spec_document_links_exist(self):
        paths = list((ROOT / "specs").rglob("*.md")) + [
            ROOT / "docs/uiux-improvement-spec.md",
            ROOT / ".specify/memory/constitution.md",
        ]
        for path in paths:
            for target in re.findall(r"\[[^\]]+\]\(([^\s)]+)\)", path.read_text()):
                url = urlsplit(target)
                if url.scheme or not url.path:
                    continue
                with self.subTest(document=path.relative_to(ROOT), target=target):
                    resolved = (path.parent / unquote(url.path)).resolve()
                    self.assertTrue(resolved.is_relative_to(ROOT.resolve()))
                    self.assertTrue(resolved.exists(), str(resolved))

    def test_bundled_shell_scripts_are_parseable(self):
        for path in (ROOT / ".specify/scripts/bash").glob("*.sh"):
            result = subprocess.run(["bash", "-n", str(path)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
