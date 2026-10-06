'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {install} = require('../scripts/cursor-model-state.cjs');
(async()=>{
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-model-'));
  const configPath = path.join(root, 'cli-config.json');
  const originalRead = fs.promises.readFile;
  const commit = async config => {
    const temp = configPath + '.fixture.tmp';
    await fs.promises.writeFile(temp, JSON.stringify(config));
    await fs.promises.rename(temp, configPath);
  };
  const model = modelId => ({modelId});
  try {
    fs.writeFileSync(configPath, JSON.stringify({model: model('opus'), authInfo: {fixture: 'do-not-copy'}}));
    assert.equal(install({runDir: root, conversationId: 'same-chat', configPath}), true);
    await commit({model: model('sonnet'), selectedModel: {modelId:'sonnet', parameters:[{id:'effort',value:'high'}]}, authInfo:{fixture:'do-not-copy'}});
    // No prompt was sent: a successful model menu write alone must persist.
    let saved = JSON.parse(fs.readFileSync(path.join(root,'.cursor-model.json'),'utf8'));
    assert.equal(saved.fields.model.modelId,'sonnet');
    assert.equal(saved.fields.selectedModel.parameters[0].value,'high');
    assert.ok(!JSON.stringify(saved).includes('do-not-copy'));
    // Another pane writes shared preferences; this process retains its own
    // model while seeing updated shared authentication/non-model settings.
    fs.writeFileSync(configPath, JSON.stringify({model:model('other-pane'),authInfo:{fixture:'new-auth'}}));
    let mine = JSON.parse(await fs.promises.readFile(configPath,'utf8'));
    assert.equal(mine.model.modelId,'sonnet');
    assert.equal(mine.authInfo.fixture,'new-auth');
    await commit({...mine,privacyMode:true});
    assert.equal(JSON.parse(fs.readFileSync(path.join(root,'.cursor-model.json'))).fields.model.modelId,'sonnet');
    // Failed config writes must not replace the last successfully selected model.
    await assert.rejects(fs.promises.rename(path.join(root,'missing'),configPath));
    assert.equal(JSON.parse(fs.readFileSync(path.join(root,'.cursor-model.json'))).fields.model.modelId,'sonnet');
    const authPath=path.join(root,'auth.json');
    fs.writeFileSync(authPath,'unchanged');
    assert.equal(await fs.promises.readFile(authPath,'utf8'),'unchanged');
    // Resume in a fresh process restores the saved fields, not shared defaults.
    const script = `const fs=require('fs');fs.promises.readFile(${JSON.stringify(configPath)},'utf8').then(s=>console.log(JSON.parse(s).model.modelId))`;
    const child=spawnSync(process.execPath,['-r',path.resolve('scripts/cursor-sync-output.cjs'),'-e',script,'--','--resume','same-chat'],{
      encoding:'utf8', env:{...process.env,SILING_CURSOR_SYNC_ONCE:'1',ORCH_AGENT_TYPE:'cursor',ORCH_RUN_DIR:root,CURSOR_CONFIG_DIR:root}
    });
    assert.equal(child.status,0,child.stderr);
    assert.equal(child.stdout.trim(),'sonnet');
    assert.equal(JSON.parse(await originalRead(configPath,'utf8')).authInfo.fixture,'new-auth');
  } finally {fs.rmSync(root,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
