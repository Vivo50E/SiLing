"""Keep the separate English/Chinese README pages and their switch navigable."""

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


PROJECT_DIR = Path(__file__).resolve().parents[1]
READMES = ("README.md", "README_CN.md", "README_EN.md")


class ReadmeTests(unittest.TestCase):
    def test_independent_project_preserves_origin_and_copyright(self):
        for filename, status in (
            ("README.md", "independent project"),
            ("README_CN.md", "独立项目"),
        ):
            with self.subTest(filename=filename):
                text = (PROJECT_DIR / filename).read_text(encoding="utf-8")
                self.assertIn(status, text)
                self.assertIn(
                    "https://github.com/YAMY1234/agent-orchestrator-public", text
                )
                self.assertIn("[MIT License](LICENSE)", text)
        license_text = (PROJECT_DIR / "LICENSE").read_text(encoding="utf-8")
        for author in ("Agent Orchestrator contributors", "SiLing contributors"):
            self.assertIn(f"Copyright (c) 2026 {author}", license_text)
        self.assertIn("MIT License", license_text)
        self.assertIn("The above copyright notice and this permission notice", license_text)

    def test_readmes_use_separate_language_pages_and_preserve_the_brand(self):
        homepage = (PROJECT_DIR / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("## 中文\n", homepage)
        self.assertNotIn("](#中文)", homepage)
        self.assertNotIn("](#english)", homepage)
        for filename, switch in (("README.md", "[中文](README_CN.md)"),
                                 ("README_CN.md", "[English](README.md)")):
            with self.subTest(filename=filename):
                text = (PROJECT_DIR / filename).read_text(encoding="utf-8")
                title = re.search(r"^# (.+)$", text, re.MULTILINE).group(1)
                self.assertIn("司令", title)
                self.assertIn("SiLing", title)
                self.assertIn(
                    "https://github.com/YAMY1234/agent-orchestrator-public", text
                )
                self.assertIn(switch, text.split("</div>", 1)[0])
        legacy = (PROJECT_DIR / "README_EN.md").read_text(encoding="utf-8")
        self.assertIn("](README.md)", legacy)
        self.assertNotIn("## Quick start", legacy)

    def test_relative_links_and_images_exist(self):
        for filename in READMES:
            text = (PROJECT_DIR / filename).read_text(encoding="utf-8")
            targets = re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text)
            targets += re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', text)
            for target in targets:
                url = urlsplit(target)
                if url.scheme or url.netloc:
                    continue
                with self.subTest(filename=filename, target=target):
                    path = PROJECT_DIR / unquote(url.path or filename)
                    self.assertTrue(path.is_file(), f"Missing local link: {target}")
                    if url.fragment:
                        # The landing-page language links use simple headings.
                        headings = re.findall(
                            r"^#{1,6} (.+)$", path.read_text(encoding="utf-8"),
                            re.MULTILINE,
                        )
                        self.assertIn(
                            unquote(url.fragment),
                            [heading.lower().replace(" ", "-") for heading in headings],
                        )

    def test_bilingual_quick_start_commands_match(self):
        commands = []
        for filename, heading in (("README.md", "## Quick start"),
                                  ("README_CN.md", "## 快速开始")):
            text = (PROJECT_DIR / filename).read_text(encoding="utf-8")
            section = text.split(heading, 1)[1]
            block = re.search(r"```bash\n(.*?)```", section, re.DOTALL).group(1)
            # The Python-version comment is localized; executable lines match.
            commands.append([line.split("  #", 1)[0].rstrip()
                             for line in block.splitlines() if line.strip()])
        self.assertTrue(commands[0])
        self.assertEqual(commands[0], commands[1])


if __name__ == "__main__":
    unittest.main()
