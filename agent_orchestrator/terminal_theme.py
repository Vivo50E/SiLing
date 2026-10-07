"""Terminal theme normalization and ttyd HTML patching."""

from __future__ import annotations

import json
import os


_TTYD_SOFT_DARK_THEME = {
    "background": "#1f242c",
    "foreground": "#d6deeb",
    "cursor": "#f0f6fc",
    "cursorAccent": "#1f242c",
    "selectionBackground": "#3b4252",
    "black": "#1f242c",
    "red": "#ff7b72",
    "green": "#7ee787",
    "yellow": "#d29922",
    "blue": "#79c0ff",
    "magenta": "#d2a8ff",
    "cyan": "#56d4dd",
    "white": "#d6deeb",
    "brightBlack": "#8b949e",
    "brightRed": "#ffa198",
    "brightGreen": "#aff5b4",
    "brightYellow": "#e3b341",
    "brightBlue": "#a5d6ff",
    "brightMagenta": "#d8b9ff",
    "brightCyan": "#7ee0e8",
    "brightWhite": "#f0f6fc",
}
_TTYD_SOFT_LIGHT_THEME = {
    "background": "#e8eef6",
    "foreground": "#1f2937",
    "cursor": "#1f2937",
    "cursorAccent": "#e8eef6",
    "selectionBackground": "#cbd5e1",
    "black": "#1f2937",
    "red": "#cf222e",
    "green": "#116329",
    "yellow": "#953800",
    "blue": "#0969da",
    "magenta": "#8250df",
    "cyan": "#1b7c83",
    "white": "#dbe3ee",
    "brightBlack": "#475569",
    "brightRed": "#a40e26",
    "brightGreen": "#1a7f37",
    "brightYellow": "#9a6700",
    "brightBlue": "#218bff",
    "brightMagenta": "#a475f9",
    "brightCyan": "#3192aa",
    "brightWhite": "#f8fafc",
}
_TTYD_SOFT_GREEN_THEME = {
    "background": "#eef7ee",
    "foreground": "#1f2f24",
    "cursor": "#1f2f24",
    "cursorAccent": "#eef7ee",
    "selectionBackground": "#cfe8d0",
    "black": "#1f2f24",
    "red": "#b3261e",
    "green": "#137333",
    "yellow": "#8a5a00",
    "blue": "#1769aa",
    "magenta": "#7a4fb3",
    "cyan": "#1b7f73",
    "white": "#dceadf",
    "brightBlack": "#5f7165",
    "brightRed": "#d93025",
    "brightGreen": "#188038",
    "brightYellow": "#9a6700",
    "brightBlue": "#1a73e8",
    "brightMagenta": "#9334e6",
    "brightCyan": "#129e8f",
    "brightWhite": "#fbfff9",
}
_TTYD_LIGHT_THEME = {
    "background": "#ffffff",
    "foreground": "#111827",
    "cursor": "#111827",
    "cursorAccent": "#ffffff",
    "selectionBackground": "#bfdbfe",
    "black": "#111827",
    "red": "#b91c1c",
    "green": "#15803d",
    "yellow": "#a16207",
    "blue": "#1d4ed8",
    "magenta": "#7e22ce",
    "cyan": "#0e7490",
    "white": "#e5e7eb",
    "brightBlack": "#6b7280",
    "brightRed": "#dc2626",
    "brightGreen": "#16a34a",
    "brightYellow": "#ca8a04",
    "brightBlue": "#2563eb",
    "brightMagenta": "#9333ea",
    "brightCyan": "#0891b2",
    "brightWhite": "#111827",
}
_TTYD_THEME_PALETTES = {
    "soft-dark": _TTYD_SOFT_DARK_THEME,
    "soft-light": _TTYD_SOFT_LIGHT_THEME,
    "soft-green": _TTYD_SOFT_GREEN_THEME,
    "light": _TTYD_LIGHT_THEME,
}
_TTYD_DARK_THEME_JS = (
    'theme:{foreground:"#d2d2d2",background:"#2b2b2b",cursor:"#adadad",'
    'black:"#000000",red:"#d81e00",green:"#5ea702",yellow:"#cfae00",'
    'blue:"#427ab3",magenta:"#89658e",cyan:"#00a7aa",white:"#dbded8",'
    'brightBlack:"#686a66",brightRed:"#f54235",brightGreen:"#99e343",'
    'brightYellow:"#fdeb61",brightBlue:"#84b0d8",brightMagenta:"#bc94b7",'
    'brightCyan:"#37e6e8",brightWhite:"#f1f1f0"}'
)

