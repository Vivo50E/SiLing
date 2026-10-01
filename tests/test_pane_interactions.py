"""Behavior checks for terminal selection and Codex launch commands."""

import json
import os
import asyncio
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from agent_orchestrator import dashboard, task_runner, terminal_theme
from agent_orchestrator.config import TaskConfig


class PaneInteractionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("tmux"), "tmux required")
    def test_single_line_selection_trims_highlight_and_preserves_multiline(self):
        with tempfile.TemporaryDirectory(prefix="siling-trim-", dir="/tmp") as temp:
            socket = str(Path(temp) / "tmux.sock")
            def tmux(*args):
                return subprocess.check_output(["tmux", "-S", socket, *args], text=True, timeout=5).strip()
            def key(*args):
                tmux("send-keys", "-t", "check", "-X", *args)
            try:
                tmux("-f", "/dev/null", "new-session", "-d", "-s", "check", "-x", "80", "-y", "20",
                     "printf '   hello world\\n    second line\\n'; exec cat")
                for _ in range(100):
                    if "hello world" in tmux("capture-pane", "-p", "-t", "check"):
                        break
                    time.sleep(.01)
                with patch.dict(os.environ, {"TMUX": socket + ",0,0"}):
                    for reverse in (False, True):
                        tmux("copy-mode", "-t", "check")
                        key("history-top"); key("start-of-line")
                        if reverse:
                            key("-N", "8", "cursor-right")
                        key("begin-selection")
                        key("-N", "8", "cursor-left" if reverse else "cursor-right")
                        self.assertTrue(dashboard._tmux_trim_selection("check"))
                        self.assertEqual(dashboard._tmux_copy_selection("check"), "hello")
                        self.assertEqual(tmux("display-message", "-p", "-t", "check",
                                              "#{selection_start_x} #{selection_end_x}"), "8 3" if reverse else "3 8")
                        key("cancel")
                    tmux("copy-mode", "-t", "check")
                    key("history-top"); key("start-of-line"); key("begin-selection")
                    key("cursor-down"); key("-N", "10", "cursor-right")
                    before = dashboard._tmux_copy_selection("check")
                    self.assertFalse(dashboard._tmux_trim_selection("check"))
                    self.assertEqual(dashboard._tmux_copy_selection("check"), before)
                    key("cancel")
                    tmux("copy-mode", "-t", "check")
                    key("history-top"); key("start-of-line"); key("begin-selection")
                    key("cursor-right")
                    self.assertFalse(dashboard._tmux_trim_selection("check"))
            finally:
                subprocess.run(["tmux", "-S", socket, "kill-server"], capture_output=True, timeout=5)

    @unittest.skipUnless(shutil.which("tmux"), "tmux required")
    def test_wheel_history_exits_only_when_scrolled_back_to_latest(self):
        # An isolated socket keeps the user's tmux server and bindings intact.
        with tempfile.TemporaryDirectory(prefix="siling-scroll-", dir="/tmp") as temp:
            base = ["tmux", "-S", str(Path(temp) / "tmux.sock")]
            def tmux(*args):
                return subprocess.run(base + list(args), capture_output=True,
                                      text=True, check=True, timeout=5).stdout.strip()
            try:
                tmux("-f", "/dev/null", "new-session", "-d", "-s", "check",
                     "-x", "80", "-y", "20",
                     "i=0; while [ $i -lt 80 ]; do echo line-$i; i=$((i+1)); done; exec cat")
                for _ in range(100):
                    if int(tmux("display-message", "-p", "-t", "check", "#{history_size}")) > 0:
                        break
                    time.sleep(0.01)
                self.assertGreater(int(tmux("display-message", "-p", "-t", "check", "#{history_size}")), 0)
                tmux("copy-mode", "-e", "-t", "check", ";",
                     "send-keys", "-t", "check", "-X", "-N", "5", "scroll-up")
                self.assertEqual(tmux("display-message", "-p", "-t", "check", "#{pane_in_mode}"), "1")
                tmux("send-keys", "-t", "check", "-X", "-N", "2", "scroll-down")
                self.assertEqual(tmux("display-message", "-p", "-t", "check", "#{pane_in_mode}"), "1")
                tmux("send-keys", "-t", "check", "-X", "-N", "3", "scroll-down")
                self.assertEqual(tmux("display-message", "-p", "-t", "check", "#{pane_in_mode}"), "0")
            finally:
                subprocess.run(base + ["kill-server"], capture_output=True, timeout=5)

    @unittest.skipUnless(shutil.which("tmux"), "tmux required")
    def test_copy_selection_reads_offscreen_lines_without_changing_buffers(self):
        with tempfile.TemporaryDirectory(prefix="siling-copy-", dir="/tmp") as temp:
            socket = str(Path(temp) / "tmux.sock")
            def tmux(*args):
                return subprocess.check_output(["tmux", "-S", socket, *args],
                                               text=True, timeout=5)
            try:
                tmux("-f", "/dev/null", "new-session", "-d", "-s", "check",
                     "-x", "80", "-y", "20",
                     "i=0; while [ $i -lt 80 ]; do echo copy-line-$i; i=$((i+1)); done; exec cat")
                for _ in range(100):
                    if "copy-line-79" in tmux("capture-pane", "-p", "-t", "check", "-S", "-"):
                        break
                    time.sleep(0.01)
                tmux("set-buffer", "-b", "personal", "keep me")
                tmux("copy-mode", "-t", "check")
                for command in ("history-top", "start-of-line", "begin-selection"):
                    tmux("send-keys", "-t", "check", "-X", command)
                tmux("send-keys", "-t", "check", "-X", "-N", "39", "cursor-down")
                tmux("send-keys", "-t", "check", "-X", "end-of-line")
                with patch.dict(os.environ, {"TMUX": f"{socket},0,0"}):
                    copied = dashboard._tmux_copy_selection("check")
                self.assertEqual(copied.splitlines(), [f"copy-line-{i}" for i in range(40)])
                self.assertEqual(tmux("show-buffer", "-b", "personal"), "keep me")
                self.assertEqual(tmux("list-buffers", "-F", "#{buffer_name}").splitlines(), ["personal"])
                self.assertEqual(tmux("display-message", "-p", "-t", "check", "#{selection_present}").strip(), "1")
                tmux("send-keys", "-t", "check", "-X", "cancel")
                with patch.dict(os.environ, {"TMUX": f"{socket},0,0"}):
                    with self.assertRaisesRegex(RuntimeError, "No terminal text"):
                        dashboard._tmux_copy_selection("check")
            finally:
                subprocess.run(["tmux", "-S", socket, "kill-server"],
                               capture_output=True, timeout=5)

    def test_selection_api_resolves_the_requested_session(self):
        with patch.object(dashboard.TtydManager, "_sweep_orphans", return_value=0):
            app = dashboard.create_app(Path("/nonexistent/siling-copy-test"),
                                       ttyd_enabled=False, remote_nodes_enabled=False)
        with TestClient(app) as client, patch.object(dashboard, "_lookup_run_light") as lookup, \
                patch.object(dashboard, "_tmux_copy_selection", return_value="selected\ntext") as copy:
            lookup.return_value = {"tmux_session": "private-test"}
            response = client.post("/api/sessions/example/selection")
            self.assertEqual(response.json(), {"text": "selected\ntext"})
            copy.assert_called_once_with("private-test")
            with patch.object(dashboard, "_tmux_trim_selection", return_value=True) as trim:
                self.assertEqual(client.post("/api/sessions/example/selection/trim").json(), {"adjusted": True})
                trim.assert_called_once_with("private-test")
                lookup.return_value = None
                self.assertEqual(client.post("/api/sessions/missing/selection/trim").status_code, 404)
                trim.assert_called_once()
            lookup.return_value = None
            self.assertEqual(client.post("/api/sessions/missing/selection").status_code, 404)
            lookup.return_value = {"tmux_session": "private-test"}
            copy.side_effect = RuntimeError("No terminal text is selected")
            self.assertEqual(client.post("/api/sessions/example/selection").status_code, 409)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_wrapped_links_highlight_and_open_the_complete_target(self):
        script = terminal_theme._TTYD_INTERACTION_SCRIPT.split(">", 1)[1].rsplit("</script>", 1)[0]
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("terminal_links.cjs"))],
            input=script, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tty_route_enables_live_input_for_codex_and_shell(self):
        with patch.object(dashboard.TtydManager, "_sweep_orphans", return_value=0):
            app = dashboard.create_app(Path("/nonexistent/siling-input-test"),
                                       ttyd_enabled=True, remote_nodes_enabled=False)
        upstream_context = AsyncMock()
        forward = AsyncMock(side_effect=RuntimeError("probe complete"))
        with TestClient(app) as client, \
                patch.object(dashboard.TtydManager, "available", return_value=True), \
                patch.object(dashboard.TtydManager, "ensure", return_value=12345), \
                patch.object(dashboard.TtydManager, "port_for", return_value=12345), \
                patch.object(dashboard, "tmux_alive", return_value=True), \
                patch.object(dashboard, "_lookup_run_light") as lookup, \
                patch.object(dashboard.websockets, "connect", return_value=upstream_context), \
                patch.object(dashboard, "_forward_tty_input", forward):
            for agent, expected in (("codex", True), ("terminal", True), ("cursor", True), ("claude", False)):
                lookup.return_value = {"agent": agent, "tmux_session": "test-session"}
                tty_response = client.get("/api/sessions/test/tty").json()
                self.assertTrue(tty_response["ok"])
                self.assertTrue(tty_response["selection_copy"])
                with client.websocket_connect("/tty/test-session/ws") as socket:
                    socket.send_bytes(b"0hello")
                    self.assertEqual(socket.receive()["type"], "websocket.close")
                self.assertEqual(forward.await_args.kwargs["resume_live"], expected)

    def test_live_input_distinguishes_typing_from_mouse_and_protocol_frames(self):
        for message in (b"0hello", "0你好", b"0\r", b"0\x03", b"0\x7f",
                        b"0\x1b[200~pasted\ntext\x1b[201~"):
            with self.subTest(message=message):
                self.assertTrue(dashboard._ttyd_input_resumes_live(message))
        for message in (b"", b"0", b'1{"columns":80}', b'{"AuthToken":""}',
                        b"0\x1b[<64;10;5M", b"0\x1b[M !!", b"0\x1b[1;2R",
                        b"0\x1b[?1;2c", b"0\x1b[I", b"0\x1b[A", b"0\x1b"):
            with self.subTest(message=message):
                self.assertFalse(dashboard._ttyd_input_resumes_live(message))

    def test_live_input_cancels_history_before_forwarding_original_bytes(self):
        order = []
        payload = b"0first-character"
        def resolve(session):
            self.assertEqual(session, "test-session")
            order.append("cancel")
            return "%123", ""
        async def send(message):
            self.assertIs(message, payload)
            order.append("send")
        upstream = AsyncMock()
        upstream.send.side_effect = send
        with patch.object(dashboard, "_tmux_target_pane", side_effect=resolve):
            asyncio.run(dashboard._forward_tty_input(
                upstream, "test-session", payload, resume_live=True))
        self.assertEqual(order, ["cancel", "send"])

    def test_other_agents_and_scrolling_do_not_probe_or_cancel_tmux_mode(self):
        upstream = AsyncMock()
        with patch.object(dashboard, "_tmux_target_pane") as resolve:
            for enabled, payload in ((False, b"0hello"), (True, b"0\x1b[<64;1;1M")):
                asyncio.run(dashboard._forward_tty_input(
                    upstream, "test-session", payload, resume_live=enabled))
            resolve.assert_not_called()
        self.assertEqual(upstream.send.await_count, 2)

    def test_failed_mode_exit_does_not_send_input_to_history_commands(self):
        upstream = AsyncMock()
        with patch.object(dashboard, "_tmux_target_pane", return_value=("", "failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                asyncio.run(dashboard._forward_tty_input(
                    upstream, "test-session", b"0text", resume_live=True))
        upstream.send.assert_not_awaited()

    def test_reconnecting_codex_sessions_restore_live_input_policy(self):
        entries = [None, {}, {"agent": "codex"},
                   {"agent": "codex", "tmux_session": "codex-test"},
                   {"agent": "claude", "tmux_session": "claude-test"},
                   {"agent": "cursor", "tmux_session": "cursor-test"},
                   {"agent": "terminal", "tmux_session": "shell-test"}]
        with patch.object(dashboard, "_safe_read_json", return_value={"sessions": entries}):
            self.assertEqual(dashboard._live_input_sessions_from_snapshot(Path("/unused")), {"codex-test", "shell-test", "cursor-test"})

    def test_narrow_header_keeps_priority_in_accessible_action_row(self):
        source = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text()
        def rule(selector):
            return re.search(re.escape(selector) + r"\s*\{([^}]+)\}", source).group(1)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", rule(".pane-card.narrow .pane-head"))
        actions = rule(".pane-card.narrow .pane-actions")
        self.assertIn("overflow-x: auto", actions)
        self.assertIn("justify-content: flex-start", actions)
        self.assertIn("order: -1", rule(".pane-card.narrow .pane-state-select"))
        self.assertIn('ifr.dataset.nativeSelection = sessionPrefersNativeSelection(s) ? "true" : "false"', source)

    def test_codex_launch_and_resume_preserve_scrollback(self):
        task = TaskConfig(name="scroll", initial_prompt="test", agent="codex",
                          model="example-model", effort="high")
        command = shlex.split(task_runner._build_agent_command(task))
        self.assertIn("--no-alt-screen", command)
        self.assertEqual(command[command.index("-m") + 1], "example-model")
        for module in (dashboard, task_runner):
            command = shlex.split(module._resume_cmd_for("codex", "id with spaces"))
            self.assertIn("--no-alt-screen", command)
            self.assertEqual(command[-1], "id with spaces")
            self.assertNotIn("--no-alt-screen", module._resume_cmd_for("claude", "id"))

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_shell_codex_cursor_selection_preserves_other_agent_mouse(self):
        script = terminal_theme._TTYD_INTERACTION_SCRIPT.split(">", 1)[1].rsplit("</script>", 1)[0]
        source = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text()
        policy = re.search(r"  function sessionPrefersNativeSelection\(s\) \{.*?\n  \}", source, re.S).group(0)
        harness = r"""
const assert = require('node:assert/strict');
eval(POLICY);
for (const agent of ['terminal', 'codex', ' Codex ', 'cursor', ' Cursor ']) {
  assert.equal(sessionPrefersNativeSelection({agent}), true);
}
for (const agent of ['claude', '', undefined]) {
  assert.equal(sessionPrefersNativeSelection({agent}), false);
}
assert.equal(sessionPrefersNativeSelection(null), false);
const screenEvents = {}, documentEvents = {}, timers = [];
let reported = 0;
const selection = {
  shouldForceSelection: e => !!e.altKey || !!e.shiftKey,
  _getMouseBufferCoords: () => null,
};
const mouse = { triggerMouseEvent: () => { reported++; return true; } };
global.window = {
  term: { options: {}, onRender() {}, _core: { coreMouseService: mouse, _selectionService: selection } },
  frameElement: { dataset: { nativeSelection: String(sessionPrefersNativeSelection({agent: 'codex'})) } },
  addEventListener: () => {},
};
global.document = {
  head: { appendChild() {} },
  documentElement: { style: { setProperty() {} } },
  createElement: () => ({}),
  querySelector: () => ({
    addEventListener: (name, fn) => { screenEvents[name] = fn; },
    getBoundingClientRect: () => ({width: 0, height: 0}),
  }),
  addEventListener: (name, fn) => { documentEvents[name] = fn; },
};
global.setTimeout = fn => timers.push(fn);
eval(SOURCE);
const down = {button: 0, clientX: 0, clientY: 0};
assert.equal(selection.shouldForceSelection(down), true);
screenEvents.mousedown(down);
mouse.triggerMouseEvent({});
documentEvents.mouseup(down);
mouse.triggerMouseEvent({});
assert.equal(reported, 0, 'release must not erase browser selection');
timers.splice(0).forEach(fn => fn());
mouse.triggerMouseEvent({});
assert.equal(reported, 1, 'wheel/mouse reporting resumes after selection');
assert.equal(selection.shouldForceSelection({...down, ctrlKey: true}), false);
window.frameElement.dataset.nativeSelection = 'false';
assert.equal(selection.shouldForceSelection(down), false);
assert.equal(selection.shouldForceSelection({...down, altKey: true}), true);
screenEvents.mousedown(down);
mouse.triggerMouseEvent({});
assert.equal(reported, 2, 'agent mouse protocol remains unchanged');
"""
        result = subprocess.run(
            ["node", "-e", "const POLICY = " + json.dumps(policy) + ";\nconst SOURCE = " + json.dumps(script) + ";\n" + harness],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
