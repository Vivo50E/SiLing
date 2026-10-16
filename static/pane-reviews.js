/* On-demand pane PR/MR list. Opening a dialog never reconnects the terminal. */
(() => {
  'use strict';
  window.SilingPaneReviews = {open({runId, title, trigger, api, ui, openUrl, changed}) {
    if (document.querySelector('#pane-reviews')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'pane-reviews';
    dialog.className = 'pane-reviews';
    dialog.setAttribute('aria-labelledby', 'pane-reviews-title');
    dialog.innerHTML = `<header><h2 id="pane-reviews-title"></h2><button type="button" data-close></button></header>
      <p data-session></p><p data-help></p><div class="review-toolbar"><button type="button" data-refresh></button><span data-branch></span></div>
      <p data-status role="status"></p><ul data-list></ul>
      <form><label for="pane-review-url" data-label></label><div class="review-toolbar"><input id="pane-review-url" type="url" required placeholder="https://…" autocomplete="off"><button type="submit" data-add></button></div><p data-error role="alert"></p></form>`;
    const el = name => dialog.querySelector(`[data-${name}]`);
    document.body.append(dialog);
    const labels={close:'Close',refresh:'Refresh',label:'Add a PR/MR link',add:'Add',help:'Related branch results, linked URLs and recent output. Nothing is polled in the background.'};
    for (const [name,label] of Object.entries(labels)) el(name).textContent=ui.message(label);
    dialog.querySelector('h2').textContent=ui.message('Related PRs / MRs');
    el('session').textContent=title;
    let busy=false,closed=false;
    const setBusy=value=>{busy=value;el('refresh').disabled=value;el('add').disabled=value;};
    const render=data=>{
      window.SilingPaneLinkCounts.loaded(runId, 'reviews', data.items);
      el('list').replaceChildren();
      el('branch').textContent=data.branch || '';
      el('status').textContent=data.warning ? ui.message(data.warning) : data.items.length ? '' : ui.message('No related PR/MR found. Add a link below.');
      for (const item of data.items) {
        // Validate even server-provided URLs before handing them to web routing.
        let url;try {url=new URL(item.url);} catch {continue;}
        if (!['http:','https:'].includes(url.protocol) || url.username || url.password) continue;
        const row=document.createElement('li'),link=document.createElement('a'),meta=document.createElement('small');
        link.href=url.href;link.textContent=item.title;link.rel='noopener noreferrer';link.target='_blank';
        link.addEventListener('click',event=>{event.preventDefault();dialog.close();openUrl(url.href);});
        meta.textContent=`${item.kind} ${item.kind==='MR'?'!':'#'}${item.number} · ${item.project} · ${ui.message(item.state)} · ${ui.message(item.source)}`;
        row.append(link,meta);el('list').append(row);
      }
    };
    const load=async(branch=true)=>{
      setBusy(true);el('status').textContent=ui.message('Loading PRs / MRs…');
      try {const data=await api(`/api/sessions/${encodeURIComponent(runId)}/reviews?branch=${branch}`);if(!closed)render(data);}
      catch(error){if(!closed)el('status').textContent=ui.message('Could not load PRs / MRs. Retry.')+' '+error.message;}
      finally {if(!closed)setBusy(false);}
    };
    el('close').onclick=()=>dialog.close();
    el('refresh').onclick=()=>{if(!busy)void load();};
    dialog.querySelector('form').onsubmit=async event=>{
      event.preventDefault();if(busy)return;
      const value=dialog.querySelector('input').value.trim();
      let url;try{url=new URL(value);}catch{}
      if(!url || !['http:','https:'].includes(url.protocol) || url.username || url.password ||
          !/\/(?:[^/]+\/[^/]+\/pull|.+\/-\/merge_requests)\/[1-9][0-9]*(?:\/(?:files|commits|checks|diffs))?\/?$/.test(url.pathname)){
        el('error').textContent=ui.message('Enter a GitHub PR or GitLab MR URL.');return;
      }
      setBusy(true);el('error').textContent='';
      try{
        await api(`/api/sessions/${encodeURIComponent(runId)}/folders`,{method:'POST',body:{path:value,type:'url'}});
        changed?.();if(!closed){dialog.querySelector('input').value='';await load(false);}
      }catch(error){if(!closed)el('error').textContent=error.message;}
      finally{if(!closed)setBusy(false);}
    };
    dialog.addEventListener('close',()=>{closed=true;dialog.remove();if(trigger?.isConnected)trigger.focus({preventScroll:true});},{once:true});
    ui.containDialogFocus(dialog);dialog.showModal();void load();
  }};
})();
