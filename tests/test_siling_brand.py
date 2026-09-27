import os
from pathlib import Path
import subprocess
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]


class SiLingBrandContractTests(unittest.TestCase):
    def test_launcher_is_executable_and_exposes_siling_help(self):
        launcher = PROJECT_DIR / "siling"
        self.assertTrue(launcher.is_file())
        self.assertTrue(os.access(launcher, os.X_OK))

        result = subprocess.run(
            [str(launcher), "--help"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=20,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SiLing", result.stdout)

    def test_new_agent_sessions_receive_the_siling_command(self):
        run_script = (PROJECT_DIR / "scripts" / "run.sh").read_text()
        index = (PROJECT_DIR / "static" / "index.html").read_text()

        self.assertIn('export PATH="$REPO_DIR:$REPO_DIR/.venv/bin:$PATH"', run_script)
        self.assertIn("siling link-folder", index)
        self.assertNotIn("`orch link-folder", index)


if __name__ == "__main__":
    unittest.main()
