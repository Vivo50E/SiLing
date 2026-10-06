/* Cached host observations only: never attach, send input or control sessions. */
(() => {
  "use strict";
  window.SilingResources = {create};
  function create({trigger, mobileTrigger, returnFocus, api, ui}) {
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
    let last = null, receivedWall = 0, receivedMono = 0, failed = false;
    let controller = null, generation = 0, pollTimer = null, renderTimer = null;
    let opener = returnFocus || trigger;
    const bytes = value => {
      if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
      const units = ["B", "KiB", "MiB", "GiB", "TiB"];
      let i = 0; while (value >= 1024 && i < units.length - 1) {value /= 1024; i++;}
      return value.toLocaleString(document.documentElement.lang, {maximumFractionDigits:1}) + " " + units[i];
    };
    function render() {
      title.textContent = t("Host resources"); close.setAttribute("aria-label", t("Close"));
      refresh.textContent = t("Refresh snapshot"); refresh.disabled = !!controller;
      host.textContent = t("Dashboard host: {host}", {host:last?.host || t("unknown")});
      notice.textContent = last?.enabled === false ? t("Resource monitoring disabled on the server")
        : failed ? t("Resource request failed — previous values are not live")
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
        const reason = metric?.error === "timeout" ? t("Collection timed out")
          : metric?.error === "warming_up" ? t("Waiting for two CPU samples") : "";
        field.meta.textContent = [t(labels[state] || "unknown"), time, metric?.source || "", reason].filter(Boolean).join(" · ");
      }
    }
    async function poll() {
      if (!dialog.open || document.hidden || controller) return;
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
          if (dialog.open && !document.hidden) pollTimer = setTimeout(poll, 5000);
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
    mobileTrigger.setAttribute("aria-haspopup", "dialog");
    mobileTrigger.setAttribute("aria-controls", dialog.id);
    mobileTrigger.setAttribute("aria-expanded", "false");
    mobileTrigger.addEventListener("click", () => {
      opener = mobileTrigger; render(); dialog.showModal();
      mobileTrigger.setAttribute("aria-expanded", "true"); start();
    });
    dialog.addEventListener("close", () => {
      cancel(); mobileTrigger.setAttribute("aria-expanded", "false");
      const target = opener.getClientRects().length ? opener
        : mobileTrigger.getClientRects().length ? mobileTrigger : returnFocus;
      target?.focus({preventScroll:true});
    });
    refresh.addEventListener("click", () => void poll());
    document.addEventListener("visibilitychange", () => {
      cancel();
      if (dialog.open && !document.hidden) {render(); void poll(); renderTimer = setInterval(render, 1000);}
    });
    return {render};
  }
})();
