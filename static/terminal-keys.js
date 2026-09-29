/* ttyd's legacy xterm encoder collapses Shift+Enter into ordinary CR. */
(() => {
  function install(doc, getSession, getTerminal) {
    let composing = false;
    doc.addEventListener("compositionstart", () => { composing = true; }, true);
    doc.addEventListener("compositionend", () => {
      setTimeout(() => { composing = false; }, 0);
    }, true);
    doc.addEventListener("keydown", event => {
      if (event.key !== "Enter" || !event.shiftKey || event.ctrlKey
          || event.altKey || event.metaKey || composing || event.isComposing
          || event.keyCode === 229
          || !event.target?.classList?.contains("xterm-helper-textarea")) return;
      const session = getSession();
      if (!session || session.alive === false || session.agent_exited === true) return;
      const agent = String(session.agent || "").trim().toLowerCase();
      let data;
      // Codex can decode bare LF as Enter. A bracketed paste inserts a literal
      // newline and also uses SiLing's existing return-from-history path.
      if (agent === "codex") data = "\x1b[200~\n\x1b[201~";
      // Claude and Cursor document Ctrl+J as their tmux-safe newline binding.
      else if (["claude", "cursor", "agent"].includes(agent)) data = "\n";
      else return; // Plain shells, SSH terminals and unknown apps stay native.
      const terminal = getTerminal();
      if (typeof terminal?.input !== "function") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      // Use the same WebSocket as surrounding keystrokes; no HTTP send race,
      // clipboard access, global tmux keybinding or additional Enter is needed.
      terminal.input(data, true);
    }, true);
  }
  if (typeof module !== "undefined") module.exports = {install};
  else window.SiLingTerminalKeys = {install};
})();
