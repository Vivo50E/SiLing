/* Explicit, sequential restart; never launches on page load. */
(() => {
  'use strict';
  window.SilingRestartAll = ({ui,trigger,load,restart,refresh}) => {
    const t=(en,zh)=>document.documentElement.lang.startsWith('zh')?zh:en;
    const dialog=document.createElement('dialog');dialog.id='restart-all-dialog';dialog.className='ui-dialog';
    dialog.style.cssText='width:min(680px,94vw);max-height:85vh;overflow:auto';
    dialog.innerHTML='<div class="modal-head"><h2 id="restart-all-title"></h2><button class="restart-all-close">×</button></div><div class="modal-body"><p class="restart-all-help"></p><p class="restart-all-status" role="status"></p><ol class="restart-all-list"></ol><button class="restart-all-start primary"></button><button class="restart-all-stop"></button></div>';
    dialog.setAttribute('aria-labelledby','restart-all-title');document.body.append(dialog);ui.containDialogFocus(dialog);
    const $=s=>dialog.querySelector(s),start=$('.restart-all-start'),stop=$('.restart-all-stop'),status=$('.restart-all-status'),list=$('.restart-all-list');
    let busy=false,cancelled=false,queue=[],attempted=new Set();
    const label=()=>{trigger.textContent=t('Restart all Agents','重启所有 Agent');};label();
    new MutationObserver(label).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
    const close=()=>{if(busy){cancelled=true;status.textContent=t('Stopping after the current session…','当前会话处理完后停止…');}else dialog.close();};
    $('.restart-all-close').onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});stop.onclick=close;
    const bounded=async action=>{const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),75000);try{return await action(controller.signal);}finally{clearTimeout(timer);}};
    trigger.onclick=async()=>{
      if(dialog.open)return;
      dialog.showModal();busy=true;cancelled=false;start.disabled=true;list.replaceChildren();queue=[];
      $('#restart-all-title').textContent=t('Restart all Agents','重启所有 Agent');
      $('.restart-all-close').ariaLabel=t('Close','关闭');
      $('.restart-all-help').textContent=t('Restart running Claude, Codex and Cursor sessions across all groups, including background sessions, one at a time. This interrupts running work. Each session resumes its saved conversation and model using the currently installed CLI; this does not download updates. Terminal/SSH, stopped, archived, offline and sessions without a saved conversation are excluded. Pane positions and drafts are kept.','逐个重启所有分组中运行的 Claude、Codex 和 Cursor（包括后台会话）。这会中断正在执行的工作。使用已安装的 CLI 恢复各自保存的对话和模型，不下载更新。跳过 Terminal/SSH、已停止、已归档、离线和没有保存对话的会话，保留 pane 位置和草稿。');
      status.textContent=t('Loading…','正在加载…');start.textContent=t('Confirm restart','确认重启');stop.textContent=t('Cancel','取消');
      try{
        queue=(await bounded(load)).filter(s=>!attempted.has(s.run_id));
        for(const session of queue){const item=document.createElement('li');item.textContent=`${session.display_name||session.task||session.run_id} · ${session.agent} · ${session.node_label||session.node_id||'local'}`;list.append(item);}
        status.textContent=t(`${queue.length} sessions ready for review.`,`${queue.length} 个会话待确认重启。`);
      }catch(error){status.textContent=error.message;}
      finally{busy=false;start.disabled=!queue.length;if(cancelled)dialog.close();}
    };
    start.onclick=async()=>{
      if(busy||!queue.length)return;
      busy=true;cancelled=false;start.disabled=true;stop.textContent=t('Stop remaining','停止后续重启');
      let succeeded=0,failed=0,skipped=0;
      for(let i=0;i<queue.length&&!cancelled;i++){
        const session=queue[i],item=list.children[i],name=item.textContent;
        status.textContent=t(`Restarting ${i+1}/${queue.length}…`,`正在重启 ${i+1}/${queue.length}…`);
        try{
          // Recheck after confirmation: another pane/client may already have restarted it.
          const current=(await bounded(load)).find(s=>s.run_id===session.run_id);
          if(!current){skipped++;item.textContent=name+t(' — skipped (state changed)',' — 已跳过（状态已变化）');continue;}
          if(cancelled)break;
          attempted.add(session.run_id);
          const result=await bounded(signal=>restart(current,signal));
          if(!result?.ok)throw new Error(result?.reason||t('Restart failed','重启失败'));
          if(result.run_id)attempted.add(result.run_id);
          succeeded++;item.textContent=name+t(' — restarted',' — 已重启');
        }catch(error){failed++;item.textContent=name+' — '+error.message;}
      }
      busy=false;stop.textContent=t('Close','关闭');
      status.textContent=t(`Finished: ${succeeded} restarted, ${failed} failed, ${skipped} skipped${cancelled?' (remaining cancelled)':''}. Failed or timed-out requests are not retried automatically; check individual sessions.`,`完成：重启 ${succeeded}，失败 ${failed}，跳过 ${skipped}${cancelled?'（已取消后续重启）':''}。失败或超时不会自动重试，请检查对应会话。`);
      refresh();
    };
  };
})();
