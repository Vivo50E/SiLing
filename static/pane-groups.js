/* Project grouping is metadata and a visibility filter, never a terminal lifecycle action. */
(() => {
  const colors = {blue: "#589bf1", teal: "#39b5a4", purple: "#ad87e5", orange: "#dc9744", pink: "#d47ead", gray: "#8b96a4"};
  const palette = [...Object.values(colors), "#ef6464", "#edb84d", "#81bd57", "#39bde0", "#6575df", "#c86bdd"];
  const colorValue = value => /^#[0-9a-f]{6}$/i.test(value || "") ? value.toLowerCase() : colors[value] || colors.blue;
  window.SiLingPaneGroups = ({api, ui, sessions, language, changed, refresh, beforeFilter, arrange}) => {
    const $ = id => document.getElementById(id);
    const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    const t = (en, zh) => language() === "zh" ? zh : en;
    let groups = [], members = {}, available = false, pending = false, filter = "all", storageError = "";
    let editing = "", draftColor = colors.blue, autoLayout = false;
    try { autoLayout = localStorage.getItem("siling_group_auto_layout") === "true"; } catch (_) {}
    try { filter = localStorage.getItem("siling_group_filter") || "all"; } catch (_) {}
    const bar = $("pane-group-bar");
    bar.innerHTML = '<div id="pane-group-tabs" role="group"></div><button id="btn-arrange-groups" type="button"></button><button id="btn-pane-groups"></button><span id="pane-group-status" role="status"></span>';
    const setting = document.createElement("div");
    setting.innerHTML = '<label class="settings-row"><span id="group-auto-layout-label"></span><input id="group-auto-layout" type="checkbox" aria-describedby="group-auto-layout-help"></label><p id="group-auto-layout-help" class="ui-secondary"></p>';
    $("settings-section-appearance").appendChild(setting);
    $("group-auto-layout").checked = autoLayout;
    $("group-auto-layout").addEventListener("change", event => {
      beforeFilter();
      autoLayout = event.target.checked;
      try { localStorage.setItem("siling_group_auto_layout", String(autoLayout)); } catch (_) {}
      applyVisibility();
    });
    $("btn-arrange-groups").addEventListener("click", () => {
      if (!available) return;
      beforeFilter();
      arrange(id => {
        const index = groups.findIndex(group => group.id === members[id]);
        return index < 0 ? groups.length : index;
      });
    });
    const dialog = document.createElement("dialog");
    dialog.id = "pane-groups-dialog";
    dialog.className = "ui-dialog";
    dialog.setAttribute("aria-labelledby", "pane-groups-title");
    dialog.innerHTML = `<div class="modal-head"><h2 id="pane-groups-title"></h2><button data-dialog-close aria-label="Close">×</button></div>
      <div class="modal-body">
        <p id="pane-groups-help" class="ui-secondary"></p>
        <div class="group-workspace">
          <aside class="group-library" aria-labelledby="group-edit-label">
            <h3 id="group-edit-label"></h3><button id="group-new" type="button"></button>
            <div id="group-library-list"></div>
          </aside>
          <form id="pane-group-form">
            <div class="group-editor-heading"><h3 id="group-editor-title"></h3><span id="group-preview" class="group-preview"><i class="group-dot" aria-hidden="true"></i><span></span></span></div>
            <label><span id="group-name-label"></span><input id="group-name" maxlength="64" required autocomplete="off"></label>
            <fieldset class="group-colors"><legend id="group-color-label"></legend><div id="group-palette"></div>
              <div class="group-custom-color">
                <label><span id="group-picker-label"></span><input id="group-color" type="color" value="#589bf1"></label>
                <label><span id="group-hex-label">HEX</span><input id="group-hex" type="text" value="#589bf1" pattern="#[0-9a-fA-F]{6}" maxlength="7" required spellcheck="false" autocomplete="off" aria-describedby="group-color-help"></label>
              </div><p id="group-color-help" class="ui-secondary"></p>
            </fieldset>
            <div class="group-editor-actions"><button id="group-save" type="submit"></button><button id="group-delete" type="button" class="danger"></button></div>
          </form>
        </div>
        <details class="group-assignment">
          <summary class="group-assignment-heading" tabindex="0"><h3 id="group-bulk-title"></h3><span id="group-selected-count" role="status"></span></summary>
          <div class="group-selection-tools"><button id="group-select-all" type="button"></button><button id="group-select-none" type="button"></button></div>
          <div id="group-session-list"></div>
          <div class="group-assignment-actions"><label><span id="group-target-label"></span><select id="group-target"></select></label><span id="group-target-dot" class="group-dot" aria-hidden="true"></span><button id="group-assign"></button></div>
        </details>
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
        return `<button data-group-filter="${esc(g.id)}" aria-pressed="${filter === g.id}" ${!available ? "disabled" : ""} title="${esc(g.name)}" style="--group-color:${g.color ? colorValue(g.color) : "transparent"}">${g.color ? '<i class="group-dot" aria-hidden="true"></i>' : ""}${esc(g.name)} <span>${count}</span></button>`;
      }).join("");
      if ($("pane-group-tabs").innerHTML !== markup) {
        const focused = document.activeElement?.dataset.groupFilter;
        $("pane-group-tabs").innerHTML = markup;
        if (focused) [...$("pane-group-tabs").children].find(b => b.dataset.groupFilter === focused)?.focus();
      }
      $("btn-arrange-groups").textContent = t("Arrange by group", "按分组整理");
      $("btn-arrange-groups").disabled = !available;
      $("btn-arrange-groups").title = t("Group open panes in tab order; ungrouped panes last", "按分组标签顺序排列已打开的面板，未分组放最后");
      $("group-auto-layout-label").textContent = t("Fit layout when entering a group", "进入分组时自动调整布局");
      $("group-auto-layout-help").textContent = t("Size the desktop grid to open panes in the selected group. All restores your original layout. Saved in this browser.", "按所选分组已打开的面板数量调整桌面网格；回到全部恢复原布局。仅保存在当前浏览器。");
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
        "pane-groups-help": t("Names, colors and membership sync between your devices connected to this Dashboard. Your layout stays on this device. Agents keep running.", "名称、颜色和归属会同步到连接此 Dashboard 的电脑与手机；当前布局留在本设备，Agent 始终继续运行。"),
        "group-edit-label": t("Your groups", "我的分组"), "group-name-label": t("Group name", "分组名称"),
        "group-new": t("+ New group", "+ 新建分组"), "group-picker-label": t("Custom color", "自定义颜色"),
        "group-color-help": t("Pick a swatch, choose any color, or enter #RRGGBB. Preview updates immediately; Save applies it.", "可点选色块、自由取色或输入 #RRGGBB。预览即时更新，保存后才会应用。"),
        "group-select-all": t("Select all", "全选"), "group-select-none": t("Clear", "清空选择"),
        "group-color-label": t("Color", "标识色"), "group-save": t("Save group", "保存分组"),
        "group-delete": t("Delete group", "删除分组"), "group-bulk-title": t("Assign sessions", "批量归组"),
        "group-target-label": t("Move selected sessions to", "将选中会话移到"), "group-assign": t("Apply to selected", "应用到选中会话"),
      };
      for (const [id, value] of Object.entries(labels)) $(id).textContent = value;
      if (editing && !groups.some(g => g.id === editing)) editing = "";
      renderLibrary();
      $("group-palette").innerHTML = palette.map(color => `<button type="button" class="group-swatch" data-color="${color}" style="--group-color:${color}" aria-label="${esc(t("Choose color ", "选择颜色 ") + color)}" title="${color}" aria-pressed="false"><i aria-hidden="true"></i></button>`).join("");
      editSelection();
      $("group-target").innerHTML = options(t("Ungrouped", "未分组"), editing);
      updateTargetColor();
      $("group-session-list").innerHTML = sessions().filter(s => s.alive).map(s =>
        `<label><input type="checkbox" value="${esc(s.run_id)}"><span>${esc(s.display_name || s.task || s.run_id)} <small><i class="group-dot" aria-hidden="true" style="--group-color:${groupFor(s.run_id) ? colorValue(groupFor(s.run_id).color) : "transparent"}"></i>${esc(groupFor(s.run_id)?.name || t("Ungrouped", "未分组"))}</small></span></label>`
      ).join("") || esc(t("No live sessions", "暂无运行中的会话"));
      updateSelectedCount();
    }
    function renderLibrary() {
      $("group-library-list").innerHTML = groups.map(g => `<button type="button" data-edit-group="${esc(g.id)}" aria-pressed="${editing === g.id}" style="--group-color:${colorValue(g.color)}"><i class="group-dot" aria-hidden="true"></i><span>${esc(g.name)}</span><small>${sessions().filter(s => s.alive && members[s.run_id] === g.id).length}</small></button>`).join("") || `<p class="ui-secondary">${esc(t("Create a group to organize related panes.", "新建分组，把相关面板放在一起。"))}</p>`;
      $("group-new").setAttribute("aria-pressed", String(!editing));
    }
    function updatePreview() {
      $("group-preview").style.setProperty("--group-color", draftColor);
      $("group-preview").querySelector("span").textContent = $("group-name").value.trim() || t("Group preview", "分组预览");
      $("group-color").value = draftColor;
      $("group-palette").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.color === draftColor)));
    }
    function chooseColor(value) {
      draftColor = colorValue(value);
      $("group-hex").value = draftColor;
      $("group-hex").setCustomValidity("");
      updatePreview();
    }
    function updateTargetColor() {
      const group = groups.find(g => g.id === $("group-target").value);
      $("group-target-dot").style.setProperty("--group-color", group ? colorValue(group.color) : "transparent");
    }
    function updateSelectedCount() {
      const count = $("group-session-list").querySelectorAll("input:checked").length;
      $("group-selected-count").textContent = t(`${count} selected`, `已选 ${count} 个`);
      $("group-assign").disabled = pending || count === 0;
    }
    function editSelection() {
      const group = groups.find(g => g.id === editing);
      $("group-name").value = group?.name || "";
      chooseColor(group?.color || "blue");
      $("group-editor-title").textContent = group ? t("Edit group", "编辑分组") : t("New group", "新建分组");
      $("group-save").textContent = group ? t("Save changes", "保存修改") : t("Create group", "创建分组");
      $("group-delete").disabled = !group;
      $("group-delete").hidden = !group;
    }
    ui.wireDialog(dialog, $("btn-pane-groups"), () => { populateDialog(); $("group-result").textContent = ""; });
    $("group-library-list").addEventListener("click", event => {
      const button = event.target.closest("[data-edit-group]");
      if (!button || pending) return;
      editing = button.dataset.editGroup; renderLibrary(); editSelection();
      $("group-target").value = editing; updateTargetColor();
      $("group-name").focus();
    });
    $("group-new").addEventListener("click", () => {
      editing = ""; renderLibrary(); editSelection(); $("group-name").focus();
    });
    $("group-name").addEventListener("input", updatePreview);
    $("group-color").addEventListener("input", event => chooseColor(event.target.value));
    $("group-hex").addEventListener("input", event => {
      const value = event.target.value;
      const valid = /^#[0-9a-f]{6}$/i.test(value);
      event.target.setCustomValidity(valid ? "" : t("Enter a color as #RRGGBB", "请输入 #RRGGBB 格式的颜色"));
      if (valid) { draftColor = value.toLowerCase(); updatePreview(); }
    });
    $("group-palette").addEventListener("click", event => {
      const button = event.target.closest("[data-color]");
      if (button) chooseColor(button.dataset.color);
    });
    $("group-target").addEventListener("change", updateTargetColor);
    $("group-session-list").addEventListener("change", updateSelectedCount);
    for (const [id, checked] of [["group-select-all", true], ["group-select-none", false]]) {
      $(id).addEventListener("click", () => {
        $("group-session-list").querySelectorAll("input").forEach(input => { input.checked = checked; });
        updateSelectedCount();
      });
    }

    async function save(body, result) {
      if (pending) return false;
      pending = true;
      dialog.querySelectorAll("button:not([data-dialog-close]), input, select").forEach(e => { e.disabled = true; });
      result.textContent = t("Saving…", "保存中…");
      try {
        await api("/api/pane-groups", {method:"POST", body});
        const refreshed = await refresh();
        if (body.action === "create") editing = groups.find(g => g.name === body.name.trim())?.id || "";
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
        $("group-delete").disabled = !editing;
        updateSelectedCount();
      }
    }
    $("pane-group-form").addEventListener("submit", e => {
      e.preventDefault();
      if (!$("pane-group-form").reportValidity()) return;
      save({action:editing ? "update" : "create", group_id:editing, name:$("group-name").value, color:draftColor}, $("group-result"));
    });
    $("group-delete").addEventListener("click", () => {
      if (confirm(t("Delete this group? Sessions will become ungrouped and keep running.", "删除此分组？会话将变为未分组并继续运行。"))) {
        save({action:"delete", group_id:editing}, $("group-result"));
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
      badge.style.setProperty("--group-color", group ? colorValue(group.color) : "transparent");
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
      const count = cards.filter(card => card.dataset.runId && !card.classList.contains("group-hidden")).length;
      const fit = autoLayout && available && filter !== "all" && count > 0;
      const grid = $("grid");
      if (fit) {
        const sizes = [[1,1],[2,1],[3,1],[2,2],[3,2],[4,2],[3,3],[4,3],[5,3],[4,4]];
        const [cols, rows] = sizes.find(([c,r]) => c*r >= count) || [4, Math.ceil(count/4)];
        grid.style.setProperty("--group-cols", cols);
        grid.style.setProperty("--group-rows", rows);
      }
      grid.classList.toggle("group-auto-layout", fit);
      document.querySelectorAll("#pane-nav-rail [data-slot]").forEach(dot => {
        const card = cards.find(c => c.dataset.slot === dot.dataset.slot);
        dot.hidden = !!card?.classList.contains("group-hidden");
      });
      const empty = available && filter !== "all" && !cards.some(c => c.dataset.runId && !c.classList.contains("group-hidden"));
      $("pane-group-status").textContent = storageError || (empty ? t("No open panes in this group — open a session from the list.", "此分组暂无打开的面板，可从会话列表打开。") : "");
    }
    renderBar();
    return {
      matches, decorate, applyVisibility, refreshLabels: renderBar,
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
