/* On-demand pane Jira links. Opening a dialog never reconnects the terminal. */
(() => {
  'use strict';
  window.SilingPaneJira = {open({runId, title, trigger, api, ui, openUrl, changed}) {
    if (document.querySelector('#pane-jira')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'pane-jira';
    dialog.dataset.runId=runId;
    dialog.className = 'pane-reviews';
    dialog.setAttribute('aria-labelledby', 'pane-jira-title');
    dialog.innerHTML = `<header><h2 id="pane-jira-title"></h2><button type="button" data-close></button></header>
      <p data-session></p><p data-help></p><div class="review-toolbar"><button type="button" data-refresh></button><span data-branch></span></div>
      <p data-status role="status"></p><ul data-list></ul>
      <form><label for="pane-jira-url" data-label></label><div class="review-toolbar"><input id="pane-jira-url" type="url" required placeholder="https://…" autocomplete="off"><button type="submit" data-add></button></div><p data-error role="alert"></p></form>`;
    const el = name => dialog.querySelector(`[data-${name}]`);
    document.body.append(dialog);
    const translations={'Close':'关闭','Refresh':'刷新','Add':'添加','Add a Jira link':'添加 Jira 链接','Related Jira tickets':'相关 Jira tickets','Saved links and recent output; no Jira API calls or background polling.':'来自已关联链接和最近输出；不调用 Jira API，不后台轮询。','No related Jira tickets found. Add a link below.':'未找到相关 Jira ticket，可在下方添加链接。','Loading Jira tickets…':'正在加载 Jira tickets…','Could not load Jira tickets. Retry.':'加载失败，请重试。','Enter a Jira ticket URL ending in /browse/PROJECT-123.':'请输入以 /browse/PROJECT-123 结尾的 Jira ticket 链接。','linked':'已关联','output':'输出'};
    const t=value=>document.documentElement.lang.startsWith('zh')?(translations[value]||ui.message(value)):value;
    const labels={close:'Close',refresh:'Refresh',label:'Add a Jira link',add:'Add',help:'Saved links and recent output. Connect Jira MCP in Settings to resolve ticket keys automatically; no background polling.'};
    for (const [name,label] of Object.entries(labels)) el(name).textContent=t(label);
    dialog.querySelector('h2').textContent=t('Related Jira tickets');
    el('session').textContent=title;
    let busy=false,closed=false;
    const setBusy=value=>{busy=value;el('refresh').disabled=value;el('add').disabled=value;};
    const render=data=>{
      window.SilingPaneLinkCounts.loaded(runId, 'jira', data.items);
      el('list').replaceChildren();
      el('branch').textContent='';
      el('help').textContent=ui.message(labels.help);
      el('status').textContent=data.mcp_error ? ui.message(data.mcp_error==='config_changed' ? 'MCP configuration changed. Reconnect in Settings.' : 'Jira MCP unavailable. Saved links are still shown; retry or check Settings.') :
        data.failed ? ui.message('Some ticket keys could not be verified. Saved links are still shown.') :
        data.pending ? ui.message('More ticket keys remain. Refresh to continue.') : data.warning ? t(data.warning) : data.items.length ? '' : t('No related Jira tickets found. Add a link below.');
      for (const item of data.items) {
        // Validate even server-provided URLs before handing them to web routing.
        let url;try {url=new URL(item.url);} catch {continue;}
        if (!['http:','https:'].includes(url.protocol) || url.username || url.password) continue;
        const row=document.createElement('li'),link=document.createElement('a'),meta=document.createElement('small');
        link.href=url.href;link.textContent=item.title;link.rel='noopener noreferrer';link.target='_blank';
        link.addEventListener('click',event=>{event.preventDefault();dialog.close();openUrl(url.href);});
        meta.textContent=`${item.key}${item.state ? ' · '+item.state : ''} · ${item.source === 'mcp' ? 'MCP' : t(item.source)}`;
        row.append(link,meta);el('list').append(row);
      }
    };
    const load=async(force=false)=>{
      setBusy(true);el('status').textContent=t('Loading Jira tickets…');
      try {const data=await api(`/api/sessions/${encodeURIComponent(runId)}/jira?lookup=true${force?'&refresh=true':''}`);if(!closed)render(data);}
      catch(error){if(!closed)el('status').textContent=t('Could not load Jira tickets. Retry.')+' '+error.message;}
      finally {if(!closed)setBusy(false);}
    };
    el('close').onclick=()=>dialog.close();
    el('refresh').onclick=()=>{if(!busy)void load(true);};
    dialog.querySelector('form').onsubmit=async event=>{
      event.preventDefault();if(busy)return;
      const value=dialog.querySelector('input').value.trim();
      let url;try{url=new URL(value);}catch{}
      if(!url || !['http:','https:'].includes(url.protocol) || url.username || url.password ||
          !/\/browse\/[A-Z][A-Z0-9_]*-[1-9][0-9]*\/?$/.test(url.pathname)){
        el('error').textContent=t('Enter a Jira ticket URL ending in /browse/PROJECT-123.');return;
      }
      setBusy(true);el('error').textContent='';
      try{
        await api(`/api/sessions/${encodeURIComponent(runId)}/folders`,{method:'POST',body:{path:value,type:'url'}});
        changed?.();if(!closed){dialog.querySelector('input').value='';await load();}
      }catch(error){if(!closed)el('error').textContent=error.message;}
      finally{if(!closed)setBusy(false);}
    };
    dialog.addEventListener('close',()=>{closed=true;dialog.remove();if(trigger?.isConnected)trigger.focus({preventScroll:true});},{once:true});
    ui.containDialogFocus(dialog);dialog.showModal();void load();
  }};
})();
