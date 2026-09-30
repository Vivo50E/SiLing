"""Behavior checks for browser-local UI preferences and identity rendering."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class UIFoundationTests(unittest.TestCase):
    def run_js(self, source):
        result = subprocess.run(
            ["node"], input='const assert=require("node:assert/strict");'
             f'const ui=require({json.dumps(str(ROOT / "static/ui-foundation.js"))});'
             + source, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_message_catalog_preserves_parameters_and_system_language(self):
        self.run_js('''
          const root={dataset:{},style:{setProperty(){}}};
          global.document={documentElement:root,querySelectorAll:()=>[]};
          Object.defineProperty(global,'navigator',{value:{language:'zh-CN'},configurable:true});
          ui.apply({language:'system'});
          assert.equal(root.lang,'zh');
          assert.equal(ui.message('Working dir'),'工作目录');
          assert.equal(ui.message('New session · pane {pane}',{pane:'<User name>'}),'新建会话 · 面板 <User name>');
          assert.equal(ui.message('Unknown user content'),'Unknown user content');
          ui.apply({language:'en'});
          assert.equal(ui.message('Working dir'),'Working dir');
          navigator.language='fr-FR';ui.apply({language:'system'});
          assert.equal(root.lang,'en');
          const {zh}=require('./static/ui-messages.js');
          for(const [en,value] of Object.entries(zh)) {
            assert.ok(value.trim(),en);
            const params=s=>[...s.matchAll(/\\{(\\w+)\\}/g)].map(m=>m[1]).sort();
            assert.deepEqual(params(en),params(value),en+' retains all placeholders');
          }
        ''')

    def test_message_annotations_use_reviewed_keys(self):
        self.run_js('''
          const fs=require('node:fs'),{zh}=require('./static/ui-messages.js');
          const source=fs.readFileSync('./static/index.html','utf8');
          for(const match of source.matchAll(/data-ui-(?:message|title|label|placeholder)=(?:"([^"$]+)"|([^\\s>]+))/g)) {
            const value=match[1]||match[2];
            if(value.includes('${'))continue;
            assert.ok(Object.hasOwn(zh,decodeURIComponent(value)),value);
          }
        ''')

    def test_invalid_preferences_fall_back_per_field(self):
        self.run_js('''
          for (const raw of [null, [], "bad", 4]) assert.deepEqual(ui.normalize(raw), ui.defaults);
          assert.deepEqual(ui.normalize({theme:"light",density:"tiny",fontSize:"16",motion:"spin",language:"zh",secret:"x"}),
            {theme:"light",density:"comfortable",fontSize:16,motion:"system",language:"zh"});
          assert.equal(ui.normalize({fontSize:1000}).fontSize, 14);
        ''')

    def test_corrupt_or_unavailable_storage_uses_defaults(self):
        self.run_js('''
          for (const value of [null, "{broken", "null", "[]"]) {
            assert.deepEqual(ui.read({getItem:()=>value}), ui.defaults);
          }
          const blocked={getItem(){throw Error("blocked")},setItem(){throw Error("full")}};
          assert.deepEqual(ui.read(blocked),ui.defaults);
          assert.equal(ui.write(blocked,{theme:"light"}),false);
        ''')

    def test_preferences_round_trip_without_touching_session_keys(self):
        self.run_js('''
          const data=new Map([["orch_slots","keep-slots"],["siling_panel_opacity","80"]]);
          const storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};
          assert.equal(ui.write(storage,{theme:"light",fontSize:15}),true);
          assert.equal(ui.read(storage).theme,"light");
          assert.equal(ui.read(storage).fontSize,15);
          assert.equal(data.get("orch_slots"),"keep-slots");
          assert.equal(data.get("siling_panel_opacity"),"80");
          assert.equal(data.size,3);
        ''')

    def test_known_agents_and_unknown_names_have_safe_text_identity(self):
        self.run_js('''
          for (const [agent,label] of [[" CLAUDE ","Claude"],["CODEX","Codex"],["cursor","Cursor"],["terminal","Terminal"]]) {
            assert.equal(ui.agentIdentity(agent).label,label);
            assert.ok(ui.agentBadge(agent).includes(label));
          }
          const badge=ui.agentBadge('<img src=x onerror="bad">');
          assert.ok(badge.includes("agent-unknown"));
          assert.ok(badge.includes("&lt;img"));
          assert.ok(!badge.includes("<img"));
          assert.equal(ui.agentIdentity(null).label,"Agent");
          for (const name of ["__proto__", "constructor", "toString"]) {
            assert.deepEqual(ui.agentIdentity(name), {kind:"unknown",label:name});
          }
          const marks = ["claude", "codex", "cursor", "terminal", "custom"].map(name => {
            const html=ui.agentBadge(name);
            assert.ok(html.includes('class="agent-name"'));
            assert.ok(html.includes('aria-hidden="true"'));
            return html.match(/<path d="([^"]+)"/)[1];
          });
          assert.equal(new Set(marks).size,5);
        ''')

    def test_icons_and_button_labels_are_safe_and_have_consistent_geometry(self):
        self.run_js('''
          for(const name of ["__proto__","constructor","<img>",null]) {
            assert.equal(ui.icon(name),ui.icon("more"));
          }
          for(const name of ["bell","bellOff","bellBlocked","folder","refresh","close"]) {
            assert.ok(ui.icon(name).includes('viewBox="0 0 24 24"'));
            assert.ok(ui.icon(name).includes('focusable="false"'));
          }
          assert.ok(ui.buttonContent("folder",'<img src=x>').includes("&lt;img src=x&gt;"));
          assert.ok(!ui.buttonContent("folder",'<img src=x>').includes("<img"));
        ''')

    def test_notification_rendering_preserves_distinct_toggle_and_permission_states(self):
        self.run_js('''
          const attrs={};const button={setAttribute:(k,v)=>attrs[k]=v};
          for(const [enabled,permission,icon] of [[false,"default","bellOff"],[true,"granted","bell"],[true,"denied","bellBlocked"],[false,"denied","bellOff"]]) {
            ui.notificationButton(button,enabled,permission);
            assert.equal(button.innerHTML,ui.icon(icon));
            assert.equal(attrs["aria-pressed"],String(enabled));
            assert.equal(attrs["aria-label"].includes("blocked"),enabled&&permission==="denied");
          }
        ''')

    def test_creating_in_a_changed_layout_never_overwrites_an_existing_pane(self):
        self.run_js('''
          assert.equal(ui.createdSessionSlot(["a",null],1,"cols-2","cols-2","new"),1);
          assert.equal(ui.createdSessionSlot(["a","b",null],1,"cols-3","cols-3","new"),2);
          assert.equal(ui.createdSessionSlot(["a"],2,"cols-3","1","new"),-1);
          assert.equal(ui.createdSessionSlot([null,"a",null],2,"cols-2x2","cols-3","new"),0);
          assert.equal(ui.createdSessionSlot(["a","new",null],2,"cols-3","cols-3","new"),1);
        ''')

    def test_login_link_masks_credentials_without_changing_copy_target(self):
        source = (ROOT / "static/index.html").read_text()
        helper = re.search(r"  function maskedDashboardUrl\(value\) \{[\s\S]*?\n  \}", source).group(0)
        self.run_js(helper + '''
          const original="https://alice:password@example.test/?token=secret&other=private#sensitive";
          const masked=maskedDashboardUrl(original);
          for(const secret of ["alice","password","secret","private","sensitive"]) assert.ok(!masked.includes(secret));
          assert.ok(original.includes("token=secret"));
          assert.equal(maskedDashboardUrl("invalid"),"Dashboard login link");
        ''')

    def test_javascript_syntax_and_unique_static_ids(self):
        source = (ROOT / "static/index.html").read_text()
        script = source[source.rindex("<script>") + 8:source.rindex("</script>")]
        self.run_js("new Function(" + json.dumps(script) + ");")
        groups = (ROOT / "static/pane-groups.js").read_text()
        self.run_js("new Function(" + json.dumps(groups) + ");")
        markup = source[:source.rindex("<script>")]
        ids = re.findall(r'\bid="([^"]+)"', markup)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
