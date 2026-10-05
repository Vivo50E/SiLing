/* Narrow-screen navigation is independent of desktop slots and preferences. */
(() => {
  "use strict";
  window.SilingMobileReader = {create};
  function create({host, api, message: t, sessions, title, attention, status, files, terminal}) {
    let active = false, selected = "", generation = 0, abort = null, timer = null;
    let last = null, stale = false, reading = false, interactive = false, frame = null;
    let listScroll = 0, query = "", filter = "all";
    const el = (tag, id, parent) => {
      const node = document.createElement(tag);
      if (id) node.id = "mobile-reader-" + id;
      if (parent) parent.append(node);
      return node;
    };
    const button = (id, parent, action) => {
      const node = el("button", id, parent);
      node.type = "button"; node.addEventListener("click", action);
      return node;
    };
    host.id = "mobile-reader"; host.hidden = true;
    const listView = el("section", "home", host);
    const heading = el("h2", "heading", listView);
    const controls = el("div", "filters", listView);
    const search = el("input", "search", controls); search.type = "search";
    const select = el("select", "filter", controls);
    for (const value of ["all", "attention"]) {
      const option = el("option", "", select); option.value = value;
    }
    const list = el("div", "list", listView);
    const detail = el("section", "detail", host); detail.hidden = true;
    const actions = el("div", "actions", detail);
    const back = button("back", actions, () => goBack());
    const fileButton = button("files", actions, () => files(selected));
    const refresh = button("refresh", actions, () => { cancel(); void poll(); });
    const interact = button("interact", actions, () => void toggleTerminal());
    const name = el("h2", "title", detail); name.tabIndex = -1;
    const meta = el("p", "meta", detail);
    const notice = el("p", "notice", detail); notice.setAttribute("role", "status");
    const output = el("pre", "output", detail); output.tabIndex = 0;
    const terminalHost = el("div", "terminal", detail); terminalHost.hidden = true;

    function cancel() {
      generation++;
      clearTimeout(timer); timer = null;
      abort?.abort(); abort = null; reading = false;
    }
    function detach() {
      frame?.remove(); frame = null; interactive = false;
      terminalHost.replaceChildren(); terminalHost.hidden = true; output.hidden = false;
    }
    function updateCopy() {
      heading.textContent = t("Sessions");
      search.placeholder = t("Search sessions"); search.setAttribute("aria-label", t("Search sessions"));
      select.setAttribute("aria-label", t("Session filter"));
      select.options[0].textContent = t("All sessions");
      select.options[1].textContent = t("Needs attention");
      back.textContent = t("Back to sessions"); fileButton.textContent = t("Files");
      refresh.textContent = t("Refresh snapshot");
      interact.textContent = t(interactive ? "Return to read-only" : "Open interactive terminal");
      output.setAttribute("aria-label", t("Read-only output"));
      const row = sessions().find(s => s.run_id === selected);
      name.textContent = row ? title(row) : selected;
      interact.disabled = !interactive && (!row?.alive || row.node_online === false);
      refresh.disabled = interactive || reading;
      const source = last?.source === "tmux" ? t("Terminal snapshot") : last?.source === "log" ? t("Saved log") : t("Output unavailable");
      const time = Number(last?.observed_at);
      const when = time > 0 && Number.isFinite(time)
        ? t("Snapshot read at {time}", {time:new Date(time * 1000).toLocaleTimeString(document.documentElement.lang)})
        : t("Snapshot time unknown");
      const truncation = last?.truncated === true ? t("Truncated output")
        : last?.truncated === false ? t("Complete requested snapshot") : t("Truncation unknown");
      meta.textContent = last ? [source, when, t("Output update time unknown"), truncation].join(" · ") : "";
      notice.textContent = interactive ? t("Interactive terminal — input goes to this session")
        : stale ? t("Refresh failed — previous snapshot may be stale. Retry to check.")
        : reading && !last ? t("Loading snapshot…")
        : last && !last.text ? t("No output yet") : "";
    }
    function renderList() {
      const scroll = list.scrollTop;
      const focus = list.contains(document.activeElement) ? document.activeElement.dataset.runId : "";
      list.replaceChildren();
      for (const row of sessions()) {
        if (filter === "attention" && !attention(row)) continue;
        if (query && !(title(row) + " " + (row.agent || "")).toLocaleLowerCase().includes(query)) continue;
        const item = button("", list, () => open(row.run_id));
        item.dataset.runId = row.run_id; item.className = "mobile-session";
        const label = el("strong", "", item); label.textContent = title(row);
        const info = el("span", "", item);
        info.textContent = [row.agent || "Agent", status(row)].filter(Boolean).join(" · ");
      }
      if (!list.childElementCount) el("p", "", list).textContent = t("No matching sessions");
      list.scrollTop = scroll;
      if (focus) [...list.querySelectorAll("button")].find(n => n.dataset.runId === focus)?.focus({preventScroll:true});
    }
    search.addEventListener("input", () => {query = search.value.trim().toLocaleLowerCase(); renderList();});
    select.addEventListener("change", () => {filter = select.value; renderList();});
    function update() {
      if (!active) return;
      updateCopy();
      if (!selected) renderList();
    }
    function open(id) {
      if (!active) return;
      if (!selected) listScroll = list.scrollTop;
      cancel(); detach(); selected = id; last = null; stale = false;
      listView.hidden = true; detail.hidden = false; output.textContent = "";
      updateCopy(); name.focus(); void poll();
    }
    function goBack() {
      const old = selected;
      cancel(); detach(); selected = ""; last = null; stale = false;
      detail.hidden = true; listView.hidden = false; update();
      list.scrollTop = listScroll;
      [...list.querySelectorAll("button")].find(n => n.dataset.runId === old)?.focus({preventScroll:true});
    }
    async function poll() {
      if (!active || !selected || interactive || document.hidden || reading) return;
      const token = generation, id = selected;
      abort = new AbortController(); const controller = abort;
      const timeout = setTimeout(() => controller.abort(), 12000);
      reading = true; updateCopy();
      try {
        const result = await api("/api/sessions/" + encodeURIComponent(id) + "/read?lines=200&position=tail&max_chars=32000", {signal:controller.signal});
        if (token !== generation || !active || selected !== id) return;
        if (!result?.ok || typeof result.text !== "string") throw Error("unavailable");
        // Older remote nodes may ignore the optional cap; bound the rendered text too.
        const chars = Array.from(result.text);
        if (chars.length > 32000) {result.text = chars.slice(-32000).join(""); result.truncated = true;}
        const bottom = output.scrollHeight - output.scrollTop - output.clientHeight < 40;
        const first = !last;
        last = result; stale = false;
        if (output.textContent !== result.text) output.textContent = result.text;
        if (first || bottom) output.scrollTop = output.scrollHeight;
      } catch (_) {
        if (token === generation) stale = true;
      } finally {
        clearTimeout(timeout);
        if (token === generation) {
          reading = false; abort = null; updateCopy();
          if (active && selected && !interactive && !document.hidden) timer = setTimeout(poll, 5000);
        }
      }
    }
    async function toggleTerminal() {
      if (interactive) {cancel(); detach(); updateCopy(); void poll(); return;}
      cancel(); interactive = true; updateCopy();
      output.hidden = true; terminalHost.hidden = false;
      const token = generation, id = selected;
      const controller = new AbortController(); abort = controller;
      const timeout = setTimeout(() => controller.abort(), 12000);
      try {
        const result = await api("/api/sessions/" + encodeURIComponent(id) + "/tty", {signal:controller.signal});
        if (token !== generation || !active || selected !== id) return;
        if (!result?.ok || !result.url) throw Error("unavailable");
        frame = terminal(result, sessions().find(s => s.run_id === id) || {run_id:id});
        frame.title = t("Interactive terminal"); terminalHost.append(frame);
      } catch (_) {
        if (token === generation) {detach(); stale = true; updateCopy();}
      } finally {
        clearTimeout(timeout);
        if (token === generation) abort = null;
      }
    }
    function setActive(value) {
      if (active === value) return;
      active = value; host.hidden = !active;
      cancel(); detach();
      if (active) {update(); if (selected) void poll();}
    }
    document.addEventListener("visibilitychange", () => {
      if (!active || interactive) return;
      cancel(); if (!document.hidden) void poll();
    });
    new MutationObserver(update).observe(document.documentElement, {attributes:true,attributeFilter:["lang"]});
    return {setActive, update, open};
  }
})();
