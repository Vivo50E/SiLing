/* Cached host observations only: never attach, send input or control sessions. */
(() => {
  "use strict";
  window.SilingResources = {create};
  function create({trigger, mobileTrigger, summary, returnFocus, api, ui}) {
    const t = (...args) => ui.message(...args);
    const node = (tag, parent, text) => {
      const el = document.createElement(tag);
      if (text) el.textContent = text;
      parent.append(el); return el;
    };
    const dialog = node("dialog", document.body);
    dialog.id = "resource-dialog"; dialog.className = "ui-dialog";
    dialog.setAttribute("aria-labelledby", "resource-title");
    const head = node("div", dialog); head.className = "modal-head";
    const title = node("h2", head); title.id = "resource-title";
    const close = node("button", head, "×"); close.dataset.dialogClose = "";
    const body = node("div", dialog); body.className = "modal-body";
    const host = node("p", body); host.id = "resource-host";
    const notice = node("p", body); notice.id = "resource-notice"; notice.setAttribute("role", "status");
    const grid = node("div", body); grid.className = "resource-grid";
    const fields = [
      ["cpu", "CPU — all cores, 0–100%"], ["memory", "Memory — available / total"],
      ["swap", "Swap — used / total"], ["outputs_disk", "Output volume — free / total"],
      ["projects_disk", "Project volume — free / total"],
    ].map(([key, label]) => {
      const card = node("section", grid); card.dataset.metric = key;
      return {key, label, card, title:node("h3", card), value:node("strong", card), meta:node("p", card)};
    });
    const help = node("p", body); help.className = "resource-help";
    const refresh = node("button", body); refresh.id = "resource-refresh";
    const heading = node("span", summary); heading.className = "resource-summary-heading";
    const summaryTitle = node("strong", heading);
    const summaryStatus = node("small", heading);
    const indicator = node("span", summary, "!"); indicator.className = "resource-summary-indicator";
    indicator.setAttribute("aria-hidden", "true");
    const miniFields = [
      ["cpu", "CPU"], ["memory", "Mem"], ["outputs_disk", "Disk"],
    ].map(([key, label]) => {
      const card = node("span", summary); card.className = "resource-mini"; card.dataset.summaryMetric = key;
      const ring = node("span", card); ring.className = "resource-ring"; ring.setAttribute("aria-hidden", "true");
      const copy = node("span", card); copy.className = "resource-mini-copy";
      const name = node("span", copy); name.className = "resource-mini-label";
      return {key, label, card, name, value:node("strong", copy), ring};
    });
    const arrow = node("span", summary, "›"); arrow.className = "resource-summary-arrow"; arrow.setAttribute("aria-hidden", "true");
    let last = null, receivedWall = 0, receivedMono = 0, failed = false;
    let controller = null, generation = 0, pollTimer = null, renderTimer = null;
    let opener = returnFocus || trigger;
    const bytes = value => {
      if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
      const units = ["B", "KiB", "MiB", "GiB", "TiB"];
      let i = 0; while (value >= 1024 && i < units.length - 1) {value /= 1024; i++;}
      return value.toLocaleString(document.documentElement.lang, {maximumFractionDigits:1}) + " " + units[i];
    };
    function percentage(key, value) {
      if (!value) return null;
      let percent = value.percent;
      if (key !== "cpu") {
        const total = value.total_bytes, free = key === "memory" ? value.available_bytes : value.free_bytes;
        if (!Number.isFinite(total) || total <= 0 || !Number.isFinite(free) || free < 0 || free > total) return null;
        percent = 100 * (total - free) / total;
      }
      return Number.isFinite(percent) && percent >= 0 && percent <= 100 ? percent : null;
    }
    function render() {
      title.textContent = t("Host resources"); close.setAttribute("aria-label", t("Close"));
      refresh.textContent = t("Refresh snapshot"); refresh.disabled = !!controller;
      host.textContent = t("Dashboard host: {host}", {host:last?.host || t("unknown")});
      const metrics = Object.values(last?.metrics || {});
      const missingDependency = metrics.some(metric => metric?.error === "dependency_missing");
      const collectionFailed = metrics.some(metric => metric?.error && !["pending", "warming_up"].includes(metric.error));
      notice.textContent = last?.enabled === false ? t("Resource monitoring disabled on the server")
        : failed ? t("Resource request failed — previous values are not live")
        : missingDependency ? t("Resource collector needs psutil. Install requirements.txt in the Dashboard's Python environment; collection retries automatically.")
        : collectionFailed ? t("Some resource metrics could not be collected — see the reason below")
        : !last ? t("Loading snapshot…") : t("Read-only · sampled every 5 seconds");
      help.textContent = t("This Dashboard host only, not your phone or remote nodes. Native memory pressure is unavailable; available memory and nonzero swap are not pressure verdicts. No alerts or automatic session controls. Archiving does not free running agents.");
      const elapsed = Math.max(0, (Date.now() - receivedWall) / 1000,
        (performance.now() - receivedMono) / 1000);
      for (const field of fields) {
        field.title.textContent = t(field.label);
        const metric = last?.metrics?.[field.key];
        const value = metric?.value;
        const age = typeof metric?.age_s === "number" ? metric.age_s + elapsed : null;
        const state = last?.enabled === false ? "disabled"
          : age !== null && age >= 15 ? "stale"
          : failed ? "unavailable" : metric?.status || "unknown";
        field.card.dataset.status = state;
        field.value.textContent = !value ? "—" : field.key === "cpu"
          ? (typeof value.percent === "number" ? value.percent.toLocaleString(document.documentElement.lang) + "%" : "—")
          : bytes(value.available_bytes ?? value.used_bytes ?? value.free_bytes) + " / " + bytes(value.total_bytes);
        const labels = {fresh:"Observed", stale:"Stale", unavailable:"Metric unavailable", unknown:"unknown", disabled:"Disabled"};
        const when = Number(metric?.observed_at);
        const time = when > 0 ? new Date(when * 1000).toLocaleTimeString(document.documentElement.lang) : "—";
        const reasons = {timeout:"Collection timed out", warming_up:"Waiting for two CPU samples",
          dependency_missing:"Missing dependency: psutil",
          dependency_unavailable:"Cannot load psutil — repair the Dashboard's Python environment",
          path_missing:"Configured directory does not exist",
          permission_denied:"Permission denied while collecting this metric",
          unavailable:"Collection failed"};
        const reason = Object.hasOwn(reasons, metric?.error) ? t(reasons[metric.error]) : "";
        field.meta.textContent = [t(labels[state] || "unknown"), time, metric?.source || "", reason].filter(Boolean).join(" · ");
      }
      const state = last?.enabled === false ? "disabled" : failed ? "unavailable"
        : fields.some(field => field.card.dataset.status === "stale") ? "stale"
        : fields.some(field => field.card.dataset.status !== "fresh") ? "partial" : "fresh";
      summary.dataset.status = state;
      indicator.textContent = state === "disabled" ? "–" : "!";
      summaryTitle.textContent = t("Host resources");
      const statusLabel = {disabled:"Disabled", unavailable:"Resource request failed", stale:"Stale",
        partial:last ? "Partial data" : "Loading snapshot…", fresh:"Every 5s"}[state];
      // Keep freshness visible even when a long hostname is ellipsized on phones.
      summaryStatus.textContent = [t(statusLabel), last?.host].filter(Boolean).join(" · ");
      for (const mini of miniFields) {
        const detail = fields.find(field => field.key === mini.key);
        const percent = percentage(mini.key, last?.metrics?.[mini.key]?.value);
        mini.card.dataset.status = detail.card.dataset.status;
        mini.name.textContent = t(mini.label);
        mini.value.textContent = percent === null || state === "disabled" ? "—"
          : percent.toLocaleString(document.documentElement.lang, {maximumFractionDigits:1}) + "%";
        mini.ring.style.setProperty("--resource-fill", `${percent ?? 0}%`);
        mini.card.title = [detail.title.textContent, detail.value.textContent, detail.meta.textContent].join(" · ");
      }
      summary.title = [host.textContent, t(statusLabel), notice.textContent, t("Memory used = total − available. Disk usage is for the output volume."), t("Open resource details")].join("\n");
      summary.setAttribute("aria-label", [host.textContent, t(statusLabel),
        ...miniFields.map(field => `${t(field.label)} ${field.value.textContent}`), t("Open resource details")].join(" · "));
    }
    async function poll() {
      if (document.hidden || controller) return;
      clearTimeout(pollTimer);
      const current = ++generation;
      const requestController = new AbortController();
      controller = requestController;
      const timeout = setTimeout(() => requestController.abort(), 4000);
      render();
      try {
        const value = await api("/api/resources", {signal:requestController.signal, cache:"no-store", promptForToken:false});
        if (current !== generation) return;
        if (value?.schema_version !== 1 || value.scope !== "dashboard_host" || !value.metrics) throw Error("Unsupported resource response");
        last = value; receivedWall = Date.now(); receivedMono = performance.now(); failed = false;
      } catch (_) {
        if (current === generation) failed = true;
      } finally {
        clearTimeout(timeout);
        if (current === generation) {
          controller = null; render();
          if (!document.hidden) pollTimer = setTimeout(poll, 5000);
        }
      }
    }
    function cancel() {
      generation++; controller?.abort(); controller = null;
      clearTimeout(pollTimer); clearInterval(renderTimer);
    }
    ui.wireDialog(dialog, trigger, render);
    function start() {void poll(); clearInterval(renderTimer); renderTimer = setInterval(render, 1000);}
    trigger.addEventListener("click", () => {opener = returnFocus || trigger; start();});
    for (const button of [mobileTrigger, summary]) {
      button.setAttribute("aria-haspopup", "dialog");
      button.setAttribute("aria-controls", dialog.id);
      button.setAttribute("aria-expanded", "false");
      button.addEventListener("click", () => {
        opener = button; render(); dialog.showModal();
        button.setAttribute("aria-expanded", "true"); start();
      });
    }
    dialog.addEventListener("close", () => {
      // The visible summary owns the same loop; closing details must not stop it.
      mobileTrigger.setAttribute("aria-expanded", "false"); summary.setAttribute("aria-expanded", "false");
      const target = opener.getClientRects().length ? opener
        : mobileTrigger.getClientRects().length ? mobileTrigger : returnFocus;
      target?.focus({preventScroll:true});
    });
    refresh.addEventListener("click", () => void poll());
    document.addEventListener("visibilitychange", () => {
      cancel();
      if (!document.hidden) start();
    });
    render();
    if (!document.hidden) start();
    return {render};
  }
})();
