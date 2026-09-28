/* Project grouping is metadata and a visibility filter, never a terminal lifecycle action. */
(() => {
  const colors = {blue: "#589bf1", teal: "#39b5a4", purple: "#ad87e5", orange: "#dc9744", pink: "#d47ead", gray: "#8b96a4"};
  window.SiLingPaneGroups = ({api, ui, sessions, language, changed, refresh, beforeFilter}) => {
    const $ = id => document.getElementById(id);
    const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    const t = (en, zh) => language() === "zh" ? zh : en;
    let groups = [], members = {}, available = false, pending = false, filter = "all", storageError = "";
    try { filter = localStorage.getItem("siling_group_filter") || "all"; } catch (_) {}
    const bar = $("pane-group-bar");
    bar.innerHTML = '<div id="pane-group-tabs" role="group"></div><button id="btn-pane-groups"></button><span id="pane-group-status" role="status"></span>';
    const dialog = document.createElement("dialog");
    dialog.id = "pane-groups-dialog";
    dialog.className = "ui-dialog";
    dialog.setAttribute("aria-labelledby", "pane-groups-title");
    dialog.innerHTML = `<div class="modal-head"><h2 id="pane-groups-title"></h2><button data-dialog-close aria-label="Close">×</button></div>
      <div class="modal-body">
        <p id="pane-groups-help" class="ui-secondary"></p>
        <form id="pane-group-form" class="ui-menu-group">
          <label><span id="group-edit-label"></span><select id="group-edit"></select></label>
          <label><span id="group-name-label"></span><input id="group-name" maxlength="64" required></label>
          <label><span id="group-color-label"></span><select id="group-color"></select></label>
          <button id="group-save" type="submit"></button><button id="group-delete" type="button" class="danger"></button>
        </form>
        <div class="ui-menu-group">
          <h3 id="group-bulk-title"></h3>
          <div id="group-session-list"></div>
          <label><span id="group-target-label"></span><select id="group-target"></select></label>
          <button id="group-assign"></button>
        </div>
        <p id="group-result" role="status" aria-live="polite"></p>
      </div>`;
    document.body.appendChild(dialog);
    const groupFor = id => groups.find(g => g.id === members[id]);
    const matches = row => !available || filter === "all" || (members[row?.run_id] || "") === (filter === "ungrouped" ? "" : filter);
    const options = (first, value = "") => `<option value="">${esc(first)}</option>` + groups.map(g => `<option value="${esc(g.id)}" ${g.id === value ? "selected" : ""}>${esc(g.name)}</option>`).join("");

    function selectFilter(value) {
      beforeFilter();
      filter = value;
      try { localStorage.setItem("siling_group_filter", value); } catch (_) {}
      renderBar();
      changed();
    }
    function renderBar() {
      const live = sessions().filter(s => s.alive);
      $("pane-group-tabs").setAttribute("aria-label", t("Filter by project group", "按项目分组筛选"));
      const entries = [{id:"all", name:t("All", "全部")}, {id:"ungrouped", name:t("Ungrouped", "未分组")}, ...groups];
      // Updating counts must not remove a keyboard user's focused tab on every poll.
      const markup = entries.map(g => {
        const count = live.filter(s => g.id === "all" || (members[s.run_id] || "") === (g.id === "ungrouped" ? "" : g.id)).length;
        return `<button data-group-filter="${esc(g.id)}" aria-pressed="${filter === g.id}" ${!available ? "disabled" : ""} title="${esc(g.name)}" style="--group-color:${colors[g.color] || "transparent"}">${esc(g.name)} <span>${count}</span></button>`;
      }).join("");
      if ($("pane-group-tabs").innerHTML !== markup) {
        const focused = document.activeElement?.dataset.groupFilter;
        $("pane-group-tabs").innerHTML = markup;
        if (focused) [...$("pane-group-tabs").children].find(b => b.dataset.groupFilter === focused)?.focus();
      }
      $("btn-pane-groups").textContent = t("Manage groups", "管理分组");
      $("btn-pane-groups").disabled = !available;
    }
    $("pane-group-tabs").addEventListener("click", e => {
      const button = e.target.closest("[data-group-filter]");
      if (button) selectFilter(button.dataset.groupFilter);
    });

    function populateDialog() {
      const labels = {
        "pane-groups-title": t("Project groups", "项目分组"),
        "pane-groups-help": t("Groups are shared by devices using this Dashboard. Filtering only hides panes; agents keep running. Deleting a group never stops its sessions.", "分组由连接此 Dashboard 的设备共享。筛选只隐藏面板，Agent 继续运行；删除分组不会停止会话。"),
        "group-edit-label": t("Edit group", "编辑分组"), "group-name-label": t("Name", "名称"),
        "group-color-label": t("Color", "标识色"), "group-save": t("Save group", "保存分组"),
        "group-delete": t("Delete group", "删除分组"), "group-bulk-title": t("Assign sessions", "批量归组"),
        "group-target-label": t("Move selected sessions to", "将选中会话移到"), "group-assign": t("Apply to selected", "应用到选中会话"),
      };
      for (const [id, value] of Object.entries(labels)) $(id).textContent = value;
      const selected = $("group-edit").value;
      $("group-edit").innerHTML = options(t("+ New group", "+ 新建分组"), selected);
      $("group-color").innerHTML = Object.keys(colors).map((c, i) => `<option value="${c}">${language() === "zh" ? ["蓝色","青色","紫色","橙色","粉色","灰色"][i] : c}</option>`).join("");
      editSelection();
      $("group-target").innerHTML = options(t("Ungrouped", "未分组"), selected);
      $("group-session-list").innerHTML = sessions().filter(s => s.alive).map(s =>
        `<label><input type="checkbox" value="${esc(s.run_id)}"><span>${esc(s.display_name || s.task || s.run_id)} <small>${esc(groupFor(s.run_id)?.name || t("Ungrouped", "未分组"))}</small></span></label>`
      ).join("") || esc(t("No live sessions", "暂无运行中的会话"));
    }
    function editSelection() {
      const group = groups.find(g => g.id === $("group-edit").value);
      $("group-name").value = group?.name || "";
      $("group-color").value = group?.color || "blue";
      $("group-delete").disabled = !group;
    }
    ui.wireDialog(dialog, $("btn-pane-groups"), () => { populateDialog(); $("group-result").textContent = ""; });
    $("group-edit").addEventListener("change", editSelection);

    async function save(body, result) {
      if (pending) return false;
      pending = true;
      dialog.querySelectorAll("button:not([data-dialog-close]), input, select").forEach(e => { e.disabled = true; });
      result.textContent = t("Saving…", "保存中…");
      try {
        await api("/api/pane-groups", {method:"POST", body});
        const refreshed = await refresh();
        if (dialog.open) populateDialog();
        result.textContent = refreshed && available ? t("Saved", "已保存")
          : t("Saved; view refresh failed. Refresh before editing again.", "已保存，但视图刷新失败。请刷新后再编辑。");
        return true;
      } catch (error) {
        result.textContent = t("Save failed or not confirmed: ", "保存失败或结果未确认：") + error.message;
        return false;
      } finally {
        pending = false;
        document.querySelectorAll("#grid .pane-card[data-run-id]").forEach(card => {
          const row = sessions().find(s => s.run_id === card.dataset.runId);
          if (row) decorate(card, row);
        });
        dialog.querySelectorAll("button, input, select").forEach(e => { e.disabled = false; });
        $("group-delete").disabled = !$("group-edit").value;
      }
    }
    $("pane-group-form").addEventListener("submit", e => {
      e.preventDefault();
      save({action:$("group-edit").value ? "update" : "create", group_id:$("group-edit").value, name:$("group-name").value, color:$("group-color").value}, $("group-result"));
    });
    $("group-delete").addEventListener("click", () => {
      if (confirm(t("Delete this group? Sessions will become ungrouped and keep running.", "删除此分组？会话将变为未分组并继续运行。"))) {
        save({action:"delete", group_id:$("group-edit").value}, $("group-result"));
      }
    });
    $("group-assign").addEventListener("click", () => {
      const ids = [...$("group-session-list").querySelectorAll("input:checked")].map(e => e.value);
      if (!ids.length) { $("group-result").textContent = t("Select at least one session.", "请至少选择一个会话。"); return; }
      save({action:"assign", group_id:$("group-target").value, run_ids:ids}, $("group-result"));
    });

    function decorate(card, row) {
      const group = groupFor(row.run_id);
      let badge = card.querySelector(".pane-group-badge");
      if (!badge) {
        badge = document.createElement("span"); badge.className = "pane-group-badge";
        card.querySelector(".pane-drag-region .title").after(badge);
      }
      badge.textContent = group?.name || "";
      badge.title = group?.name || "";
      badge.hidden = !group;
      badge.style.setProperty("--group-color", colors[group?.color] || "transparent");
      let label = card.querySelector(".pane-group-control");
      if (!label) {
        label = document.createElement("label"); label.className = "pane-group-control";
        label.innerHTML = '<span></span><select class="pane-group-select"></select><small role="status"></small>';
        card.querySelector(".pane-menu .ui-menu-group").prepend(label);
        label.querySelector("select").addEventListener("change", async e => {
          const value = e.target.value;
          e.target.disabled = true;
          const ok = await save({action:"assign", group_id:value, run_ids:[row.run_id]}, label.querySelector("small"));
          if (!ok) e.target.value = members[row.run_id] || "";
          e.target.disabled = !available;
        });
      }
      label.querySelector("span").textContent = t("Project group", "项目分组");
      const select = label.querySelector("select");
      if (document.activeElement !== select && !pending) {
        select.innerHTML = options(t("Ungrouped", "未分组"), members[row.run_id]);
        select.disabled = !available;
      }
    }

    function applyVisibility() {
      const cards = [...$("grid").querySelectorAll(".pane-card:not(.cached-pane)")];
      for (const card of cards) {
        const id = card.dataset.runId;
        const hide = available && filter !== "all" && (!id || !matches({run_id:id}));
        if (hide && !card.classList.contains("group-hidden")) {
          if (card.classList.contains("zoomed-pane")) beforeFilter();
          const rect = card.getBoundingClientRect();
          card.style.setProperty("--group-width", `${rect.width}px`);
          card.style.setProperty("--group-height", `${rect.height}px`);
          card.querySelectorAll("dialog[open]").forEach(d => d.close());
          if (card.contains(document.activeElement)) $("btn-pane-groups").focus();
        }
        card.classList.toggle("group-hidden", hide);
        card.inert = hide;
        if (hide) card.setAttribute("aria-hidden", "true"); else card.removeAttribute("aria-hidden");
      }
      document.querySelectorAll("#pane-nav-rail [data-slot]").forEach(dot => {
        const card = cards.find(c => c.dataset.slot === dot.dataset.slot);
        dot.hidden = !!card?.classList.contains("group-hidden");
      });
      const empty = available && filter !== "all" && !cards.some(c => c.dataset.runId && !c.classList.contains("group-hidden"));
      $("pane-group-status").textContent = storageError || (empty ? t("No open panes in this group — open a session from the list.", "此分组暂无打开的面板，可从会话列表打开。") : "");
    }
    renderBar();
    return {
      matches, decorate, applyVisibility,
      reveal(runId) {
        if (!matches({run_id:runId})) selectFilter("all");
      },
      receive(data) {
        available = !!data && Array.isArray(data.groups) && !!data.members && !data.error;
        if (available) {
          groups = data.groups; members = data.members;
          if (filter !== "all" && filter !== "ungrouped" && !groups.some(g => g.id === filter)) selectFilter("all");
        }
        renderBar();
        storageError = data?.error || (!available ? t("Groups unavailable", "分组暂不可用") : "");
        $("pane-group-status").textContent = storageError;
      },
    };
  };
})();
