/* Explicit, sequential recovery; never launches on page load. */
(() => {
  'use strict';
  window.SilingResumeAll = ({ui,trigger,load,resume,refresh}) => {
    const t=(en,zh)=>document.documentElement.lang.startsWith('zh')?zh:en;
    const dialog=document.createElement('dialog');dialog.id='resume-all-dialog';dialog.className='ui-dialog';
    dialog.style.cssText='width:min(680px,94vw);max-height:85vh;overflow:auto';
    dialog.innerHTML='<div class="modal-head"><h2 id="resume-all-title"></h2><button class="resume-all-close">×</button></div><div class="modal-body"><p class="resume-all-help"></p><p class="resume-all-status" role="status"></p><ol class="resume-all-list"></ol><button class="resume-all-start primary"></button><button class="resume-all-stop"></button></div>';
    dialog.setAttribute('aria-labelledby','resume-all-title');document.body.append(dialog);ui.containDialogFocus(dialog);
    const $=s=>dialog.querySelector(s),start=$('.resume-all-start'),stop=$('.resume-all-stop'),status=$('.resume-all-status'),list=$('.resume-all-list');
    let busy=false,cancelled=false,queue=[],attempted=new Set();
    const label=()=>{trigger.textContent=t('Resume all sessions','恢复所有会话');};label();
    new MutationObserver(label).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
    const close=()=>{if(busy){cancelled=true;status.textContent=t('Stopping after the current session…','当前会话处理完后停止…');}else dialog.close();};
    $('.resume-all-close').onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});stop.onclick=close;
    const bounded=async action=>{const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),60000);try{return await action(controller.signal);}finally{clearTimeout(timer);}};
    trigger.onclick=async()=>{
      if(dialog.open)return;
      dialog.showModal();busy=true;cancelled=false;start.disabled=true;list.replaceChildren();queue=[];
      $('#resume-all-title').textContent=t('Resume all sessions','恢复所有会话');
      $('.resume-all-close').ariaLabel=t('Close','关闭');
      $('.resume-all-help').textContent=t('Resume stopped Agents across all groups, one at a time. Running, archived, offline and Terminal/SSH sessions are excluded. Missing conversations will not be replaced with new ones. Existing pane positions are kept; other sessions run in the background.','逐个恢复所有分组中已停止的 Agent，跳过运行中、已归档、离线和 Terminal/SSH 会话。缺失的对话不会自动新建。保留已有 pane 位置，其余会话在后台运行。');
      status.textContent=t('Loading…','正在加载…');start.textContent=t('Confirm resume','确认恢复');stop.textContent=t('Cancel','取消');
      try{
        queue=(await bounded(load)).filter(s=>!attempted.has(s.run_id));
        for(const session of queue){const item=document.createElement('li');item.textContent=`${session.display_name||session.task||session.run_id} · ${session.agent} · ${session.node_label||session.node_id||'local'}`;list.append(item);}
        status.textContent=t(`${queue.length} sessions ready for review.`,`${queue.length} 个会话待确认恢复。`);
      }catch(error){status.textContent=error.message;}
      finally{busy=false;start.disabled=!queue.length;if(cancelled)dialog.close();}
    };
    start.onclick=async()=>{
      if(busy||!queue.length)return;
      busy=true;cancelled=false;start.disabled=true;stop.textContent=t('Stop remaining','停止后续恢复');
      let succeeded=0,failed=0,skipped=0;
      for(let i=0;i<queue.length&&!cancelled;i++){
        const session=queue[i],item=list.children[i],name=item.textContent;
        status.textContent=t(`Recovering ${i+1}/${queue.length}…`,`正在恢复 ${i+1}/${queue.length}…`);
        try{
          // Recheck after confirmation: another pane/client may already have resumed it.
          const current=(await bounded(load)).find(s=>s.run_id===session.run_id);
          if(!current){skipped++;item.textContent=name+t(' — skipped (state changed)',' — 已跳过（状态已变化）');continue;}
          if(cancelled)break;
          attempted.add(session.run_id);
          const result=await bounded(signal=>resume(current,signal));
          if(!result?.ok)throw new Error(result?.reason||t('Recovery failed','恢复失败'));
          succeeded++;item.textContent=name+t(' — resumed',' — 已恢复');
        }catch(error){failed++;item.textContent=name+' — '+error.message;}
      }
      busy=false;stop.textContent=t('Close','关闭');
      status.textContent=t(`Finished: ${succeeded} resumed, ${failed} failed, ${skipped} skipped${cancelled?' (remaining cancelled)':''}. Failed or timed-out requests are not retried automatically; check individual sessions.`,`完成：恢复 ${succeeded}，失败 ${failed}，跳过 ${skipped}${cancelled?'（已取消后续恢复）':''}。失败或超时不会自动重试，请检查对应会话。`);
      refresh();
    };
  };
})();
