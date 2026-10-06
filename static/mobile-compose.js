/* Ordinary mobile drafts, separate from desktop and private-input storage. */
(() => {
  "use strict";
  window.SilingMobileCompose = {create};
  function create({parent, api, message:t, title, refresh}) {
    const states = new Map(), prefix = "siling_mobile_draft_v1:";
    let id = "", row = null, active = false, opened = false, pending = null, storageFailed = false;
    const node = (tag, suffix, host = parent) => {
      const el = document.createElement(tag); el.id = "mobile-compose" + (suffix ? "-" + suffix : "");
      host.append(el); return el;
    };
    const host = node("div", ""); host.hidden = true;
    const label = node("label", "label", host);
    const input = node("textarea", "text", host); input.rows = 3; input.maxLength = 8000;
    label.htmlFor = input.id;
    const tools = node("div", "tools", host);
    const button = (suffix, action) => {
      const el = node("button", suffix, tools); el.type = "button"; el.onclick = action; return el;
    };
    const keys = ["Escape", "Tab", "C-c"].map(key => {
      const el = button("key-" + key, () => void deliver(key)); el.dataset.key = key; return el;
    });
    const send = button("send", () => void deliver()); send.className = "primary";
    const status = node("p", "status", host); status.setAttribute("role", "status");
    const warning = node("p", "storage", host); warning.setAttribute("role", "status");
    const check = node("button", "check", host); check.type = "button"; check.onclick = refresh;
    const review = node("button", "review", host); review.type = "button";
    const name = () => row ? title(row) : id;
    review.onclick = () => {
      if (!id || pending) return;
      if (!window.confirm(t("Check the output first. Previous input may already have arrived. Allow another send to {name}?", {name:name()}))) return;
      const state = get(id); state.delivery = "draft"; save(id); render();
    };
    function get(key) {
      if (!states.has(key)) {
        let state = {text:"", delivery:"draft"};
        try {
          const raw = sessionStorage.getItem(prefix + key);
          if (raw) {
            const data = JSON.parse(raw);
            if (data?.version !== 1 || typeof data.text !== "string" || data.text.length > 8000
                || !["draft","sending","uncertain","accepted","offline"].includes(data.delivery)) throw Error("invalid draft");
            state = {text:data.text, delivery:data.delivery === "sending" ? "uncertain" : data.delivery};
          }
        } catch (_) {storageFailed = true;}
        states.set(key, state);
      }
      return states.get(key);
    }
    function save(key) {
      try {sessionStorage.setItem(prefix + key, JSON.stringify({version:1, ...get(key)}));}
      catch (_) {storageFailed = true;}
    }
    input.addEventListener("input", () => {
      if (!id) return;
      const state = get(id); state.text = input.value;
      if (state.delivery === "accepted") state.delivery = "draft";
      save(id); render();
    });
    function enabled() {return active && row?.alive && !row.agent_exited && row.node_online !== false;}
    function render() {
      host.hidden = !active || !opened || !id;
      parent.classList.toggle("composing", !host.hidden);
      if (!id) return;
      const state = get(id), uncertain = state.delivery === "uncertain";
      host.dataset.delivery = state.delivery;
      label.textContent = t("Reply to {name}", {name:name()});
      input.placeholder = t("Enter inserts a newline. Use Send to submit. Do not enter secrets.");
      input.disabled = !!pending && pending.id === id;
      send.textContent = t("Send");
      send.disabled = !enabled() || !!pending || uncertain || !input.value.length || input.value.length > 8000;
      for (const key of keys) {
        key.textContent = key.dataset.key === "C-c" ? t("Ctrl+C · interrupt") : key.dataset.key === "Escape" ? "Esc" : "Tab";
        key.setAttribute("aria-label", t("Send {key} to this session", {key:key.textContent}));
        key.disabled = !enabled() || !!pending || uncertain;
      }
      const messages = {
        sending:"Sending to the terminal…", accepted:"Terminal input accepted; agent execution is not confirmed.",
        uncertain:"Delivery unknown. Draft kept. Check output before allowing another send.",
        offline:"Offline — not sent. Draft kept; reconnect and send explicitly.",
        draft:"This draft stays in this tab, separately from desktop input.",
      };
      status.textContent = t(messages[state.delivery]);
      if (!enabled() && !uncertain && state.delivery !== "sending") status.textContent = t("Session unavailable or ended — input disabled; draft kept.");
      warning.hidden = !storageFailed;
      warning.textContent = t("Draft storage unavailable or invalid. This copy is in memory only; do not reload this tab.");
      check.textContent = t("Check output"); check.hidden = !uncertain;
      review.textContent = t("I checked — allow another send"); review.hidden = !uncertain; review.disabled = !!pending;
    }
    async function deliver(key = "") {
      if (!id || !enabled() || pending || get(id).delivery === "uncertain") return;
      const target = id, state = get(target), text = state.text;
      if (!key && (!text.length || text.length > 8000)) return;
      if (key === "C-c" && !window.confirm(t("Send Ctrl+C to {name}? This may interrupt its current work.", {name:name()}))) return;
      if (navigator.onLine === false) {state.delivery = "offline"; save(target); render(); return;}
      const controller = new AbortController();
      const request = {id:target, controller}; pending = request;
      state.delivery = "sending"; save(target); render();
      const timeout = setTimeout(() => controller.abort(), 12000);
      try {
        const result = await api(`/api/sessions/${encodeURIComponent(target)}/input`, {
          method:"POST", body:key ? {key} : {text}, signal:controller.signal,
          promptForToken:false, cache:"no-store",
        });
        if (result?.ok !== true || result.delivery !== "accepted") throw Error("unconfirmed");
        state.delivery = "accepted";
        if (!key && state.text === text) state.text = "";
      } catch (_) {state.delivery = "uncertain";}
      finally {
        clearTimeout(timeout); if (pending === request) pending = null;
        save(target);
        if (id === target) input.value = state.text;
        render();
        if (id === target && active && opened) refresh();
      }
    }
    function setSession(next, nextRow, available) {
      if (next !== id) {opened = false; id = next; input.value = id ? get(id).text : "";}
      row = nextRow; active = available; render();
    }
    function toggle() {opened = !opened; render(); if (opened) input.focus({preventScroll:true});}
    window.addEventListener("offline", () => {pending?.controller.abort(); render();});
    window.addEventListener("online", render);
    document.addEventListener("visibilitychange", () => {if (document.hidden) pending?.controller.abort();});
    return {setSession, toggle, get opened() {return opened;}};
  }
})();
