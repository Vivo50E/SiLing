# Cursor transcript replay in small panes

The observed Cursor build (`2026.10.01-14929f9`) uses an Ink renderer that can clear the terminal and replay all static history when its changed live region exceeds the terminal height. In the affected session, the PTY stayed at 35 × 10 while tmux history changed by thousands of lines between samples. Increasing pane height only reduced the trigger; it did not fix partial repaint delivery.

SiLing's Cursor launcher now preloads `scripts/cursor-sync-output.cjs` for that invocation. Complete clear-screen repaint writes are bracketed with DEC synchronized-output markers before entering the PTY. tmux processes the history but presents the finished screen instead of intermediate replay screens. For large frames, markers refresh the synchronization deadline at character boundaries outside ANSI control strings. This preserves the original data, colors, hyperlinks, terminal history, callback and backpressure behavior.

This targets the observed complete-frame clear-screen writes. Ordinary output, redirected output, incomplete control strings and Cursor's own synchronized widgets pass through. It does not change Cursor's computation or reduce how often Cursor internally redraws. No vendor installation files or global shell configuration are modified; the preload removes its environment settings before Cursor starts child commands.

Application synchronized updates require **tmux 3.7 or later**. tmux's [3.7c implementation](https://github.com/tmux/tmux/blob/3.7c/screen-write.c) has a one-second timeout; the refresh markers prevent long transcript replays from dropping out of synchronization midway. Older tmux versions do not receive this display guarantee.

After updating SiLing, newly started or resumed Cursor sessions use the hook. **An already-running Cursor process needs to be restarted/resumed to enable it; refreshing the Dashboard or reconnecting ttyd is insufficient.** Finish or pause the current task first and use the existing Restart agent action. This change does not restart any active session automatically.

Validation uses an isolated Node fixture and a real 35 × 10 tmux client, without a paid model call: a 150,000-line replay exposes intermediate history without the hook, while the hooked stream exposes only the final viewport. Final screen contents match, and prior lines remain in tmux history. This does not replace checking the user's next real Cursor workload after restart.

## 中文

本次定位到的原因是 Cursor 在小终端里清屏重放整段历史，一次重绘经过 PTY 分块传输后，中间状态会被逐次显示。之前压缩工具栏、增大高度只能降低触发概率。

现在在 Cursor 启动时为完整清屏重绘加入同步更新边界，让 tmux 处理完整帧后再显示；超长帧会延续同步保护，避免一秒超时后再次显示中间状态。原始文本、颜色、链接及 tmux 历史保留，不修改 Cursor 安装文件，也不影响其子进程。

需要 tmux 3.7+。更新 SiLing 后，新建／恢复的 Cursor 会话自动启用；**当前已运行的 Cursor 必须在任务完成或暂停后重启／恢复，单纯刷新网页不能生效**。现有会话不会被自动重启。该修复针对已复现的完整清屏重绘，仍需用真实任务确认更新后的表现。
