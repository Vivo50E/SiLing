'use strict';
(async () => {
  const state = await window.silingConnection.read();
  const zh = state.chinese;
  document.documentElement.lang = zh ? 'zh' : 'en';
  if (zh) {
    document.querySelector('#intro').textContent = '连接正在运行的 Dashboard。此应用不会启动或重启 Agent。';
    document.querySelector('#label').textContent = 'Dashboard 地址';
    document.querySelector('#connect').textContent = '保存并连接';
    document.querySelector('#privacy').textContent = '粘贴 siling url 返回的根地址（按需包含 token）。仅保存在本机用户的应用配置中，未加密；远程连接要求 HTTPS 和受信任的证书。';
  }
  const input = document.querySelector('#url'), status = document.querySelector('#status');
  input.value = state.url;
  if (state.failed) status.textContent = zh ? '连接失败，请检查服务、地址和证书后重试。' : 'Connection failed. Check the server, address and certificate, then retry.';
  input.focus();
  document.querySelector('form').addEventListener('submit', async event => {
    event.preventDefault();
    const button = document.querySelector('#connect');
    button.disabled = true;
    try {
      const result = await window.silingConnection.save(input.value.trim());
      if (!result.ok) throw Error('Cannot save');
    } catch {
      status.textContent = zh ? '无法保存：请输入有效的 Dashboard 根地址，并确认配置目录可写。远程地址必须使用 HTTPS。' : 'Cannot save: use a valid Dashboard root URL and a writable profile. Remote addresses require HTTPS.';
      button.disabled = false;
    }
  });
})().catch(() => { document.querySelector('#status').textContent = 'Connection settings unavailable / 无法读取连接设置'; });
