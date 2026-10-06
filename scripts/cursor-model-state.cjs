'use strict';
// Scope model preferences to one Cursor process. Authentication and all other
// config fields continue to use Cursor's original shared config and keychain.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const KEYS = ['model', 'selectedModel', 'modelParameters', 'maxMode', 'maxModeAutoEnabled'];
function pick(config) {
  if (!config || typeof config.model?.modelId !== 'string') return null;
  return Object.fromEntries(KEYS.filter(key => key in config).map(key => [key, config[key]]));
}
function install({runDir, conversationId, configPath} = {}) {
  if (!runDir || !conversationId) return false;
  const target = path.resolve(configPath || path.join(process.env.CURSOR_CONFIG_DIR?.trim() ||
    (process.env.XDG_CONFIG_HOME?.trim() ? path.join(process.env.XDG_CONFIG_HOME, 'cursor') : path.join(os.homedir(), '.cursor')), 'cli-config.json'));
  const statePath = path.join(runDir, '.cursor-model.json');
  let fields = null;
  try {
    const saved = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    if (saved.conversation_id === conversationId) fields = pick(saved.fields);
  } catch {}
  const read = fs.promises.readFile, rename = fs.promises.rename;
  const matches = value => typeof value === 'string' && path.resolve(value) === target;
  function save(next) {
    fields = next;
    const temp = `${statePath}.${process.pid}.tmp`;
    try {
      fs.writeFileSync(temp, JSON.stringify({version: 1, conversation_id: conversationId, fields}), {mode: 0o600});
      fs.renameSync(temp, statePath);
    } catch { try { fs.unlinkSync(temp); } catch {} }
  }
  fs.promises.readFile = async function(file, ...args) {
    const data = await read.call(this, file, ...args);
    if (!matches(file)) return data;
    try {
      const config = JSON.parse(data.toString());
      if (!fields) return data; // Never mistake another process's startup default for a saved choice.
      for (const key of KEYS) delete config[key];
      const merged = JSON.stringify({...config, ...fields});
      return typeof data === 'string' ? merged : Buffer.from(merged);
    } catch { return data; }
  };
  fs.promises.rename = async function(from, to) {
    // Cursor commits config via writeFile(temp) + rename(temp, cli-config.json).
    // Read the exact bytes this process wrote, not the global file after a race.
    let next = null;
    if (matches(to)) {
      try { next = pick(JSON.parse(await read.call(fs.promises, from, 'utf8'))); } catch {}
    }
    const result = await rename.call(this, from, to);
    if (next) save(next);
    return result;
  };
  return true;
}
module.exports = {install, pick};
