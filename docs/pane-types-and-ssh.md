# Pane types and stalled SSH

Open a pane's **⋯** menu for these actions.

## Disconnect SSH

In a **Terminal** pane, choose **Disconnect SSH** and confirm. SiLing identifies the single foreground OpenSSH client belonging to this pane, then sends that process a local termination signal. It does not wait for a response from the SSH server and leaves the local login shell and tmux pane running. Remote commands can be interrupted by disconnection.

The inspection checks the terminal, parent process chain, user, foreground process group, command name, and start time. Confirmation is tied to that process identity; if it changes, the operation is rejected. Background tunnels, other panes, agent sessions, and ambiguous process trees are not targeted. If you used `exec ssh` to replace the shell itself, this recovery action refuses to terminate it; end/reopen that terminal through the existing session controls instead.

This adds a recovery action; ordinary Ctrl+C continues to behave as terminal input. OpenSSH also provides its own local disconnect escape: Enter, then `~.` with the default escape configuration. For automatic detection of future lost connections, configure `ServerAliveInterval` and `ServerAliveCountMax` for the relevant host in your own SSH configuration. SiLing does not overwrite that configuration. See the [OpenSSH escape documentation](https://man.openbsd.org/ssh.1#ESCAPE_CHARACTERS) and [server-alive settings](https://man.openbsd.org/ssh_config.5#ServerAliveInterval).

## Switch pane type

Choose **Switch pane type**, select Terminal, Claude, Codex or Cursor, check the project directory and click **Switch type**. This starts a new session in the same pane position. The previous session remains running in the background and can be reopened from Sessions. Its history stays with the original session; its linked files and palette are carried to the new session. An agent's conversation is not converted into a different agent's native conversation.

Switching a Terminal pane to an agent starts that agent on the same **Dashboard node**, not inside an existing SSH connection. An SSH shell is still a separate remote connection; to manage an agent directly on that machine, configure it as a Remote Node. Both nodes need the updated Dashboard to use these controls.

Failed starts keep the original pane. Repeated submissions of the same request reuse the recorded result. If startup was interrupted and the result is uncertain, check Sessions before reopening the switch form. If the user moved the source pane while startup was pending, the new session follows it; if the source was removed, only a free slot may be used.

## 中文

在 pane 标题栏的 **⋯** 菜单中操作：

- **断开 SSH**：适用于普通 Terminal。确认后直接终止当前前台 SSH 客户端，不等待远程响应；本地 shell 和 pane 保留。远程命令可能因连接断开而中断。不会停止后台 SSH 隧道或其他 pane，也不会改变普通 Ctrl+C 的含义。若使用 `exec ssh` 替换了本地 shell，则拒绝此操作，可使用原有的结束／重新打开终端功能。
- **切换面板类型**：选择 Terminal／Claude／Codex／Cursor，检查工作目录后点击「切换类型」。新会话放到原 pane 位置；原会话保留在后台，可从会话列表重新打开。Files 和配色会继承，聊天历史仍属于原会话。

从 SSH Terminal 切换到 Agent，启动位置是该 pane 所属的 Dashboard 节点，不会自动进入 SSH 远程机器。启动失败保留原 pane；不确定是否已启动时，先检查会话列表，再重新打开切换表单。
