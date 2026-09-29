"""Executable key routing checks, independent of live agent sessions."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class TerminalKeysTests(unittest.TestCase):
    def test_shift_enter_routes_without_submitting_or_hijacking_other_keys(self):
        script = r'''
          const assert = require('node:assert/strict');
          const handlers = {}, timers = [];
          const doc = {addEventListener:(key,fn)=>{handlers[key]=fn;}};
          let session = {agent:'codex',alive:true}, sent = [];
          let terminal = {input:(value,user)=>sent.push([value,user])};
          global.setTimeout = fn => timers.push(fn);
          keys.install(doc,()=>session,()=>terminal);
          function press(extra={}) {
            const event={key:'Enter',shiftKey:true,target:{classList:{contains:c=>c==='xterm-helper-textarea'}},
              preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true},...extra};
            handlers.keydown(event); return event;
          }
          for(const [agent,data] of [['codex','\x1b[200~\n\x1b[201~'],['claude','\n'],['cursor','\n'],['agent','\n']]) {
            session.agent=agent; sent=[];
            const e=press();assert.deepEqual(sent,[[data,true]],agent);
            assert.ok(e.prevented&&e.stopped);
          }
          for(const agent of ['terminal','custom-agent','']) {
            session.agent=agent;sent=[];assert.ok(!press().prevented);assert.deepEqual(sent,[]);
          }
          session.agent='codex';
          for(const extra of [{shiftKey:false},{ctrlKey:true},{altKey:true},{metaKey:true},
              {isComposing:true},{keyCode:229},{key:'a'},{target:{classList:{contains:()=>false}}}]) {
            sent=[];assert.ok(!press(extra).prevented);assert.deepEqual(sent,[]);
          }
          for(const flags of [{alive:false},{agent_exited:true}]) {
            session={agent:'codex',...flags};sent=[];assert.ok(!press().prevented);assert.deepEqual(sent,[]);
          }
          session={agent:'codex',alive:true};
          handlers.compositionstart();sent=[];assert.ok(!press().prevented);
          handlers.compositionend();assert.ok(!press().prevented);
          timers.splice(0).forEach(fn=>fn());assert.ok(press().prevented);
          sent=[];press({repeat:true});assert.equal(sent.length,1,'one newline per repeated key event');
          terminal={};assert.ok(!press().prevented,'older terminal without input API stays native');
          terminal=null;assert.ok(!press().prevented);
        '''
        result = subprocess.run(
            ["node"], input="const keys=require(" + json.dumps(str(ROOT / "static/terminal-keys.js")) + ");" + script,
            text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
