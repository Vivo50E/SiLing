/* File context belongs to terminal output, independently of the program in it. */
(() => {
  const tr = (en, zh) => document.documentElement.lang.startsWith('zh') ? zh : en;
  const states = new Map();
  const likelyPath = /(?:\/|\.\.?\/|\b)[^\s<>"'`]*\.[A-Za-z0-9]{1,12}\b/u;
  window.SilingTerminalFiles = {
    create({api, openViewer}) {
      const endpoint = (id, suffix) => `/api/sessions/${encodeURIComponent(id)}/${suffix}`;
      const getState = id => {
        if (!states.has(id)) states.set(id, {id, records: [], pending: false});
        return states.get(id);
      };
      const refresh = async state => {
        let data = await api(endpoint(state.id, 'file-context'));
        let legacy = '';
        try { legacy = localStorage.getItem('siling_ssh_host:' + state.id) || ''; } catch (_) {}
        if (!data.configured && legacy) {
          data = await api(endpoint(state.id,'file-context'),{method:'PUT',body:{mode:data.current.host===legacy?'auto':'ssh',host:legacy,cwd:'',auto_discover:true}});
        }
        state.data = data;
        return data;
      };
      const rowContext = (state, row) => {
        const term = state.frame?.contentWindow?.term;
        const text = term?.buffer.active.getLine(row)?.translateToString(true);
        const matches=state.records.filter(rec => !rec.marker.isDisposed && (rec.virtual || rec.marker.line === row) && rec.text === text);
        const ids=new Set(matches.map(rec=>rec.context));
        if(ids.size!==1 || matches.some(rec=>rec.uncertain || (rec.cleared && state.data?.current.id!==rec.context)))return '';
        return matches[0].context;
      };
      const scan = async state => {
        if (state.pending || !state.frame?.isConnected) return;
        const term = state.frame.contentWindow?.term;
        if (!term) return;
        state.pending = true;
        try {
          const {current, settings} = await refresh(state);
          if (!state.frame?.isConnected) return;
          state.records = state.records.filter(r => !r.marker.isDisposed);
          const buffer = term.buffer.active;
          const alternate = buffer.type === 'alternate';
          const lines = [];
          const initial = !state.initialized || state.data.observing === false;
          // Only observe live output. Scrolling back must not relabel old text
          // with today's host/cwd. Existing marker ownership stays immutable.
          const start = !alternate && state.lastLine && !state.lastLine.isDisposed ? Math.max(0, buffer.baseY - 200, state.lastLine.line) : buffer.baseY;
          for (let y = start; y < Math.min(buffer.length, buffer.baseY + term.rows); y++) {
            const text = buffer.getLine(y)?.translateToString(true) || '';
            if (!text.trim()) continue;
            const previous=state.records.find(rec=>!rec.marker.isDisposed && (rec.virtual || rec.marker.line===y) && rec.text===text);
            if(previous) {
              if(previous.cleared && previous.context!==current.id) previous.uncertain=true;
              previous.cleared=false;
              continue;
            }
            for(const rec of state.records) { if(!rec.virtual && rec.marker.line===y) rec.marker.dispose(); }
            const marker = alternate ? {line:y,isDisposed:false,dispose(){this.isDisposed=true;}} : term.registerMarker(y - buffer.baseY - buffer.cursorY);
            if (!marker) continue;
            state.records.push({marker, text, context: current.id, uncertain:initial, virtual:alternate});
            if (!initial) lines.push(text);
          }
          state.initialized=true;
          state.lastLine?.dispose();
          state.lastLine = alternate ? null : term.registerMarker(0);
          while (state.records.length > 1024) state.records.shift().marker.dispose();
          const text = lines.join('\n').slice(0, 16000);
          if (settings.auto_discover !== false && likelyPath.test(text) && !current.unresolved) {
            await api(endpoint(state.id, 'discover-files'), {method:'POST', body:{text, context_id:current.id, automatic:true}});
          }
          state.error = '';
        } catch (error) { state.error = error.message; }
        finally { state.pending = false; }
      };
      const attach = (frame, id) => {
        if (frame.dataset.fileContext !== 'true') return;
        frame.addEventListener('load', () => {
          const state = getState(id);
          if (state.stop) state.stop();
          state.frame = frame;
          for (const record of state.records) record.marker.dispose();
          state.records = [];
          state.initialized=false;
          state.lastLine?.dispose();state.lastLine=null;
          frame.contentWindow.silingFileContextForRow = row => rowContext(state, row);
          let writeListener;
          const clearListeners=[];
          let disposed = false;
          const timer = setInterval(() => {
            if (!frame.isConnected || disposed) { state.stop(); return; }
            const term = frame.contentWindow?.term;
            if (term && !writeListener) {
              writeListener=term.onWriteParsed(()=>{});
              for (const final of ['J','K']) {
                const listener=term.parser?.registerCsiHandler({final},params=>{
                  const b=term.buffer.active; const cursor=b.baseY+b.cursorY;
                  for(const rec of state.records) {
                    const y=rec.marker.line;
                    if(final==='K'?y===cursor:y>=b.baseY && (Number(params[0]||0)===2 || y>=cursor)) rec.cleared=true;
                  }
                  return false;
                });
                if(listener)clearListeners.push(listener);
              }
            }
            void scan(state);
          }, 4000);
          state.stop = () => { disposed = true; clearInterval(timer); writeListener?.dispose();clearListeners.forEach(item=>item.dispose()); };
          void scan(state);
        });
      };
      const openPath = async (id, path, contextId) => {
        if (!contextId) {
          await configure(id, path);
          return;
        }
        try {
          const result = await api(endpoint(id, 'terminal-file'), {method:'POST', body:{path, context_id:contextId}});
          await openViewer(id, result.folder.path);
        } catch(error) {
          if (/base directory|context expired/.test(error.message)) await configure(id,path);
          else throw error;
        }
      };
      const configure = async (id, providedText) => {
        const state = getState(id);
        const data = await refresh(state);
        const dialog = document.createElement('dialog');
        dialog.className = 'ui-dialog';
        dialog.style.cssText = 'width:min(640px,94vw);max-height:90vh;overflow:auto';
        dialog.innerHTML = `
          <div class="modal-head"><h2>${tr('Terminal files','终端文件')}</h2><button class="ui-button" data-close aria-label="Close">×</button></div>
          <div class="modal-body" style="display:grid;gap:12px">
            <details data-settings><summary>${tr("Connection and base directory","连接与工作目录")}</summary><div style="display:grid;gap:10px;margin-top:10px">
            <label>${tr('Connection','连接')} <select data-mode><option value="auto">${tr('Detect shell / SSH','自动识别 shell / SSH')}</option><option value="local">${tr('Local','本机')}</option><option value="ssh">SSH</option></select></label>
            <label>${tr('SSH alias (manual SSH mode)','SSH 别名（手动 SSH 模式）')} <input data-host placeholder="dev-server"></label>
            <label>${tr('Base directory (required for relative remote paths)','工作目录（远程相对路径需要填写）')} <input data-cwd placeholder="/home/user/project" style="width:100%"></label>
            <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" data-auto style="width:auto;margin:0"> ${tr('Discover files in new output automatically','自动发现新输出中的文件')}</label>
            <button class="ui-button" data-save>${tr('Save file context','保存文件上下文')}</button>
            <p class="ui-secondary" data-current></p></div></details>
            <label>${tr('Resolve selected text using','使用以下上下文解析选中文字')} <select data-context style="max-width:100%"></select></label>
            <textarea data-text rows="4" style="width:100%" placeholder="${tr('Select terminal text or paste it here','选中终端文字，或粘贴到这里')}"></textarea>
            <p class="ui-secondary">${tr('Intelligent identification sends only this text to your local Claude CLI’s configured model. It cannot run tools.','智能识别仅将这里的文字发送给本机 Claude CLI 配置的模型，不允许执行工具。')}</p>
            <div><button class="ui-button" data-scan>${tr('Find files','识别路径')}</button> <button class="ui-button" data-model>${tr('Identify with Claude','用 Claude 智能识别')}</button></div>
            <p role="status" data-status style="margin:0;white-space:pre-wrap"></p><div data-results style="display:grid;gap:8px"></div>
          </div>`;
        document.body.appendChild(dialog);
        const el = name => dialog.querySelector(`[data-${name}]`);
        const setContexts = value => {
          el('context').replaceChildren();
          for (const ctx of value.contexts) {
            const option = document.createElement('option');
            option.value = ctx.id;
            option.textContent = `${ctx.host || tr('Local','本机')} · ${ctx.cwd || tr('base directory unknown','工作目录未设置')}`;
            option.selected = ctx.id === value.current.id;
            el('context').append(option);
          }
          el('current').textContent = `${tr('Detected context','当前上下文')}: ${value.current.host || tr('Local','本机')} · ${value.current.cwd || '?'}${value.current.unresolved ? ' — '+tr('Set a manual SSH alias','请设置手动 SSH 别名') : ''}`;
        };
        setContexts(data);
        if (state.error) el('status').textContent=state.error;
        el('mode').value = data.settings.mode || 'auto';
        el('host').value = data.settings.host || data.current.host || '';
        el('cwd').value = data.current.cwd || '';
        el('auto').checked = data.settings.auto_discover !== false;
        el('settings').open = !!data.current.unresolved || (!!data.current.host && !data.current.cwd);
        const updateFields=()=> {el('host').disabled=el('mode').value!=='ssh';el('cwd').readOnly=el('mode').value==='auto'&&!data.current.host;};
        el('mode').onchange=updateFields;updateFields();
        el('text').value = providedText || state.frame?.contentWindow?.term?.getSelection() || '';
        const position = state.frame?.contentWindow?.term?.getSelectionPosition?.();
        if (position) {
          const ids = new Set();
          for(let y=position.start.y;y<=position.end.y;y++) { const ctx=rowContext(state,y); if(ctx) ids.add(ctx); }
          if(ids.size===1) el('context').value=[...ids][0];
          else if(ids.size>1) el('status').textContent=tr('Selection spans multiple contexts; choose its host and directory.','选区跨越多个上下文，请选择对应主机和目录。');
        }
        if (!el('text').value) {
          try { const selection = await api(endpoint(id,'selection'),{method:'POST'});el('text').value=selection.text||''; }
          catch (_) { /* An empty selection is normal; users can paste instead. */ }
        }
        el('close').onclick = () => dialog.close();
        dialog.addEventListener('close', () => dialog.remove(), {once:true});
        el('save').onclick = async () => {
          try {
            const value = await api(endpoint(id,'file-context'),{method:'PUT',body:{mode:el('mode').value,host:el('host').value,cwd:el('cwd').value,auto_discover:el('auto').checked}});
            state.data=value;setContexts(value);
            el('status').textContent=tr('Saved. Existing output retains its original context.','已保存。历史输出保留原来的上下文。');
          } catch(error) {el('status').textContent=error.message;}
        };
        const identify = async intelligent => {
          el('scan').disabled=el('model').disabled=true;
          el('status').textContent=tr('Checking files…','正在检查文件…');
          el('results').replaceChildren();
          try {
            const result=await api(endpoint(id,'discover-files'),{method:'POST',body:{text:el('text').value,context_id:el('context').value,intelligent}});
            for(const item of result.files) {
              const button=document.createElement('button');button.className='ui-button';
              button.textContent=item.source_path;button.style.overflowWrap='anywhere';
              button.onclick=()=>void openViewer(id,item.folder.path);el('results').append(button);
            }
            el('status').textContent=`${result.files.length} ${tr('files found','个文件已找到')}${result.errors.length ? '\n'+result.errors.map(e=>e.path+': '+e.error).join('\n'):''}${result.limited?' · '+tr('First 8 candidates checked; narrow the selection for more.','本次检查前 8 个候选，请缩小选区继续。'):''}`;
          } catch(error) {el('status').textContent=error.message;}
          finally {el('scan').disabled=el('model').disabled=false;}
        };
        el('scan').onclick=()=>void identify(false);el('model').onclick=()=>void identify(true);
        dialog.showModal();
      };
      return {attach, openPath, configure, states};
    },
  };
})();