_TTYD_INTERACTION_MARKER = "orch-ttyd-interactions-v1"
_TTYD_INTERACTION_SCRIPT = r"""<script id="orch-ttyd-interactions-v1">
(() => {
  const install = () => {
    const terminal = window.term;
    const core = terminal && terminal._core;
    const screen = document.querySelector(".xterm-screen");
    const mouse = core && core.coreMouseService;
    const selection = core && core._selectionService;
    if (!terminal || !screen || !mouse || !selection) return false;
    if (mouse.__orchInteractionPatch) return true;

    // ttyd 1.7.x's bundled xterm lacks DEC 2026. tmux can synchronize its
    // internal screen yet still send a client repaint over several WS chunks.
    // Hold only paint, not parsing/input, until that client frame is complete.
    const render = core._renderService;
    let synchronized = false;
    let fitAfterSync = null;
    let resizeSnapshot = null;
    let preparedResizeSnapshot = null;
    let resizeSnapshotTimer = null;
    let resizeSnapshotFrame = 0;
    let resizeSettleTimer = null;
    let sawSynchronizedOutput = false;
    const cancelResizeRelease = () => {
      clearTimeout(resizeSettleTimer);
      resizeSettleTimer = null;
      cancelAnimationFrame(resizeSnapshotFrame);
      resizeSnapshotFrame = 0;
    };
    const clearResizeSnapshot = () => {
      clearTimeout(resizeSnapshotTimer);
      cancelResizeRelease();
      resizeSnapshot?.remove();
      resizeSnapshot = null;
    };
    const releaseResizeSnapshot = () => {
      if (!resizeSnapshot) return;
      cancelResizeRelease();
      if (synchronized || resizeSnapshot.__silingPendingWrites > 0) return;
      // A resize can produce several complete tmux/TUI frames. A single END
      // or write callback is not the end of that burst. Debounce only this
      // visual cover; parsing, input and PTY sizing continue immediately.
      resizeSettleTimer = setTimeout(() => {
        resizeSnapshotFrame = requestAnimationFrame(() => {
          resizeSnapshotFrame = requestAnimationFrame(clearResizeSnapshot);
        });
      }, 120);
    };
    const captureResizeFrame = () => {
      if (!sawSynchronizedOutput || document.hidden) return;
      const canvases = [...screen.querySelectorAll("canvas")];
      const bounds = screen.getBoundingClientRect();
      if (!canvases.length || bounds.width < 2 || bounds.height < 2) return;
      const cover = document.createElement("div");
      cover.className = "siling-resize-snapshot";
      const buffer = terminal.buffer.active;
      cover.__silingResizeAnchor = {
        rows: terminal.rows, cellHeight: bounds.height / terminal.rows,
        // Only a live prompt on the last row is predictably bottom-anchored.
        // History readers, selections and top-positioned full-screen cursors
        // keep the original top alignment.
        bottom: buffer.viewportY === buffer.baseY && buffer.cursorY === terminal.rows - 1
          && !terminal.hasSelection(),
      };
      cover.setAttribute("aria-hidden", "true");
      Object.assign(cover.style, {position: "fixed", inset: "0", overflow: "hidden",
        pointerEvents: "none", zIndex: "2147483646",
        background: terminal.options.theme?.background || "#000"});
      try {
        for (const source of canvases) {
          const rect = source.getBoundingClientRect();
          const copy = document.createElement("canvas");
          copy.width = source.width; copy.height = source.height;
          const context = copy.getContext("2d");
          if (!context) return;
          context.drawImage(source, 0, 0);
          Object.assign(copy.style, {position: "absolute", left: `${rect.left}px`,
            top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px`});
          cover.appendChild(copy);
        }
      } catch (_) { return; }
      return cover;
    };
    const alignResizeFrame = (cover, rows) => {
      const anchor = cover.__silingResizeAnchor;
      const offset = anchor.bottom && Number.isInteger(rows) && rows > 0
        ? (rows - anchor.rows) * anchor.cellHeight : 0;
      for (const canvas of cover.querySelectorAll("canvas")) {
        canvas.style.transform = `translateY(${offset}px)`;
      }
    };
    const preserveResizeFrame = rows => {
      if (resizeSnapshot) {
        cancelResizeRelease();
        alignResizeFrame(resizeSnapshot, rows);
        return;
      }
      const cover = preparedResizeSnapshot || captureResizeFrame();
      preparedResizeSnapshot = null;
      if (!cover) return;
      alignResizeFrame(cover, rows);
      document.body.appendChild(cover);
      resizeSnapshot = cover;
      // A disconnected/older peer must never leave a stale screen covering input.
      resizeSnapshotTimer = setTimeout(clearResizeSnapshot, 600);
    };
    // FitAddon clears the renderer immediately BEFORE calling resize(). Keep
    // that pre-clear frame only for a resize in this same synchronous turn.
    if (render && typeof render.clear === "function") {
      const nativeClear = render.clear;
      render.clear = function (...args) {
        if (!resizeSnapshot) {
          const prepared = captureResizeFrame();
          preparedResizeSnapshot = prepared;
          queueMicrotask(() => {
            if (preparedResizeSnapshot === prepared) preparedResizeSnapshot = null;
          });
        }
        return nativeClear.apply(this, args);
      };
    }
    const nativeResize = terminal.resize;
    terminal.resize = function (cols, rows) {
      if (cols !== terminal.cols || rows !== terminal.rows) preserveResizeFrame(rows);
      try { return nativeResize.call(this, cols, rows); }
      catch (error) { clearResizeSnapshot(); throw error; }
    };
    const nativeWrite = terminal.write;
    terminal.write = function (data, callback) {
      const cover = resizeSnapshot;
      if (!cover) return nativeWrite.call(this, data, callback);
      cancelResizeRelease();
      cover.__silingPendingWrites = (cover.__silingPendingWrites || 0) + 1;
      try {
        return nativeWrite.call(this, data, () => {
          cover.__silingPendingWrites--;
          if (resizeSnapshot === cover) releaseResizeSnapshot();
          callback?.();
        });
      } catch (error) {
        cover.__silingPendingWrites--;
        if (resizeSnapshot === cover) clearResizeSnapshot();
        throw error;
      }
    };
    window.addEventListener("pagehide", clearResizeSnapshot);

    if (render && typeof render._renderRows === "function" && terminal.parser) {
      const renderRows = render._renderRows;
      let syncTimeout = null;
      const finishSync = () => {
        clearTimeout(syncTimeout);
        syncTimeout = null;
        if (!synchronized) return;
        synchronized = false;
        terminal.refresh(0, terminal.rows - 1);
        const pendingFit = fitAfterSync;
        fitAfterSync = null;
        pendingFit?.();
      };
      render._renderRows = function (...args) {
        if (!synchronized) return renderRows.apply(this, args);
      };
      terminal.parser.registerCsiHandler({prefix: "?", final: "h"}, params => {
        if (params.includes(2026)) {
          sawSynchronizedOutput = true;
          cancelResizeRelease();
          synchronized = true;
          clearTimeout(syncTimeout);
          syncTimeout = setTimeout(finishSync, 1000);
        }
        // Let xterm process any other DEC modes in the same command.
        return false;
      });
      terminal.parser.registerCsiHandler({prefix: "?", final: "l"}, params => {
        if (params.includes(2026)) {
          finishSync();
          releaseResizeSnapshot();
        }
        return false;
      });
      terminal.onResize(finishSync);
      window.addEventListener("pagehide", finishSync);
    }

    // Zoom/toolbar/font changes can settle after ttyd's single window-resize
    // fit. Recheck the actual container after layout, without changing the PTY
    // again when the fitted dimensions already match.
    const fitParent = terminal.element && terminal.element.parentElement;
    if (fitParent && typeof terminal.fit === "function") {
      let fitFrame = 0;
      const scheduleFit = () => {
        if (fitFrame) return;
        fitFrame = requestAnimationFrame(() => {
          fitFrame = requestAnimationFrame(() => {
            fitFrame = 0;
            if (synchronized) { fitAfterSync = scheduleFit; return; }
            const bounds = fitParent.getBoundingClientRect();
            if (!fitParent.isConnected || bounds.width < 2 || bounds.height < 2) return;
            terminal.fit();
          });
        });
      };
      const fitObserver = new ResizeObserver(scheduleFit);
      fitObserver.observe(fitParent);
      document.fonts?.ready.then(scheduleFit);
      document.fonts?.addEventListener("loadingdone", scheduleFit);
      window.addEventListener("pageshow", scheduleFit);
      scheduleFit();
    }

    // The iframe does not inherit Dashboard CSS. Keep its native scrollbar
    // aligned with xterm's actual palette, including late ttyd preferences.
    const scrollbarStyle = document.createElement("style");
    scrollbarStyle.textContent = `
      .xterm-viewport { scrollbar-color: var(--orch-scroll-thumb) var(--orch-scroll-track); }
      .xterm-viewport::-webkit-scrollbar { width: 12px; height: 12px; }
      .xterm-viewport::-webkit-scrollbar-track,
      .xterm-viewport::-webkit-scrollbar-corner { background: var(--orch-scroll-track); }
      .xterm-viewport::-webkit-scrollbar-thumb {
        background: var(--orch-scroll-thumb); border: 3px solid var(--orch-scroll-track);
        border-radius: 8px;
      }
      .xterm-viewport::-webkit-scrollbar-thumb:hover { background: var(--orch-scroll-hover); }
      @media (forced-colors: active) { .xterm-viewport { scrollbar-color: auto; } }
    `;
    document.head.appendChild(scrollbarStyle);
    let scrollbarPalette = "";
    const syncScrollbarTheme = () => {
      const palette = terminal.options.theme || {};
      const hex = (value, fallback) => /^#[0-9a-f]{6}$/i.test(value || "") ? value : fallback;
      const background = hex(palette.background, "#2b2b2b");
      const foreground = hex(palette.foreground, "#d2d2d2");
      const key = background + foreground;
      if (key === scrollbarPalette) return;
      scrollbarPalette = key;
      const rgb = value => [1, 3, 5].map(i => parseInt(value.slice(i, i + 2), 16));
      const bg = rgb(background), fg = rgb(foreground);
      const blend = amount => `rgb(${bg.map((v, i) => Math.round(v + (fg[i] - v) * amount)).join(",")})`;
      const style = document.documentElement.style;
      style.colorScheme = bg[0] * .299 + bg[1] * .587 + bg[2] * .114 < 128 ? "dark" : "light";
      style.setProperty("--orch-scroll-track", background);
      style.setProperty("--orch-scroll-thumb", blend(.45));
      style.setProperty("--orch-scroll-hover", blend(.65));
    };
    syncScrollbarTheme();
    terminal.onRender(syncScrollbarTheme);

    let mode = "";
    let pendingUrl = "";
    let pendingFileContext = "";
    let startX = 0;
    let startY = 0;
    // Shell, Codex and Cursor use tmux selection to span its history buffer. Older
    // dashboard frames keep native selection; Option-drag still selects in
    // xterm, and Ctrl-drag remains available to terminal applications.
    const nativeSelection = (event) => {
      try {
        return window.frameElement?.dataset.nativeSelection === "true"
          && event.button === 0 && !event.ctrlKey;
      } catch (_) { return false; }
    };
    let tmuxSelectionPending = false;
    const inlineSelection = () => {
      try { return window.frameElement?.dataset.inlineSelection === "true"; }
      catch (_) { return false; }
    };
    const originalForceSelection = selection.shouldForceSelection.bind(selection);
    selection.shouldForceSelection = (event) => (
      (nativeSelection(event) && (!inlineSelection() || mode === "native-link" || event.detail >= 2))
        || originalForceSelection(event)
    );
    const originalTriggerMouseEvent = mouse.triggerMouseEvent.bind(mouse);
    mouse.triggerMouseEvent = (event) => (
      mode === "tmux-selection"
        ? (event.button === 0 && event.action === 0 ? false : originalTriggerMouseEvent(event))
        : mode ? false : originalTriggerMouseEvent(event)
    );
    mouse.__orchInteractionPatch = true;

    const cleanLocalPath = (value) => {
      let path = String(value || "");
      if (/^file:/i.test(path)) {
        try {
          const url = new URL(path);
          if (url.host && url.host !== "localhost") return "";
          path = decodeURIComponent(url.pathname);
        } catch (_) { return ""; }
      }
      const relative = window.frameElement?.dataset.fileContext === "true"
        && /^(?:\.\.?\/)?(?:[\p{L}\p{N}_.@+~-]+\/)*[\p{L}\p{N}_.@+~-]+\.[A-Za-z0-9]{1,12}(?::\d+(?::\d+)?)?$/u.test(path);
      if ((!path.startsWith("/") && !relative) || path.startsWith("//") || /[\x00-\x1f]/.test(path)) return "";
      return path.replace(/(?::\d+(?::\d+)?|#L\d+(?:C\d+)?)$/, "");
    };
    const cleanLinkTarget = (value) => {
      let url = String(value || "");
      // Terminal linkifiers do not consistently recognize CJK punctuation
      // as a URL boundary. In prose such as `https://example.test（details）`,
      // trim the annotation before opening the target instead of letting the
      // browser percent-encode it as part of the path.
      const cjkBoundary = url.search(/[（【《〈「『〔［｛，。；：！？、]/u);
      if (cjkBoundary >= 0) url = url.slice(0, cjkBoundary);
      url = url.replace(/[.,;:!?]+$/, "");
      // Markdown commonly leaves its closing delimiter next to a literal
      // URL. Drop only unmatched trailing delimiters so valid targets such
      // as `Function_(mathematics)` remain intact.
      for (const [opening, closing] of [["(", ")"], ["[", "]"], ["{", "}"]]) {
        let balance = 0;
        for (const character of url) {
          if (character === opening) balance += 1;
          else if (character === closing) balance -= 1;
        }
        while (balance < 0 && url.endsWith(closing)) {
          url = url.slice(0, -1);
          balance += 1;
        }
      }
      url = url.replace(/[.,;:!?]+$/, "");
      return /^https?:\/\//i.test(url) ? url : cleanLocalPath(url);
    };

    const literalLinkTarget = (raw) => {
      const target = cleanLinkTarget(raw);
      // A bare /word is also a CLI slash command or a prose unit. Require
      // a directory component or filename suffix before inferring a file.
      // Explicit file:// and OSC targets retain their original semantics.
      if (raw.startsWith("/") && target.startsWith("/")
          && !/^\/[^/]+\/[^/]+/.test(target)
          && !/^\/[^/]+\.[A-Za-z0-9]{1,12}$/.test(target)) return "";
      return target;
    };

    const coordsForEvent = (event) => {
      try {
        const coords = selection._getMouseBufferCoords(event);
        if (coords && coords.length === 2) return coords;
      } catch (_) {}
      const rect = screen.getBoundingClientRect();
      if (!rect.width || !rect.height) return null;
      const col = Math.max(0, Math.min(
        terminal.cols - 1,
        Math.floor((event.clientX - rect.left) * terminal.cols / rect.width),
      ));
      const row = Math.max(0, Math.min(
        terminal.rows - 1,
        Math.floor((event.clientY - rect.top) * terminal.rows / rect.height),
      ));
      return [col, terminal.buffer.active.viewportY + row];
    };

    const oscUrlForCell = (cell) => {
      const extended = cell && cell.extended;
      const urlId = Number(extended && (extended.urlId || extended._urlId || 0));
      const linkData = urlId && core._oscLinkService?.getLinkData(urlId);
      return cleanLinkTarget(typeof linkData === "string" ? linkData
        : String((linkData && (linkData.uri || linkData.url)) || ""));
    };

    const rangesForCells = (cells) => {
      const ranges = [];
      for (const cell of cells) {
        const previous = ranges[ranges.length - 1];
        if (previous && previous.row === cell.row
            && cell.col <= previous.col + previous.width) {
          previous.width = Math.max(previous.width, cell.col + cell.width - previous.col);
        } else ranges.push({ ...cell });
      }
      return ranges;
    };

    const linkForEvent = (event) => {
      const coords = coordsForEvent(event);
      if (!coords) return null;
      let [col, row] = coords;
      const buffer = terminal.buffer.active;
      const line = row >= 0 && row < buffer.length
        ? buffer.getLine(row)
        : null;
      if (!line) return null;
      // A click on the second column of a wide glyph belongs to that glyph.
      if (col > 0 && line.getCell(col)?.getWidth() === 0) col -= 1;

      // Claude and Codex render Markdown links as OSC 8 hyperlinks: the
      // visible label may be `owner/repo#123` while the URL is stored in the
      // xterm cell metadata. Check that metadata before falling back to
      // searching for a literal https:// string on the screen.
      try {
        const oscUrl = oscUrlForCell(line.getCell(col));
        if (oscUrl) {
          const cleanOscUrl = cleanLinkTarget(oscUrl);
          // tmux may redraw wrapped links as separate physical lines and
          // assign different OSC ids to each segment. Match the target URI.
          const cellsInRow = (y) => {
            const cells = [];
            const candidate = buffer.getLine(y);
            for (let x = 0; candidate && x < terminal.cols; x += 1) {
              const cell = candidate.getCell(x);
              if (cell?.getWidth() && oscUrlForCell(cell) === cleanOscUrl) {
                cells.push({ row: y, col: x, width: cell.getWidth() });
              }
            }
            return cells;
          };
          let cells = cellsInRow(row);
          for (let y = row - 1; y >= buffer.viewportY; y -= 1) {
            const more = cellsInRow(y);
            if (!more.length) break;
            cells = more.concat(cells);
          }
          const visibleEnd = Math.min(buffer.length, buffer.viewportY + terminal.rows);
          for (let y = row + 1; y < visibleEnd; y += 1) {
            const more = cellsInRow(y);
            if (!more.length) break;
            cells.push(...more);
          }
          return { url: cleanOscUrl, ranges: rangesForCells(cells) };
        }
      } catch (_) {}

      // Read a bounded window for CLI-authored hard wraps, retaining the
      // character-to-cell map so indentation and padding stay unclickable.
      let paragraph = "";
      const paragraphCells = [];
      const physicalLines = [];
      let paragraphOffset = -1;
      for (let y = Math.max(0, row - 24); y < Math.min(buffer.length, row + 25); y += 1) {
        const candidate = buffer.getLine(y);
        let lineText = "";
        const lineCells = [];
        for (let x = 0; x < terminal.cols; x += 1) {
          const cell = candidate?.getCell(x);
          if (!cell?.getWidth()) continue;
          if (y === row && x === col) paragraphOffset = paragraph.length + lineText.length;
          const chars = cell.getChars() || " ";
          lineText += chars;
          for (let i = 0; i < chars.length; i += 1) {
            lineCells.push({row: y, col: x, width: cell.getWidth()});
          }
        }
        const trimmed = lineText.trimEnd();
        physicalLines.push({text: trimmed, cells: lineCells.slice(0, trimmed.length),
          wrapped: !!candidate?.isWrapped});
        if (y === row && paragraphOffset >= paragraph.length + trimmed.length) paragraphOffset = -1;
        paragraph += trimmed + "\n";
        paragraphCells.push(...lineCells.slice(0, trimmed.length), null);
      }

      // CLI-rendered bare URLs and absolute SSH file paths may use hard
      // line breaks with indentation and a small right gutter. Recover those
      // only across near-full rows with matching indentation and whitespace-free
      // continuations. Never decode/re-encode query data or join across prose,
      // blank lines, another URI, or a short final row. OSC metadata above
      // remains authoritative. Prose prefixes (including Chinese colons) are
      // excluded from the clickable range. The paragraph window bounds work.
      for (let i = 0; i < physicalLines.length; i += 1) {
        const head = physicalLines[i];
        const match = head.text.match(/^(.*?)(https?:\/\/[^\s<>"'`]+|\/(?!\/)[^\s<>"'`]+)$/i);
        if (!match || (match[1] && !/[\s([<="'`：，；（【]$/u.test(match[1]))) continue;
        const indent = head.text.match(/^[ \t]*/)[0];
        const local = match[2].startsWith("/");
        let target = match[2];
        let mapped = head.cells.slice(match[1].length);
        let previous = head;
        let joined = false;
        for (let j = i + 1; j < physicalLines.length; j += 1) {
          const next = physicalLines[j];
          const part = next.text.match(local
            ? /^([ \t]*)([^\s<>"'`]+)$/
            : /^([ \t]*)([A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+)$/);
          if (!part || /^[a-z][a-z0-9+.-]*:/i.test(part[2])) break;
          if (local && ((part[2].startsWith("/") && /\.[A-Za-z0-9]{1,8}$/.test(target))
              || /[，。；：！？、]$/u.test(target))) break;
          const end = previous.cells[previous.cells.length - 1];
          if (!next.wrapped && (part[1] !== indent || !end
              || end.col + end.width < terminal.cols - 8)) break;
          target += part[2];
          mapped.push(...next.cells.slice(part[1].length));
          previous = next;
          joined = true;
        }
        if (!joined) continue;
        const url = literalLinkTarget(target);
        if (!url) continue;
        mapped = mapped.slice(0, url.length);
        if (mapped.some(cell => cell.row === row && cell.col === col)) {
          return {url, ranges: rangesForCells(mapped)};
        }
      }
      // Codex's "label (/absolute/path)" uses indented hard breaks too.
      // Only reconstruct explicitly parenthesized local targets here.
      for (const match of paragraph.matchAll(/\((?:\/|file:\/\/)/g)) {
        const start = match.index;
        let end = start + 1;
        let depth = 1;
        for (; end < paragraph.length; end += 1) {
          if (paragraph[end] === "(") depth += 1;
          if (paragraph[end] === ")" && --depth === 0) break;
        }
        if (depth) continue;
        const rawTarget = paragraph.slice(start + 1, end).replace(/\n[ \t]*/g, "");
        if (/\s/.test(rawTarget)) continue;
        const target = literalLinkTarget(rawTarget);
        if (!cleanLocalPath(target)) continue;
        const label = paragraph.slice(0, start).match(/(\[[^\]\n]+\]|[^\s()[\]，。；：！？、:]+)[ \t]*$/u);
        const begin = label ? start - label[0].length : start;
        if (paragraphOffset >= begin && paragraphOffset <= end) {
          return {url: target, ranges: rangesForCells(
            paragraphCells.slice(begin, end + 1).filter(Boolean),
          )};
        }
      }

      let first = row;
      while (first > 0 && buffer.getLine(first)?.isWrapped) first -= 1;
      let last = row;
      while (last + 1 < buffer.length && buffer.getLine(last + 1)?.isWrapped) {
        last += 1;
      }
      let text = "";
      const cells = [];
      let offset = -1;
      for (let index = first; index <= last; index += 1) {
        const candidate = buffer.getLine(index);
        for (let x = 0; x < terminal.cols; x += 1) {
          const cell = candidate?.getCell(x);
          if (!cell || !cell.getWidth()) continue;
          if (index === row && x === col) offset = text.length;
          const chars = cell.getChars() || " ";
          text += chars;
          // JS string offsets are UTF-16, not terminal columns. Keep an
          // explicit map so CJK/emoji before a URL do not shift its range.
          for (let i = 0; i < chars.length; i += 1) {
            cells.push({ row: index, col: x, width: cell.getWidth() });
          }
        }
      }
      const pattern = /https?:\/\/[^\s<>"'`]+|file:\/\/[^\s<>"'`]+|\/[^\s<>"'`]+/g;
      for (const match of text.matchAll(pattern)) {
        const raw = match[0];
        const url = literalLinkTarget(raw);
        const begin = match.index || 0;
        if (raw.startsWith("/") && begin > 0 && !/[\s([<="'`：，；（【]/u.test(text[begin - 1])) continue;
        const length = url && /^file:/i.test(raw) ? raw.length : url.length;
        if (offset >= begin && offset < begin + length) {
          return { url, ranges: rangesForCells(cells.slice(begin, begin + length)) };
        }
      }
      if (window.frameElement?.dataset.fileContext === "true") {
        const relativePattern = /(?:\.\.?\/)?(?:[\p{L}\p{N}_.@+~-]+\/)*[\p{L}\p{N}_.@+~-]+\.[A-Za-z0-9]{1,12}(?::\d+(?::\d+)?)?/gu;
        for (const match of text.matchAll(relativePattern)) {
          const begin = match.index;
          if (begin && /[\w/]/.test(text[begin - 1])) continue;
          if (offset >= begin && offset < begin + match[0].length) {
            return {url: cleanLocalPath(match[0]), ranges: rangesForCells(cells.slice(begin, begin + match[0].length))};
          }
        }
      }
      return null;
    };
    const urlForEvent = (event) => linkForEvent(event)?.url || "";

    let hoverLayer = null;
    const clearHover = () => {
      hoverLayer?.replaceChildren();
      if (screen.style) screen.style.cursor = "";
    };
    const showHover = (link) => {
      clearHover();
      if (!link) return;
      if (!hoverLayer) {
        hoverLayer = document.createElement("div");
        hoverLayer.className = "siling-link-highlight";
        hoverLayer.style.cssText = "position:absolute;inset:0;pointer-events:none;z-index:10";
        screen.appendChild(hoverLayer);
      }
      screen.style.cursor = "pointer";
      const rect = screen.getBoundingClientRect();
      const cellWidth = rect.width / terminal.cols;
      const cellHeight = rect.height / terminal.rows;
      for (const range of link.ranges) {
        const y = range.row - terminal.buffer.active.viewportY;
        if (y < 0 || y >= terminal.rows) continue;
        const underline = document.createElement("span");
        Object.assign(underline.style, {
          position: "absolute", left: `${range.col * cellWidth}px`,
          top: `${(y + 1) * cellHeight - 1}px`, width: `${range.width * cellWidth}px`,
          borderBottom: "1px solid", color: terminal.options?.theme?.foreground || "#d2d2d2",
        });
        hoverLayer.appendChild(underline);
      }
    };

    const clearMode = () => {
      mode = "";
      pendingUrl = "";
    };

    screen.addEventListener("mousedown", (event) => {
      if (event.button !== 0 || event.ctrlKey) return;
      clearHover();
      selectionEpoch++; tmuxPreview = null; clearMargin();
      clearTimeout(liveMarginTimer); liveMarginTimer = null; liveMarginDirty = false;
      startX = event.clientX;
      startY = event.clientY;
      if (event.altKey || (nativeSelection(event) && event.detail >= 2)) {
        // Older xterm.js releases still emit a mouse-release report after an
        // Option-drag selection. tmux redraws on that report and erases the
        // selection. Keep mouse reporting muted through the matching mouseup.
        mode = "selection";
        return;
      }
      pendingUrl = urlForEvent(event);
      const point = coordsForEvent(event);
      pendingFileContext = point ? window.silingFileContextForRow?.(point[1]) || "" : "";
      if (nativeSelection(event)) {
        mode = pendingUrl ? "native-link" : inlineSelection() ? "tmux-selection" : "selection";
        tmuxSelectionPending = false;
        if (mode === "tmux-selection") terminal.clearSelection?.();
        return;
      }
      if (!pendingUrl) return;
      mode = "link";
    }, true);

    document.addEventListener("mousemove", (event) => {
      if (mode === "tmux-selection" && (event.buttons & 1)
          && Math.hypot(event.clientX - startX, event.clientY - startY) > 3) {
        tmuxSelectionPending = true;
        scheduleLiveMargin();
      }
    }, true);
    screen.addEventListener("mousemove", (event) => {
      if (event.buttons) return;
      const link = linkForEvent(event);
      showHover(link);
      const layer = screen.querySelector(".xterm-link-layer");
      if (layer) layer.style.cursor = link ? "pointer" : "default";
    }, true);
    screen.addEventListener("mouseleave", clearHover);
    terminal.onScroll?.(() => { clearHover(); paintNativeMargin(); });
    terminal.onResize?.(() => { clearHover(); clearMargin(); });
    terminal.onWriteParsed?.(() => {
      clearHover(); paintNativeMargin();
      if (mode === "tmux-selection" && tmuxSelectionPending) scheduleLiveMargin();
    });

    // A multiline selection has a separate left edge on each row. Keep the
    // actual buffer intact and exclude its common margin from both highlight
    // and clipboard text. A row with no indentation makes this a no-op.
    const dedentSelection = (text) => {
      const lines = text.split(/\r?\n/);
      const nonempty = lines.filter(line => /\S/.test(line));
      if (!nonempty.length || nonempty.some(line => /^[ \t]*\t/.test(line))) return {text, indent: 0};
      const indent = nonempty.reduce((minimum, line) => Math.min(minimum, line.match(/^ */)[0].length), Infinity);
      if (!indent) return {text, indent: 0};
      return {indent, text: text.replace(/^ */gm, spaces => spaces.slice(Math.min(indent, spaces.length)))};
    };
    const marginLayer = document.createElement("div");
    marginLayer.className = "siling-selection-margin";
    Object.assign(marginLayer.style, {position:"absolute", inset:"0", pointerEvents:"none", zIndex:"8"});
    screen.appendChild(marginLayer);
    const clearMargin = () => marginLayer.replaceChildren();
    const rawSelection = terminal.getSelection?.bind(terminal) || (() => "");
    const nativeDedent = () => {
      const text = rawSelection();
      const range = terminal.getSelectionPosition?.();
      if (!range || selection._activeSelectionMode === 3
          || range.end.y - range.start.y + 1 !== text.split(/\r?\n/).length) return {text, indent:0};
      return dedentSelection(text);
    };
    terminal.getSelection = () => nativeDedent().text;
    const paintMargin = (range, indent, viewport) => {
      clearMargin();
      if (!indent) return;
      const bounds = screen.getBoundingClientRect();
      const cellWidth = bounds.width / terminal.cols, cellHeight = bounds.height / terminal.rows;
      for (let row = Math.max(range.start.y, viewport); row <= Math.min(range.end.y, viewport + terminal.rows - 1); row++) {
        const col = row === range.start.y ? range.start.x : 0;
        const end = row === range.end.y ? range.end.x : terminal.cols;
        const line = terminal.buffer.active.getLine(terminal.buffer.active.viewportY + row - viewport);
        let width = 0;
        // Never cover content if the buffer changed since the snapshot.
        while (width < indent && col + width < end) {
          const cell = line?.getCell(col + width);
          if (!cell || !/^[ \t]*$/.test(cell.getChars())) break;
          width++;
        }
        if (!width) continue;
        const mask = document.createElement("span");
        Object.assign(mask.style, {position:"absolute", left:`${col * cellWidth}px`,
          top:`${(row - viewport) * cellHeight}px`, width:`${width * cellWidth}px`,
          height:`${cellHeight}px`, background:terminal.options.theme?.background || "#2b2b2b"});
        marginLayer.appendChild(mask);
      }
    };
    const paintNativeMargin = () => {
      const result = nativeDedent();
      const range = terminal.getSelectionPosition?.();
      if (range) paintMargin(range, result.indent, terminal.buffer.active.viewportY);
      else if (tmuxPreview) paintMargin(tmuxPreview, tmuxPreview.indent, tmuxPreview.viewport);
      else clearMargin();
    };
    document.addEventListener("copy", event => {
      const result = nativeDedent();
      if (!result.indent || !event.clipboardData) return;
      event.clipboardData.setData("text/plain", result.text);
      event.preventDefault();
      event.stopImmediatePropagation();
    }, true);
    terminal.onSelectionChange?.(paintNativeMargin);
    // xterm emits onSelectionChange only after some drag operations finish.
    // Its redraw event also follows the moving selection, without changing
    // the drag anchor (which would make extending/reversing the drag jump).
    let nativeMarginFrame = null;
    selection.onRequestRedraw?.(() => {
      if (nativeMarginFrame !== null) return;
      nativeMarginFrame = requestAnimationFrame(() => {
        nativeMarginFrame = null;
        paintNativeMargin();
      });
    });
    let tmuxPreview = null;
    let selectionEpoch = 0;
    const updateTmuxMargin = async (previewOnly = false) => {
      const epoch = selectionEpoch;
      const result = await window.silingTrimSelection(previewOnly);
      if (epoch !== selectionEpoch) return;
      tmuxPreview = null; clearMargin();
      const preview = result?.preview;
      if (!preview || preview.rectangle
          || preview.end.y - preview.start.y + 1 !== preview.text.split(/\r?\n/).length) return;
      const normalized = dedentSelection(preview.text);
      if (!normalized.indent) return;
      tmuxPreview = {...preview, indent:normalized.indent, normalized:normalized.text};
      paintMargin(preview, normalized.indent, preview.viewport);
    };
    let liveMarginTimer = null;
    let liveMarginPending = false;
    let liveMarginDirty = false;
    const scheduleLiveMargin = () => {
      liveMarginDirty = true;
      if (liveMarginTimer !== null || liveMarginPending || !window.silingTrimSelection) return;
      const epoch = selectionEpoch;
      liveMarginTimer = setTimeout(() => {
        liveMarginTimer = null;
        if (epoch !== selectionEpoch || mode !== "tmux-selection" || !tmuxSelectionPending) return;
        liveMarginPending = true;
        liveMarginDirty = false;
        // One read-only request at a time; final mouseup adjustment waits for
        // it. Never move tmux's selection endpoint during an active drag.
        selectionAdjustment = selectionAdjustment.then(() => updateTmuxMargin(true))
          .catch(clearMargin).finally(() => {
            liveMarginPending = false;
            if (liveMarginDirty && mode === "tmux-selection" && tmuxSelectionPending) scheduleLiveMargin();
          });
      }, 60);
    };
    let marginScrollTimer;
    screen.addEventListener("wheel", () => {
      clearTimeout(marginScrollTimer);
      marginScrollTimer = setTimeout(() => {
        if (tmuxSelectionPending && mode !== "tmux-selection" && window.silingTrimSelection) {
          selectionAdjustment = selectionAdjustment.then(() => updateTmuxMargin()).catch(clearMargin);
        }
      }, 150);
    }, {passive:true});
    const trimSingleLineSelection = () => {
      const text = rawSelection();
      const position = terminal.getSelectionPosition?.();
      if (!position || position.start.y !== position.end.y
          || selection.columnSelectMode || selection._activeSelectionMode === 3
          || /[\r\n]/.test(text)) return;
      const spaces = text.match(/^[ \t]+(?=\S)/)?.[0].length || 0;
      if (spaces) terminal.select(position.start.x + spaces, position.start.y,
        position.end.x - position.start.x - spaces);
    };
    let selectionAdjustment = Promise.resolve();
    document.addEventListener("mouseup", (event) => {
      clearTimeout(liveMarginTimer); liveMarginTimer = null; liveMarginDirty = false;
      if (event.button === 0 && !event.ctrlKey && mode !== "tmux-selection") {
        setTimeout(() => { trimSingleLineSelection(); paintNativeMargin(); }, 0);
      }
      if (mode === "tmux-selection") {
        // Suppress the default drag-end copy-and-cancel: retain the highlighted
        // tmux selection so wheel scrolling and the copy shortcut can use it.
        if (tmuxSelectionPending && window.silingTrimSelection) {
          selectionAdjustment = selectionAdjustment.then(() => updateTmuxMargin())
            .catch(() => {}); // Keep the original selection if adjustment is unavailable.
        }
        setTimeout(clearMode, 0);
        return;
      }
      if (mode === "selection") {
        // Let xterm finalize the selection first; keep the mouse report muted
        // until every listener for this mouseup event has run.
        setTimeout(clearMode, 0);
        return;
      }
      if (mode !== "link" && mode !== "native-link") return;
      const moved = Math.hypot(
        event.clientX - startX,
        event.clientY - startY,
      ) > 6;
      if (mode === "native-link" && moved) {
        setTimeout(clearMode, 0);
        return;
      }
      if (mode === "native-link") {
        // We stop the click below to bypass ttyd's link dialog. Finalize
        // xterm's selection first, otherwise its document drag listener can
        // swallow the next real drag's initial mouse movement.
        (selection._handleMouseUp || selection._onMouseUp)?.call(selection, event);
      }
      // ttyd's built-in xterm handler displays a confirmation dialog for
      // every OSC 8 link. Handle the validated link here, before that
      // mouseup handler runs, so one click opens one tab without a prompt.
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!moved && cleanLocalPath(pendingUrl)) {
        if (window.parent !== window) {
          window.parent.postMessage(
            { type: "siling:open-local-path", path: cleanLocalPath(pendingUrl),
              ...(window.frameElement?.dataset.fileContext === "true" ? {context_id:pendingFileContext} : {}) },
            window.location.origin,
          );
        }
        clearMode();
        return;
      }
      if (!moved) {
        let routed = false;
        try {
          routed = window.parent !== window
            && window.parent.silingOpenWebUrl?.(pendingUrl, window) === true;
        } catch (_) {}
        if (routed) {
          clearMode();
          return;
        }
        let openInternally = false;
        try {
          openInternally = window.parent !== window
            && window.parent.localStorage.getItem("siling_open_links_internally") === "1";
        } catch (_) {}
        if (openInternally) {
          window.parent.postMessage(
            { type: "siling:open-web-url", url: pendingUrl },
            window.location.origin,
          );
        } else {
          window.open(pendingUrl, "_blank", "noopener,noreferrer");
        }
      }
      clearMode();
    }, true);

    document.addEventListener("keydown", (event) => {
      if (!inlineSelection()) return;
      const copy = event.key.toLowerCase() === "c"
        && ((event.metaKey && !event.ctrlKey) || (event.ctrlKey && event.shiftKey));
      if (copy && tmuxSelectionPending && !terminal.hasSelection?.()) {
        event.preventDefault();
        event.stopImmediatePropagation();
        const read = window.silingReadSelection;
        if (!read) return;
        const text = selectionAdjustment.then(read).then(result => {
          if (!result.text) throw new Error("No terminal text is selected");
          return tmuxPreview?.text === result.text ? tmuxPreview.normalized : result.text;
        });
        // Construct ClipboardItem during the trusted key event. Safari keeps
        // its user gesture permission while the selection request completes.
        const copying = window.ClipboardItem && navigator.clipboard?.write
          ? navigator.clipboard.write([new ClipboardItem({
              "text/plain": text.then(value => new Blob([value], {type: "text/plain"})),
            })])
          : text.then(value => navigator.clipboard.writeText(value));
        copying.catch(error => window.alert("Copy failed: " + error.message));
      } else if (event.key === "Escape"
          || (!event.metaKey && !event.altKey && event.key.length === 1)) {
        tmuxSelectionPending = false;
        selectionEpoch++; tmuxPreview = null; clearMargin();
      }
    }, true);

    // A mouseup outside the iframe never reaches xterm. Its native drag
    // interval otherwise keeps scrolling after focus or pane geometry changes.
    // Remove only drag listeners/timers; preserve the selected text for copying.
    const cancelDrag = () => {
      selection._removeMouseDownListeners?.();
      clearMode();
      clearHover();
    };
    window.silingCancelTerminalDrag = cancelDrag;
    window.addEventListener("blur", cancelDrag);
    return true;
  };

  if (install()) return;
  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    if (install() || attempts >= 100) clearInterval(timer);
  }, 50);
})();
</script>"""


