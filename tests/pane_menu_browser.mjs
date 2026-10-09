import assert from 'node:assert/strict';
export async function checkPaneMenu({evaluate,waitFor,cdp,viewport,screenshot}) {
  await evaluate(`window.menuFrame=document.querySelector('[data-run-id="fixture-0"] iframe');document.querySelector('[data-run-id="fixture-0"] .btn-pane-more').click()`);
  await waitFor(`!!document.querySelector('.pane-menu[open]')`);
  assert.equal(await evaluate(`document.querySelectorAll('.pane-menu[open] details').length`),4);
  assert.equal(await evaluate(`document.querySelectorAll('.pane-menu[open] details[open]').length`),0,'Advanced groups start folded');
  assert.ok(await evaluate(`document.querySelector('.pane-menu[open] .btn-rename-session').checkVisibility()`),'Rename stays visible');
  assert.equal(await evaluate(`document.querySelector('.pane-menu[open] .btn-terminate').checkVisibility()`),false,'Termination is folded away');
  await screenshot('pane-menu-grouped');
  await evaluate(`document.querySelector('.pane-menu[open] summary').focus()`);
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await waitFor(`document.querySelector('.pane-menu[open] details').open`);
  assert.ok(await evaluate(`document.querySelector('.pane-menu[open] .pane-theme-select').checkVisibility()`),'Keyboard expansion reveals settings');
  await evaluate(`document.querySelectorAll('.pane-menu[open] summary').forEach((el,i)=>{if(i)el.click()})`);
  assert.ok(await evaluate(`document.querySelector('.pane-menu[open] .btn-terminate').checkVisibility()`));
  assert.equal(await evaluate(`document.querySelector('[data-run-id="fixture-0"] iframe')===menuFrame`),true,'Grouping preserves terminal iframe');
  await evaluate(`document.querySelectorAll('.pane-menu[open] details[open] summary').forEach(el=>el.click());document.querySelector('.pane-menu[open] details:last-child summary').focus()`);
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  assert.equal(await evaluate(`document.activeElement===document.querySelector('.pane-menu[open] .modal-head button')`),true,'Tab wraps past folded groups to the close control');
  // Pane menus belong to the desktop grid; mobile switches to the session reader.
  await viewport(860,740);
  await evaluate(`{const language=document.querySelector('[data-appearance="language"]');language.value='zh';language.dispatchEvent(new Event('change'));}`);
  assert.equal(await evaluate(`document.querySelector('.pane-menu[open] details:last-child summary').textContent`),'会话管理');
  assert.ok(await evaluate(`(()=>{const r=document.querySelector('.pane-menu[open]').getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight})()`));
  await screenshot('pane-menu-grouped-narrow');
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await waitFor(`!document.querySelector('.pane-menu[open]')`);
  await evaluate(`{const language=document.querySelector('[data-appearance="language"]');language.value='en';language.dispatchEvent(new Event('change'));}`);
  await viewport(1280,800);
  console.log('PASS: grouped pane menu, default disclosure, keyboard navigation, terminal identity and narrow desktop Chinese layout');
}
