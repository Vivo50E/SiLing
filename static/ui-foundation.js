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
    const [kind, label] = known[name.toLowerCase()] || ["unknown", name];
    return { kind, label };
  }
  function agentBadge(agent) {
    const { kind, label } = agentIdentity(agent);
    return `<span class="agent-badge agent-${kind}" title="${escape(label)}">${escape(label)}</span>`;
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
  };
  function icon(name) {
    return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${paths[name] || paths.more}"/></svg>`;
  }
  const strings = {
    en: { copyHistory: "Copy history", selectAll: "Select all", backToTerminal: "Back to terminal", historyLoading: "Loading history…", historyHelp: "Saved scrollback snapshot. Scroll and select text, then press ⌘C / Ctrl+C to copy. Reopen for newer output.", historyEmpty: "No saved history available.", historyError: "Could not load history", settings: "Settings", appearance: "Appearance", terminal: "Terminal", notifications: "Notifications", browsing: "Browsing & files", connections: "Connections & updates", theme: "App theme", density: "Density", fontSize: "Interface text size", motion: "Motion", language: "Language", scope: "Saved in this browser only. Changes apply immediately; running sessions are not restarted.", reset: "Reset appearance", done: "Done", new: "New", search: "Search", layout: "Layout", workspace: "Workspace", more: "More", files: "Files", zoom: "Zoom", system: "System", dark: "Dark", light: "Light", comfortable: "Comfortable", compact: "Compact", reduce: "Reduce motion", appearanceHelp: "App appearance is separate from each terminal's palette and font.", flags: "Role, priority & manual flags", flagsHelp: "Lead = coordinator; P0 / P1 / P2 = priority, highest first. Blocked / Watching / Done are manual flags, not detected execution states. These currently share one saved flag; selecting one replaces the previous flag.", saveError: "Browser storage is unavailable. This change works for this page, but cannot be saved.", saved: "Saved in this browser.", move: "Move / swap with pane", closePane: "Close pane", closeHelp: "The session keeps running; reopen it from the list.", terminateHelp: "Terminate stops execution. Available resume metadata is kept; unsaved program state may be lost.", reconnect: "Reconnect display", terminalTheme: "Terminal theme", connectionHelp: "Copy the login address for a trusted device on the same network. It grants access to this Dashboard; do not share it publicly." },
    zh: { copyHistory: "复制历史", selectAll: "全选", backToTerminal: "返回终端", historyLoading: "正在读取历史…", historyHelp: "已保留历史的静态快照。滚动并选择文本，再按 ⌘C / Ctrl+C 复制。重新打开可获取最新输出。", historyEmpty: "暂无已保留的历史。", historyError: "无法读取历史", settings: "设置", appearance: "外观", terminal: "终端", notifications: "通知", browsing: "浏览与文件", connections: "连接与更新", theme: "应用主题", density: "界面密度", fontSize: "界面字号", motion: "动画", language: "语言", scope: "仅保存在当前浏览器。修改即时生效，不会重启正在运行的会话。", reset: "重置外观", done: "完成", new: "新建", search: "搜索", layout: "布局", workspace: "工作区", more: "更多", files: "文件", zoom: "放大", system: "跟随系统", dark: "深色", light: "浅色", comfortable: "舒适", compact: "紧凑", reduce: "减少动画", appearanceHelp: "应用外观独立于每个终端的配色和字号。", flags: "角色、优先级与人工标记", flagsHelp: "Lead = 协调者；P0 / P1 / P2 = 优先级，从高到低。Blocked / Watching / Done 是人工标记，不代表自动检测的运行状态。目前它们共用一个存储字段，选择新标记会替换旧标记。", saveError: "浏览器存储不可用。本次修改仅在当前页面生效，无法保存。", saved: "已保存到当前浏览器。", move: "移动／交换到面板", closePane: "关闭面板", closeHelp: "会话继续运行，可从列表重新打开。", terminateHelp: "终止会停止执行，并保留已有恢复信息；程序中未保存的状态可能丢失。", reconnect: "重连显示", terminalTheme: "终端主题", connectionHelp: "复制登录地址供同一网络的可信设备访问。该链接授予 Dashboard 访问权限，请勿公开分享。" },
  };
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
  const api = { defaults, key, normalize, read, write, agentIdentity, agentBadge, createdSessionSlot, icon, t, translate, apply, wireDialog, containDialogFocus };
  if (typeof module !== "undefined") module.exports = api;
  else window.SiLingUI = api;
})();