def normalize_terminal_theme(theme: str) -> str:
    theme = (theme or "").strip().lower().replace("_", "-").replace(" ", "-")
    if theme in {"dark", "default"}:
        return ""
    if theme == "white":
        return "light"
    if theme in _TTYD_THEME_PALETTES:
        return theme
    return ""


def ttyd_theme_client_option(theme: str = "") -> str:
    theme = normalize_terminal_theme(theme) or normalize_terminal_theme(
        os.environ.get("ORCH_TTYD_THEME", "")
    )
    palette = _TTYD_THEME_PALETTES.get(theme)
    if palette:
        return "theme=" + json.dumps(palette, separators=(",", ":"))
    return ""


def _ttyd_theme_js(theme: str) -> str:
    theme = normalize_terminal_theme(theme)
    palette = _TTYD_THEME_PALETTES.get(theme)
    if not palette:
        return _TTYD_DARK_THEME_JS
    pairs = ",".join(
        f'{key}:{json.dumps(value)}' for key, value in palette.items()
    )
    return "theme:{" + pairs + "}"


def patch_ttyd_index_theme(content: bytes, theme: str) -> bytes:
    """Patch ttyd's bundled xterm termOptions theme for themed panes."""
    if not normalize_terminal_theme(theme) or not content:
        return content
    text = content.decode("utf-8", "ignore")
    patched = text.replace(_TTYD_DARK_THEME_JS, _ttyd_theme_js(theme), 1)
    if patched == text:
        return content
    return patched.encode("utf-8")


