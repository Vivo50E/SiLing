"""Behavior checks for terminal selection and Codex launch commands."""

import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import unittest

from agent_orchestrator import dashboard, task_runner, terminal_theme
from agent_orchestrator.config import TaskConfig


class PaneInteractionTests(unittest.TestCase):
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
    def test_shell_and_codex_selection_preserves_other_agent_mouse(self):
        script = terminal_theme._TTYD_INTERACTION_SCRIPT.split(">", 1)[1].rsplit("</script>", 1)[0]
        source = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text()
        policy = re.search(r"  function sessionPrefersNativeSelection\(s\) \{.*?\n  \}", source, re.S).group(0)
        harness = r"""
const assert = require('node:assert/strict');
eval(POLICY);
for (const agent of ['terminal', 'codex', ' Codex ']) {
  assert.equal(sessionPrefersNativeSelection({agent}), true);
}
for (const agent of ['claude', 'cursor', '', undefined]) {
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
  term: { _core: { coreMouseService: mouse, _selectionService: selection } },
  frameElement: { dataset: { nativeSelection: String(sessionPrefersNativeSelection({agent: 'codex'})) } },
  addEventListener: () => {},
};
global.document = {
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
