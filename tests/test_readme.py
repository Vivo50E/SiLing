"""Keep the bilingual landing page and its detailed guides navigable."""

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


PROJECT_DIR = Path(__file__).resolve().parents[1]
READMES = ("README.md", "README_CN.md", "README_EN.md")


class ReadmeTests(unittest.TestCase):
    def test_homepage_has_both_languages_and_guides_share_the_brand(self):
        homepage = (PROJECT_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("## 中文\n", homepage)
        self.assertIn("## English\n", homepage)
        for filename in READMES:
            with self.subTest(filename=filename):
                text = (PROJECT_DIR / filename).read_text(encoding="utf-8")
                title = re.search(r"^# (.+)$", text, re.MULTILINE).group(1)
                self.assertIn("司令", title)
                self.assertIn("SiLing", title)
                self.assertIn(
                    "https://github.com/YAMY1234/agent-orchestrator-public", text
                )
                for other in set(READMES) - {filename}:
                    self.assertIn(f"]({other})", text)

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
        text = (PROJECT_DIR / "README.md").read_text(encoding="utf-8")
        chinese, english = text.split("## English\n", 1)
        commands = [re.findall(r"```bash\n(.*?)```", part, re.DOTALL)
                    for part in (chinese, english)]
        self.assertEqual(len(commands[0]), 1)
        self.assertEqual(commands[0], commands[1])


if __name__ == "__main__":
    unittest.main()
