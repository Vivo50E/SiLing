/* Browser-only presentation preferences. No session or server state is written. */
(() => {
  "use strict";
  const defaults = Object.freeze({ theme: "system", density: "comfortable", fontSize: 14, motion: "system", language: "system" });
  const key = "siling_appearance_v1";
  const choices = {
    theme: ["system", "dark", "light"], density: ["comfortable", "compact"],
    motion: ["system", "reduce"], language: ["system", "en", "zh"],
  };
  function normalize(raw) {
    const value = raw && typeof raw === "object" ? raw : {};
    const result = { ...defaults };
    for (const [name, allowed] of Object.entries(choices)) {
      if (allowed.includes(value[name])) result[name] = value[name];
    }
    if ([14, 15, 16].includes(Number(value.fontSize))) result.fontSize = Number(value.fontSize);
    return result;
  }
  function read(storage) {
    try { return normalize(JSON.parse(storage.getItem(key))); } catch { return normalize(null); }
  }
  function write(storage, value) {
    try { storage.setItem(key, JSON.stringify(normalize(value))); return true; } catch { return false; }
  }
  function escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function agentIdentity(agent) {
    const name = String(agent || "Agent").trim() || "Agent";
    const known = { claude: ["claude", "Claude"], codex: ["codex", "Codex"], cursor: ["cursor", "Cursor"], terminal: ["terminal", "Terminal"] };
    const [kind, label] = Object.hasOwn(known, name.toLowerCase()) ? known[name.toLowerCase()] : ["unknown", name];
    return { kind, label };
  }
  function agentBadge(agent) {
    const { kind, label } = agentIdentity(agent);
    return `<span class="agent-badge agent-${kind}" title="${escape(label)}"><span class="agent-glyph">${icon(`agent-${kind}`)}</span><span class="agent-name">${escape(label)}</span></span>`;
  }
  function createdSessionSlot(slots, requestedSlot, requestedLayout, currentLayout, runId) {
    const existing = slots.indexOf(runId);
    if (existing >= 0) return existing;
    if (requestedLayout === currentLayout && Number.isInteger(requestedSlot)
        && requestedSlot >= 0 && requestedSlot < slots.length && !slots[requestedSlot]) return requestedSlot;
    return slots.findIndex(value => !value);
  }
  // Small original SVG set, bundled locally; no external fonts, CDN, or brand logos.
  const paths = {
    plus: "M12 5v14M5 12h14", search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
    grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    settings: "M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6",
    folder: "M3 7V4h6l3 3h9v13H3z", zoom: "M3 9V3h6M15 3h6v6M21 15v6h-6M9 21H3v-6",
    more: "M5 11v2M12 11v2M19 11v2", workspace: "M3 5h18v15H3zM3 10h18M9 10v10",
    close: "M6 6l12 12M6 18 18 6", refresh: "M20 8a8 8 0 1 0 0 8M20 3v5h-5",
    edit: "m15 4 5 5M4 20l5-1L21 7l-4-4L5 15z",
    bell: "M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 21h4M12 2v2",
    bellOff: "m3 3 18 18M7 7v7l-2 3h12M10 4a5 5 0 0 1 7 5v3M10 21h4",
    bellBlocked: "M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 21h4M12 8v3M12 13v.1",
    activity: "M3 12h4l3-7 4 14 3-7h4",
    palette: "M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-4 2 2 0 0 1 1-4h3a3 3 0 0 0 3-3 9 9 0 0 0-9-7ZM7 10h.1M10 7h.1M15 7h.1",
    connection: "M8 12h8M8 7H6a5 5 0 0 0 0 10h2M16 7h2a5 5 0 0 1 0 10h-2",
    "agent-claude": "M12 3v18M3 12h18M6 6l12 12M6 18 18 6",
    "agent-codex": "m8 5-6 7 6 7M16 5l6 7-6 7M14 3l-4 18",
    "agent-cursor": "m5 3 14 9-7 1-3 7z",
    "agent-terminal": "M3 4h18v16H3zM7 9l3 3-3 3M13 15h4",
    "agent-unknown": "m12 3 9 5v8l-9 5-9-5V8zM3 8l9 5 9-5M12 13v8",
  };
  function icon(name) {
    const path = Object.hasOwn(paths, name) ? paths[name] : paths.more;
    return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg>`;
  }
  function buttonContent(name, label) {
    return `${icon(name)}<span class="ui-button-label">${escape(label)}</span>`;
  }
  function notificationButton(button, enabled, permission) {
    const blocked = enabled && permission === "denied";
    button.innerHTML = icon(blocked ? "bellBlocked" : enabled ? "bell" : "bellOff");
    button.setAttribute("aria-pressed", String(enabled));
    button.setAttribute("aria-label", `Agent notifications: ${enabled ? "on" : "off"}${blocked ? " — blocked by browser" : ""}`);
  }
  const strings = {
    en: { settings: "Settings", appearance: "Appearance", terminal: "Terminal", notifications: "Notifications", browsing: "Browsing & files", connections: "Connections & updates", theme: "App theme", density: "Density", fontSize: "Interface text size", motion: "Motion", language: "Language", scope: "Saved in this browser only. Changes apply immediately; running sessions are not restarted.", reset: "Reset appearance", done: "Done", new: "New", search: "Search", layout: "Layout", workspace: "Workspace", more: "More", files: "Files", zoom: "Zoom", system: "System", dark: "Dark", light: "Light", comfortable: "Comfortable", compact: "Compact", reduce: "Reduce motion", appearanceHelp: "App appearance is separate from each terminal's palette and font.", flags: "Role, priority & manual flags", flagsHelp: "Lead = coordinator; P0 / P1 / P2 = priority, highest first. Blocked / Watching / Done are manual flags, not detected execution states. These currently share one saved flag; selecting one replaces the previous flag.", saveError: "Browser storage is unavailable. This change works for this page, but cannot be saved.", saved: "Saved in this browser.", move: "Move / swap with pane", closePane: "Close pane", closeHelp: "The session keeps running; reopen it from the list.", terminateHelp: "Terminate stops execution. Available resume metadata is kept; unsaved program state may be lost.", reconnect: "Reconnect display", terminalTheme: "Terminal theme", sshFileHost: "SSH file host", sshFileHelp: "File links use this SSH host. Saved in this browser; clear after returning to a local shell.", connectionHelp: "Copy the login address for a trusted device on the same network. It grants access to this Dashboard; do not share it publicly." },
    zh: { settings: "设置", appearance: "外观", terminal: "终端", notifications: "通知", browsing: "浏览与文件", connections: "连接与更新", theme: "应用主题", density: "界面密度", fontSize: "界面字号", motion: "动画", language: "语言", scope: "仅保存在当前浏览器。修改即时生效，不会重启正在运行的会话。", reset: "重置外观", done: "完成", new: "新建", search: "搜索", layout: "布局", workspace: "工作区", more: "更多", files: "文件", zoom: "放大", system: "跟随系统", dark: "深色", light: "浅色", comfortable: "舒适", compact: "紧凑", reduce: "减少动画", appearanceHelp: "应用外观独立于每个终端的配色和字号。", flags: "角色、优先级与人工标记", flagsHelp: "Lead = 协调者；P0 / P1 / P2 = 优先级，从高到低。Blocked / Watching / Done 是人工标记，不代表自动检测的运行状态。目前它们共用一个存储字段，选择新标记会替换旧标记。", saveError: "浏览器存储不可用。本次修改仅在当前页面生效，无法保存。", saved: "已保存到当前浏览器。", move: "移动／交换到面板", closePane: "关闭面板", closeHelp: "会话继续运行，可从列表重新打开。", terminateHelp: "终止会停止执行，并保留已有恢复信息；程序中未保存的状态可能丢失。", reconnect: "重连显示", terminalTheme: "终端主题", sshFileHost: "SSH 文件主机", sshFileHelp: "文件链接从此 SSH 主机读取。设置保存在当前浏览器；退出 SSH 回到本机后请清空。", connectionHelp: "复制登录地址供同一网络的可信设备访问。该链接授予 Dashboard 访问权限，请勿公开分享。" },
  };
  Object.assign(strings.en, {
    systemBrowser: "Open external links via macOS",
    systemBrowserHelp: "Use the system browser instead of the app's profile. Only available directly on this Mac; other devices open links on their own device. Edge's profile rules still apply.",
    systemBrowserFailed: "System open failed. Check the browser before retrying. You can turn off ‘Open external links via macOS’ in Settings.",
    restartAgent: "Restart agent", restartingAgent: "Restarting agent…",
    restartHelp: "Interrupts the current turn and resumes the saved conversation in a new process to reload MCP configuration. Not a display reconnect.",
    restartConfirm: "Restart this agent? This interrupts running work and may lose unsaved input inside the terminal. The saved conversation will be resumed in a new process. External MCP services are not restarted. Other panes are unaffected.",
    restartStarted: "Agent launch requested; waiting for the resumed pane…",
    restartFailed: "Restart did not complete or its result is unknown. Check the session list before retrying. If the agent stopped, use Resume on the saved source.",
  });
  Object.assign(strings.zh, {
    systemBrowser: "通过 macOS 打开外部链接",
    systemBrowserHelp: "交给系统浏览器打开，不沿用 App 的 profile。仅在本机直接连接时可用；其他设备仍在各自浏览器打开。Edge 的 profile 切换规则仍然有效。",
    systemBrowserFailed: "系统打开失败或结果未知，请先检查浏览器，不要重复点击。可在设置中关闭“通过 macOS 打开外部链接”。",
    restartAgent: "重启当前 Agent", restartingAgent: "正在重启 Agent…",
    restartHelp: "中断当前执行，用新进程恢复已保存的对话并重新加载 MCP 配置；不是重连显示。",
    restartConfirm: "重启当前 Agent？这会中断正在执行的任务，终端内未提交的输入可能丢失。将用新进程恢复已保存的对话，不会重启独立的 MCP 服务，也不影响其他面板。",
    restartStarted: "已请求启动 Agent，正在等待恢复后的面板…",
    restartFailed: "重启未完成，或结果尚不确定。请先检查会话列表，不要重复重启。若 Agent 已停止，可从已保存的原会话执行恢复。",
  });
  let language = "en";
  function t(name) { return strings[language][name] || strings.en[name] || name; }
  function translate(root = document) {
    root.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
    root.querySelectorAll("[data-i18n-label]").forEach(el => {
      el.setAttribute("aria-label", t(el.dataset.i18nLabel));
      el.title = t(el.dataset.i18nLabel);
    });
  }
  function apply(value, root = document.documentElement) {
    const prefs = normalize(value);
    language = prefs.language === "system" ? (navigator.language.startsWith("zh") ? "zh" : "en") : prefs.language;
    root.lang = language;
    root.dataset.appTheme = prefs.theme;
    root.dataset.density = prefs.density;
    root.dataset.motion = prefs.motion;
    root.style.setProperty("--ui-font-size", `${prefs.fontSize}px`);
    translate();
  }
  function containDialogFocus(dialog) {
    dialog.addEventListener("keydown", event => {
      if (event.key === "Escape") event.stopPropagation();
      if (event.key !== "Tab") return;
      const controls = [...dialog.querySelectorAll('button, input, textarea, select, a[href], [tabindex]')]
        .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length && getComputedStyle(el).visibility !== "hidden");
      const first = controls[0], last = controls.at(-1);
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    });
  }
  function wireDialog(dialog, trigger, beforeOpen) {
    containDialogFocus(dialog);
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.setAttribute("aria-controls", dialog.id);
    trigger.setAttribute("aria-expanded", "false");
    trigger.addEventListener("click", () => {
      beforeOpen?.();
      dialog.showModal();
      trigger.setAttribute("aria-expanded", "true");
    });
    dialog.addEventListener("close", () => {
      trigger.setAttribute("aria-expanded", "false");
      if (trigger.isConnected) trigger.focus({ preventScroll: true });
    });
    dialog.addEventListener("click", event => {
      if (event.target === dialog || event.target.closest("[data-dialog-close]")) dialog.close();
    });
  }
  const api = { defaults, key, normalize, read, write, agentIdentity, agentBadge, createdSessionSlot, icon, buttonContent, notificationButton, t, translate, apply, wireDialog, containDialogFocus };
  if (typeof module !== "undefined") module.exports = api;
  else window.SiLingUI = api;
})();
