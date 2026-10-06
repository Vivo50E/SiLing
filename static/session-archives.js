/* Filing metadata never controls an agent or moves its files. */
(() => {
  "use strict";
  window.SilingSessionArchives = {create};
  function create({api, ui, trigger, sessions, title, status, project, files, changed, refresh}) {
    const t = ui.message;
    let view = {revision:-1, entries:{}}, available = false, error = "", busy = false;
    let opener = trigger, selected = "", controller = null;
    const drafts = new Map();
    const node = (tag, parent, cls = "") => {
      const el = document.createElement(tag); el.className = cls; parent.append(el); return el;
    };
    const dialog = node("dialog", document.body, "ui-dialog"); dialog.id = "session-archives";
    dialog.setAttribute("aria-labelledby", "session-archives-title");
    const head = node("div", dialog, "modal-head");
    const heading = node("h2", head); heading.id = "session-archives-title";
    const close = node("button", head); close.textContent = "×";
    close.onclick = () => dialog.close();
    const body = node("div", dialog, "modal-body");
    const help = node("p", body);
    const notice = node("p", body); notice.setAttribute("role", "status");
    const search = node("input", body); search.type = "search";
    const list = node("div", body, "archive-list");
    const preview = node("section", body, "archive-preview"); preview.hidden = true;
    const previewTitle = node("h3", preview);
    const evidence = node("p", preview);
    const output = node("pre", preview); output.tabIndex = 0;
    const retry = node("button", body); retry.onclick = () => void refresh();
    ui.containDialogFocus(dialog);
    const isArchived = id => view.entries[id]?.archived === true;
    const supported = row => row && !row.remote && ["task", "run"].includes(row.kind);
    const rowFor = id => sessions().find(row => row.run_id === id);
    function render() {
      const ids = Object.keys(view.entries).filter(isArchived);
      const running = ids.filter(id => {const row = rowFor(id); return row?.alive && !row.agent_exited;}).length;
      trigger.textContent = t("Archived {count} · running {running}", {count:ids.length, running});
      trigger.title = error ? t(error) : t("Archive keeps agents running and preserves existing history and Files.");
      trigger.dataset.count = ids.length;
      heading.textContent = t("Archived sessions"); close.setAttribute("aria-label", t("Close"));
      help.textContent = t("Archive keeps agents running and preserves existing history and Files.");
      notice.textContent = error ? t(error) : t("Shared by this Dashboard. Unarchive returns to the list, without opening or restarting a pane.");
      search.placeholder = t("Search name, project or agent"); search.setAttribute("aria-label", search.placeholder);
      retry.textContent = t("Refresh"); retry.disabled = busy;
      if (!dialog.open) return;
      const focused = list.contains(document.activeElement) ? [document.activeElement.dataset.id, document.activeElement.dataset.action] : null;
      const scroll = list.scrollTop;
      list.replaceChildren();
      for (const id of ids) {
        const row = rowFor(id), name = row ? title(row) : id;
        const projectName = row ? project(row) : "";
        const bag = [name, row?.agent, row?.cwd, projectName].join(" ").toLocaleLowerCase();
        if (!bag.includes(search.value.trim().toLocaleLowerCase())) continue;
        const item = node("section", list, "archive-item"); item.dataset.id = id;
        node("strong", item).textContent = name;
        node("p", item).textContent = [projectName, row?.agent, row ? status(row) : t("Session metadata unavailable"),
          new Date(view.entries[id].archived_at * 1000).toLocaleString(document.documentElement.lang)].filter(Boolean).join(" · ");
        const actions = node("div", item, "archive-actions");
        for (const [action, label] of [["read", "View output"], ["files", "Files"], ["restore", "Unarchive"]]) {
          const button = node("button", actions); button.textContent = t(label);
          button.dataset.id = id; button.dataset.action = action;
          button.disabled = busy || !row || (action === "restore" && !available);
          button.onclick = () => {
            if (action === "restore") void change(id, false);
            else if (action === "files") {dialog.close(); files(id);}
            else void read(id);
          };
        }
      }
      if (!list.childElementCount) node("p", list).textContent = t("No archived sessions match");
      list.scrollTop = scroll;
      if (focused) ([...list.querySelectorAll("button")].find(b => !b.disabled && b.dataset.id === focused[0] && b.dataset.action === focused[1]) || search).focus({preventScroll:true});
    }
    function receive(data) {
      if (!data || data.version !== 1 || !data.entries || !Number.isInteger(data.revision)) {
        available = false; error = "Archive state unavailable — refresh before retrying"; render(); return false;
      }
      if (data.revision < view.revision) return false;
      const updated = !available || data.revision !== view.revision;
      view = data; available = true; error = ""; render(); return updated;
    }
    async function change(id, archived = true) {
      if (busy) return;
      const row = rowFor(id);
      if (!available || !supported(row)) {
        window.alert(t(!available ? "Archive state unavailable — refresh before retrying" : "Archive currently supports persisted local sessions only")); return;
      }
      if (archived && !window.confirm(t("Archive {name}?\n\nThis hides its displays on all devices using this Dashboard. Running agents keep running; ended agents are not restarted. Existing drafts, history and Files are kept; no files are moved.", {name:title(row)}))) return;
      busy = true; render();
      const abort = new AbortController(); const timeout = setTimeout(() => abort.abort(), 8000);
      try {
        const result = await api("/api/session-archives", {method:"POST", signal:abort.signal,
          body:{run_id:id, archived, expected_revision:view.entries[id]?.revision || 0}});
        if (!result?.ok || result.session_archives?.version !== 1) throw Error("unconfirmed");
        if (receive(result.session_archives)) changed();
        if (selected === id && !archived) {controller?.abort(); selected = ""; preview.hidden = true;}
      } catch (_) {
        error = "Archive result not confirmed. Refresh to check before retrying; no session was stopped.";
        window.alert(t(error));
      } finally {
        clearTimeout(timeout); busy = false; render();
        // Reconcile the authoritative state even after a lost response, never
        // optimistically hide a pane or blindly repeat the write.
        void refresh();
      }
    }
    async function read(id) {
      controller?.abort(); controller = new AbortController(); const current = controller;
      const timeout = setTimeout(() => current.abort(), 8000);
      selected = id; preview.hidden = false;
      previewTitle.textContent = title(rowFor(id) || {run_id:id});
      output.textContent = ""; evidence.textContent = t("Loading snapshot…");
      try {
        const result = await api(`/api/sessions/${encodeURIComponent(id)}/read?lines=200&position=tail&max_chars=32000`, {signal:current.signal});
        if (current !== controller || !dialog.open) return;
        if (!result?.ok || typeof result.text !== "string") throw Error("unavailable");
        output.textContent = Array.from(result.text).slice(-32000).join("");
        evidence.textContent = [t("Snapshot only, not a complete native conversation"),
          t(result.source === "tmux" ? "Terminal snapshot" : result.source === "log" ? "Saved log" : "unknown"),
          result.observed_at ? new Date(result.observed_at * 1000).toLocaleString(document.documentElement.lang) : t("Snapshot time unknown"),
          t(result.truncated === false ? "Complete requested snapshot" : result.truncated === true ? "Truncated output" : "Truncation unknown")].join(" · ");
      } catch (_) {
        if (current === controller && dialog.open) evidence.textContent = t("Output unavailable");
      } finally {clearTimeout(timeout);}
    }
    function show(id = "", from = trigger) {
      opener = from;
      if (!dialog.open) dialog.showModal(); render();
      if (id && isArchived(id)) void read(id);
    }
    trigger.setAttribute("aria-haspopup", "dialog"); trigger.setAttribute("aria-controls", dialog.id);
    trigger.onclick = () => show(); search.oninput = render;
    dialog.addEventListener("close", () => {controller?.abort(); controller = null; opener?.focus({preventScroll:true});});
    function rememberDraft(id, value) {
      drafts.set(id, value);
      try {sessionStorage.setItem("orch_archived_draft:" + id, value);}
      catch (_) {window.alert(t("Draft kept in this tab only. Browser storage is unavailable; keep this tab open."));}
    }
    function draft(id) {
      let value = drafts.get(id) || "";
      try {value = drafts.has(id) ? value : sessionStorage.getItem("orch_archived_draft:" + id) || "";
        sessionStorage.removeItem("orch_archived_draft:" + id);} catch (_) {}
      drafts.delete(id); return value;
    }
    new MutationObserver(render).observe(document.documentElement, {attributes:true, attributeFilter:["lang"]});
    render();
    return {receive, render, show, change, supported, isArchived, rememberDraft, draft,
      listed: row => !isArchived(row.run_id) && (row.alive || view.entries[row.run_id]?.archived === false),
      get ready() {return available;}};
  }
})();
