"""CLI lookup and real launch coverage without installed/model-backed agents."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agent_orchestrator import agent_cli


PROJECT = Path(__file__).resolve().parents[1]


class AgentCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="siling-cli-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "user space"
        self.local = self.home / ".local" / "bin"
        self.local.mkdir(parents=True)
        self.patch = patch.object(agent_cli.Path, "home", return_value=self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def executable(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\nprintf "CLI_FIXTURE"\nprintf " <%s>" "$@"\nprintf "\\n"\ncommand -v python3\n')
        path.chmod(0o700)
        return path

    def test_user_local_fallback_when_service_path_is_minimal(self):
        cli = self.executable(self.local / "claude")
        self.assertEqual(agent_cli.resolve_agent_cli("claude", path="/usr/bin:/bin"), str(cli))

    def test_existing_path_wins_over_fallback(self):
        self.executable(self.local / "claude")
        cli = self.executable(self.root / "custom bin" / "claude")
        self.assertEqual(agent_cli.resolve_agent_cli("claude", path=str(cli.parent)), str(cli))

    def test_supported_aliases(self):
        for kind, name in (("claude", "claude"), ("codex", "codex"), ("cursor", "agent"), ("agent", "agent")):
            with self.subTest(kind=kind):
                cli = self.executable(self.local / name)
                self.assertEqual(agent_cli.resolve_agent_cli(kind, path="/usr/bin:/bin"), str(cli))

    def test_missing_or_non_executable_cli_is_rejected(self):
        for kind in ("claude", "codex", "cursor"):
            with self.subTest(kind=kind), self.assertRaises(FileNotFoundError):
                agent_cli.resolve_agent_cli(kind, path="/usr/bin:/bin")
        (self.local / "claude").write_text("not executable")
        with self.assertRaises(FileNotFoundError):
            agent_cli.resolve_agent_cli("claude", path="/usr/bin:/bin")

    def test_symlink_path_is_preserved_for_cli_updates(self):
        target = self.executable(self.root / "version-one")
        cli = self.local / "claude"
        cli.symlink_to(target)
        self.assertEqual(agent_cli.resolve_agent_cli("claude", path="/usr/bin:/bin"), str(cli))
        target.unlink()
        with self.assertRaises(FileNotFoundError):
            agent_cli.resolve_agent_cli("claude", path="/usr/bin:/bin")

    @unittest.skipUnless(shutil.which("tmux"), "tmux required")
    def test_run_script_launches_absolute_cli_with_resume_args_in_isolated_tmux(self):
        real_tmux = shutil.which("tmux")
        socket = self.root / "tmux.sock"
        scripts = self.root / "repo" / "scripts"
        scripts.mkdir(parents=True)
        package = scripts.parent / "agent_orchestrator"
        package.mkdir()
        shutil.copy(PROJECT / "scripts" / "run.sh", scripts / "run.sh")
        shutil.copy(PROJECT / "scripts" / "cursor-sync-output.cjs", scripts / "cursor-sync-output.cjs")
        shutil.copy(PROJECT / "agent_orchestrator" / "agent_cli.py", package / "agent_cli.py")
        (scripts / "watcher.sh").write_text("#!/bin/sh\nexit 0\n")
        tools = self.root / "tools"
        tools.mkdir()
        wrapper = tools / "tmux"
        wrapper.write_text(f"#!/bin/sh\nexec /usr/bin/env PATH=/usr/bin:/bin {shlex.quote(real_tmux)} -S {shlex.quote(str(socket))} \"$@\"\n")
        wrapper.chmod(0o700)
        (tools / "python3").symlink_to(sys.executable)
        cli_dir = self.root / "cli bin"
        for name in ("claude", "codex", "agent"):
            self.executable(cli_dir / name)
        if shutil.which("node"):
            cli = cli_dir / "agent"
            code = "console.log('CURSOR_PRELOAD_CLEAN='+(!process.env.SILING_CURSOR_SYNC_ONCE && !process.env.NODE_OPTIONS))"
            cli.write_text(cli.read_text().replace('#!/bin/sh\n', '#!/bin/sh\n' + shlex.join([shutil.which('node'), '-e', code]) + '\n'))
        env = dict(os.environ, PATH=f"{tools}:{cli_dir}:/usr/bin:/bin", ORCH_OUTPUTS_DIR=str(self.root / "outputs"))
        env.pop("NODE_OPTIONS", None)
        # Create the owned server with a PATH that cannot find our CLI fixture.
        subprocess.run([real_tmux, "-S", str(socket), "-f", "/dev/null", "new-session", "-d", "-s", "keeper", "sleep 60"],
                       env=dict(os.environ, PATH="/usr/bin:/bin"), check=True, capture_output=True, timeout=5)
        try:
            for agent, resume in ((a, r) for a in ("claude", "codex", "cursor") for r in (False, True)):
                with self.subTest(agent=agent, resume=resume):
                    args = ["/bin/bash", str(scripts / "run.sh"), "--no-attach"]
                    if resume:
                        args += ["--resume-id", "saved-id"]
                    args += [agent, f"{agent}-{resume}", str(self.root)]
                    result = subprocess.run(args,
                                            env=env, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    session = next(line.split(":", 1)[1].strip() for line in result.stdout.splitlines() if line.startswith("Session:"))
                    for _ in range(50):
                        pane = subprocess.check_output([real_tmux, "-S", str(socket), "capture-pane", "-p", "-J", "-t", session], text=True, timeout=5)
                        if "--- Agent exited ---" in pane:
                            break
                        time.sleep(0.02)
                    self.assertIn("CLI_FIXTURE", pane)
                    if agent == "cursor" and shutil.which("node"):
                        self.assertIn("CURSOR_PRELOAD_CLEAN=true", pane)
                    if resume:
                        self.assertIn("<saved-id>", pane)
                        self.assertIn("<resume>" if agent == "codex" else "<--resume>", pane)
                    else:
                        self.assertNotIn("<saved-id>", pane)
                    if agent == "cursor":
                        if resume:
                            self.assertNotIn("<--model>", pane)
                        else:
                            self.assertIn("<claude-opus-4-7-high>", pane)
                    self.assertIn(str(tools / "python3"), pane)
        finally:
            subprocess.run([real_tmux, "-S", str(socket), "kill-server"], capture_output=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
