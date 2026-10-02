"""Dependency-free desktop security policy checks, included in full discovery."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class DesktopTests(unittest.TestCase):
    def test_desktop_packaging_and_connection_policy(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "--test", str(root / "tests/desktop_package.cjs")],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_desktop_updates(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "--test", str(root / "tests/desktop_updates.cjs")],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_desktop_policy(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "--test", str(root / "tests/desktop_policy.cjs")],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
