# Cursor transcript replay in small panes

The observed Cursor build (`2026.10.01-14929f9`) uses an Ink renderer that can clear the terminal and replay all static history when its changed live region exceeds the terminal height. In the affected session, the PTY stayed at 35 × 10 while tmux history changed by thousands of lines between samples. Increasing pane height only reduced the trigger; it did not fix partial repaint delivery.

SiLing's Cursor launcher now preloads `scripts/cursor-sync-output.cjs` for that invocation. Complete repaint writes using screen/line erasure or cursor motion are bracketed with DEC synchronized-output markers before entering the PTY. tmux processes the history but presents the finished screen instead of intermediate replay screens. For large frames, markers refresh the synchronization deadline at character boundaries outside ANSI control strings. This preserves the original data, colors, hyperlinks, terminal history, callback and backpressure behavior; the exact clear/history/home prefix uses equivalent line erasures as described below.

This covers complete clear-screen and partial repaint writes, including writes without a trailing newline. The earlier implementation only recognized clear-screen writes ending in a newline and left Ink's line-erasure/cursor-motion paths unprotected. A stream parser tracks split ANSI controls, UTF-8 characters and Cursor-owned synchronization across writes; those writes pass through unchanged, as do ordinary text and redirected output. It does not change Cursor's computation or reduce how often Cursor internally redraws. No vendor installation files or global shell configuration are modified; the preload removes its environment settings before Cursor starts child commands.

Application synchronized updates require **tmux 3.7 or later**. tmux's [3.7c implementation](https://github.com/tmux/tmux/blob/3.7c/screen-write.c) has a one-second timeout; the refresh markers prevent long transcript replays from dropping out of synchronization midway. Older tmux versions do not receive this display guarantee.

After updating SiLing, newly started or resumed Cursor sessions use the hook. **An already-running Cursor process needs to be restarted/resumed to enable it; refreshing the Dashboard or reconnecting ttyd is insufficient.** Finish or pause the current task first and use the existing Restart agent action. This change does not restart any active session automatically.

Validation uses an isolated Node fixture and a real 35 × 10 tmux client, without a paid model call: 150,000-line full-screen and partial replays expose intermediate history without the hook, while the hooked streams expose only the final viewport. The partial replay has no final newline and failed with the earlier hook (over 20,000 intermediate replay lines reached the client). Final screen contents match, and prior lines remain in tmux history. This does not replace checking the user's next real Cursor workload after restart.

## 中文

本次定位到的原因是 Cursor 在小终端里清屏重放整段历史，一次重绘经过 PTY 分块传输后，中间状态会被逐次显示。之前压缩工具栏、增大高度只能降低触发概率。

现在在 Cursor 启动时为完整清屏、擦行和光标移动重绘加入同步更新边界，不再要求输出以换行结束，让 tmux 处理完整帧后再显示；超长帧会延续同步保护，避免一秒超时后再次显示中间状态。原始文本、颜色、链接及 tmux 历史保留，不修改 Cursor 安装文件，也不影响其子进程。

需要 tmux 3.7+。更新 SiLing 后，新建／恢复的 Cursor 会话自动启用；**当前已运行的 Cursor 必须在任务完成或暂停后重启／恢复，单纯刷新网页不能生效**。现有会话不会被自动重启。该修复针对已复现的完整清屏重绘，仍需用真实任务确认更新后的表现。

窗口缩小时 Ink 还会擦除旧内容并重新排版。新增测试覆盖此前漏掉的局部重绘路径，但不承诺消除尺寸切换本身的一次正常重排，也不能替代实际 Working 和放大／还原操作的验收。跨多次写入的原生同步块、ANSI 控制序列和 UTF-8 字符均保留原始字节。

## Browser paint boundary

Application synchronization and browser painting are separate boundaries. A real
Cursor capture showed synchronized application frames while its ttyd tmux client
had no `sync` terminal feature. ttyd 1.7.x's bundled xterm also ignored DEC 2026,
so a completed tmux screen could still become visible in pieces over WebSocket.

SiLing now advertises `sync` only for its ttyd tmux clients (`tmux -T sync`). The
injected browser compatibility layer defers xterm's render-service paint callback
between DEC 2026 markers. Parsing and input continue; an end marker, terminal
resize, or a one-second watchdog releases painting. This uses a guarded xterm
internal render hook because that bundled version has no public synchronized
render API; browser tests exercise the installed ttyd and compare visible pixels.
Future ttyd/xterm upgrades must rerun those compatibility tests.

After this browser-side update, reload the Dashboard/terminal iframe so both the
new client feature and browser handler are active. An agent already using the
Cursor output hook does **not** need another restart for this browser change.
Normal content changes and resize reflow remain visible; synchronization prevents
unfinished frames, not legitimate changes between complete frames.

浏览器端是另一段显示链路：Cursor 的同步输出到达 tmux 后，浏览器仍可能分段绘制。
现在只对 SiLing 的 ttyd 客户端启用 `sync`，并为 ttyd 内置的旧版 xterm 补上同步绘制支持。
期间输入和解析继续进行；结束标记、终端尺寸变化或一秒超时均会释放绘制。
这部分更新后需要刷新 Dashboard／终端 iframe；已加载 Cursor 输出补丁的 Agent 无需再次重启。
正常内容更新和尺寸重排仍会发生，补丁针对未完成画面的闪烁，不隐藏真正的内容变化。

## Separate clears and settled layout

The tmux 3.7c [whole-screen erase path](https://github.com/tmux/tmux/blob/3.7c/screen-write.c#L1815)
issues a direct client clear even during application synchronization; the
[line erase path](https://github.com/tmux/tmux/blob/3.7c/screen-write.c#L1411)
uses collected updates. A real PTY capture reproduced a blank client frame before
replacement text. For Cursor's exact clear-screen + clear-history + home prefix,
the hook substitutes per-line erasure using the current TTY row count, retains
clear-history and homes the cursor. Plain clears are not translated, so tmux's
`scroll-on-clear` history behavior is preserved outside that explicit sequence.

A synchronized erase-only write still publishes an empty frame if its end marker
is sent before Ink writes the replacement. The Cursor hook now keeps that erase
transaction open across subsequent control writes and closes it with replacement
text. It releases after 900 ms if no replacement arrives, before tmux's one-second
timeout, and closes before native synchronized blocks or incomplete control data.
Input, byte order, callbacks and backpressure remain unchanged. This hook change
requires restarting/resuming an existing Cursor process after updating SiLing.

The browser also observes the actual terminal container and font readiness, then
fits after two animation frames. This covers layout changes after ttyd's single
window resize event. Hidden containers are skipped, and fitting waits for an
active synchronized frame to finish. An unchanged fit does not resize the PTY.
The browser part requires a page reload, not an agent restart.

“先清空、稍后重绘”现在共享同一段同步显示保护，避免先提交一帧空白。
无后续文字时会在 900 ms 内释放，退出与原生同步控制也会正常收尾。
该部分属于 Cursor 进程内补丁，更新后已有 Cursor 需重启／恢复才能加载。

放大／还原后，浏览器观察实际容器和字体变化，在布局稳定后重新计算列数，
避免错过单次 resize 事件后一直保持窄列。隐藏容器不调整尺寸，正在同步重绘时
延后校正，尺寸相同不会反复触发 PTY resize。这部分刷新页面即可加载。