class TtydOutputThemeMapper:
    """Map a TUI's explicit true-color black background to the pane theme.

    Recent Codex TUIs paint every cell with ``ESC[48;2;0;0;0m``.  That is an
    explicit RGB color, so xterm's configured background and ANSI ``black``
    palette cannot override it.  ttyd prefixes terminal-output WebSocket
    messages with the byte ``0``; this mapper rewrites only that exact
    background sequence and preserves every other color and protocol message.
    """

    _BLACK_BACKGROUND = b"\x1b[48;2;0;0;0m"

    def __init__(self, theme: str):
        palette = _TTYD_THEME_PALETTES.get(normalize_terminal_theme(theme))
        background = palette.get("background", "") if palette else ""
        self._replacement = b""
        if len(background) == 7 and background.startswith("#"):
            try:
                red = int(background[1:3], 16)
                green = int(background[3:5], 16)
                blue = int(background[5:7], 16)
                self._replacement = (
                    f"\x1b[48;2;{red};{green};{blue}m".encode("ascii")
                )
            except ValueError:
                pass
        self._pending = b""

    def transform(self, message):
        if not self._replacement or not isinstance(message, bytes):
            return [message]
        if not message.startswith(b"0"):
            output = []
            if self._pending:
                output.append(b"0" + self._pending)
                self._pending = b""
            output.append(message)
            return output

        data = self._pending + message[1:]
        keep = 0
        maximum = min(len(data), len(self._BLACK_BACKGROUND) - 1)
        for size in range(maximum, 0, -1):
            if data.endswith(self._BLACK_BACKGROUND[:size]):
                keep = size
                break
        body = data[:-keep] if keep else data
        self._pending = data[-keep:] if keep else b""
        body = body.replace(self._BLACK_BACKGROUND, self._replacement)
        return [b"0" + body] if body else []

    def finish(self):
        if not self._pending:
            return None
        message = b"0" + self._pending
        self._pending = b""
        return message


def patch_ttyd_index_interactions(content: bytes) -> bytes:
    """Add reliable link and Option-drag behavior to ttyd's xterm page.

    ttyd 1.7.x bundles an xterm.js release that can emit a final tmux mouse
    report after an Option-drag selection. The resulting redraw immediately
    clears the selection. The same mouse-reporting path consumes ordinary URL
    clicks. Inject a small, idempotent compatibility layer into the HTML page;
    keyboard input is unchanged. Shell, Codex and Cursor panes favor native selection;
    Ctrl-drag retains mouse reporting, as does dragging in other agent panes.
    """
    if not content or _TTYD_INTERACTION_MARKER.encode() in content:
        return content
    text = content.decode("utf-8", "ignore")
    if "</body>" not in text:
        return content
    return text.replace(
        "</body>", _TTYD_INTERACTION_SCRIPT + "</body>", 1,
    ).encode("utf-8")
