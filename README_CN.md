<div align="center">

# SiLing

**随时知道每个 coding agent 在做什么、哪个最重要，以及如何把工作完整找回来。**

[![CI](https://github.com/Vivo50E/SiLing/actions/workflows/ci.yml/badge.svg)](https://github.com/Vivo50E/SiLing/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![macOS and Linux](https://img.shields.io/badge/macOS%20%7C%20Linux-local--first-24292f)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](README.md)

</div>

SiLing 基于 [YAMY1234 的 Agent Orchestrator](https://github.com/YAMY1234/agent-orchestrator-public)
fork 并独立维护。原项目提供了本地优先、基于 tmux 的多 Agent Dashboard；
SiLing 在此基础上增加会话控制、改进终端交互，并提供更可配置的工作台。
感谢原作者和贡献者提供的项目基础。

## SiLing 在 fork 后增加了什么

以下是 [Vivo50E/SiLing](https://github.com/Vivo50E/SiLing) 维护的新增功能和改进，
与继承自上游的核心能力分开列出：

- **更多会话入口**：增加用于手动执行命令的 Terminal-only 会话、导入已有原生
  Agent 对话、可配置的默认 Working dir，以及点击空 pane 直接创建会话。
- **单独重启 Agent**：支持使用已保存的原生对话标识重启会话，先检查工作目录和
  CLI。它与“重连显示”不同，可用于重新加载更新后的 MCP 配置。
- **终端交互改进**：可靠的多行输入、Codex 历史滚动和返回实时输入，以及
  Terminal／Codex pane 内跨屏选中文字并复制。
- **链接与文件预览**：可选择在 Dashboard 内打开网页，点击终端本地路径进入
  Files 预览；配置文件主机后，也可预览 SSH 终端中的远程文件只读副本。改善换行
  链接识别（包括带长查询参数的 URL），Markdown 预览跟随应用主题。
- **可配置的工作台**：分组设置、深色／浅色／系统主题、面板透明度、界面密度和
  字号、减少动画、统一图标与不同 Agent 的身份徽标。新增工作台控件支持中英文，
  尚非全界面翻译。
- **独立应用与受控更新**：PWA 安装、`siling` CLI，以及先在隔离环境测试指定
  commit、再明确批准应用的更新流程。推送到本 fork 的 `main` 不等于部署。

多 Agent 布局、任务优先级与状态、文件／目录／URL 关联、会话保存与恢复、
Mission Control、远程节点和实验性工作区同步等核心能力继承自 Agent Orchestrator，
并非 SiLing 从零新增。

**当前边界**：UI 改造按阶段推进，手机专用单会话工作流、服务端全局设置编辑器
仍在计划中，详见 [UI/UX 实施状态](docs/uiux-implementation-status.md)。

## Dashboard 概览

![SiLing 通过清晰的 3x2 布局管理六个实时 coding-agent sessions](docs/assets/dashboard-hero.webp)

<p align="center"><sub>在较小屏幕上，3x2 布局仍能让每个 session 清晰可读，同时保留 task 名称、优先级颜色、busy/idle 状态、关联文件和操作按钮。</sub></p>

![SiLing 缩放到十二个实时 coding-agent sessions 的总览](docs/assets/dashboard-overview.webp)

<p align="center"><sub>在更大的屏幕上切换到 4x3，一次查看十二个实时 panes；sidebar 仍然管理全部十六个 sessions。本地路径已统一处理为公开演示内容。</sub></p>

![在多任务 Dashboard 上放大任意一个实时 SiLing session](docs/assets/focus-mode.webp)

<p align="center"><sub>随时放大任意 session，查看完整 TTY 输出和操作；处理完后回到多任务总览，底层工作不会中断。</sub></p>

Codex 和 Claude Code 在单个 terminal 里很强大。真正困难的是同时跑五个、十个
terminal 之后：tab 名称开始失去意义，重要任务埋在窗口里，idle 的 agent 看起来
和 busy 的一样，而一旦关闭窗口，之后可能连这个 session 在哪里都想不起来。

SiLing 把这些 terminal sessions 变成一个可持续恢复、可视化的 task
board。每个 agent 都有自己的名称、优先级、实时状态、workspace、关联文件和
恢复入口。

## Terminal tabs 无法提供的掌控感

| 只使用 terminal | SiLing |
| --- | --- |
| 每个 tab 看起来都差不多 | 为 task 设置容易记住的自定义标签 |
| 紧急任务和普通任务混在一起 | 使用 `P0`、`P1`、`P2` 排序和分组 |
| 无法快速判断“它还在工作吗？” | 直接查看 busy、idle 时长、watching、blocked 和 done |
| 输出在 terminal，task 文件却散落在别处 | 将项目文件夹、单个文件和参考 URL 绑定到 session |
| 关闭 terminal 后失去自己的记忆索引 | 捕获原生 resume metadata，并搜索已结束 sessions |
| 重启后原来的工作区布局消失 | 保存 active sessions，并把支持恢复的任务放回原 pane |

## 所有 coding agents 的统一入口

<p align="center">
  <img src="docs/assets/new-session.webp" width="520" alt="从同一个窗口启动 Cursor Agent、Claude Code 或 OpenAI Codex CLI">
</p>

从同一个窗口启动 Cursor Agent、Claude Code、OpenAI Codex CLI 或纯登录 Shell。
为 task 设置容易记住的标签、选择 workspace，然后直接放进后台 tmux session。
Terminal Session 不会自动确认任何提示，适合手动执行命令。之后 Dashboard 就是
找回这项工作的稳定入口，不再依赖 terminal tab 的标题。

同一个流程既可以创建新 task，也可以恢复已经停止的 session。需要时打开 iTerm；
不需要额外窗口时，则让它留在后台并通过浏览器 TTY 交互。

## 为真实复杂工作准备的指挥中心

从一个专注 pane 到高密度 `4x4`、`5x3` 布局都可以自由选择。上方总览同时展示
十二个 panes，sidebar 管理全部十六个 sessions；需要阅读或介入时，可以切换到
更小的布局，让每个 agent 获得更多空间。

- 使用完整交互式 TTY，或更轻量的纯文本流。
- 不用切换 terminal，就能直接向任意 agent 发送输入。
- 每个 pane 都能放大、重连、停止、关闭或打开关联文件。
- 在不同 slot 之间拖动 task，不会重启底层 session。
- 将 Codex、Claude Code 和 Cursor Agent 放在同一个视图中管理。

浏览器只是控制面；即使关闭页面，后台 tmux sessions 仍会继续运行。

## 一眼看懂优先级和实时状态

<p align="center">
  <img src="docs/assets/priority-status.webp" width="360" alt="P0、P1、P2、blocked、watching 和 done task 分组">
</p>

Sidebar 的目标是在你阅读 terminal 输出之前，先回答“我现在应该看哪里”：

- **P0 — 红色：** 紧急任务，或者正在阻塞关键决策的任务。
- **P1 — 黄色：** 重要且需要持续关注的工作。
- **P2 — 蓝色：** 可以稳定放在后台推进的常规工作。
- **Watching — 绿色：** 正在推进，目前不需要人工介入。
- **Blocked — 紫色：** 等待输入、权限或外部依赖。
- **Done — 弱化/绿色：** 已完成，但仍然保持清晰可识别。

自定义标签会把难记的 session ID 变成 “Auth migration” 或 “Release
automation” 这样的任务名称。Idle badge 会显示 pane 已经安静了多久；busy
检测要求输出持续变化，因此一行偶然的 terminal 噪声不会让 task 看起来一直在
工作。

Pane 边框、优先级标签和 terminal 底部状态会形成统一的视觉语言：先扫描整个
grid 里的红、黄、蓝、绿，再打开真正需要关注的 task。

## 原生生命周期信号与真正有用的通知

Terminal 是否还在输出是重要信号，但它不一定能区分 agent 正在思考，还是已经把
控制权交还给用户。SiLing 可以安装 Claude Code 的原生生命周期 hook，
让 waiting、permission、failure 和 completion 状态统一进入 sidebar 与 Mission
Control timeline：

```bash
siling install-agent-hooks
```

默认 hook 只观察状态，不会批准任何权限。通知会打开对应 session 的完整 TTY
视图；当你查看该 session 时，通知会被确认；同一 session 的新通知会替换旧通知，
不会不断堆积。

自动处理权限是另一个独立的显式选项，只适用于可信的单用户环境。
`--claude-permission-policy siling` 只影响由 SiLing 启动的 Claude
sessions，但它仍然意味着工具请求可以不经人工确认，因此启用前应明确评估风险。

## Terminal 关掉，工作仍然找得回来

Terminal agent 最常见的问题并不是进程崩溃，而是人已经忘了哪个 tab、哪个
目录、哪个 resume command 对应哪个 task。

SiLing 会保留多层恢复信息：

1. 记录 task 标签、agent 类型、workspace、logs 和本地 metadata。
2. 当 agent CLI 暴露原生 session ID 时，自动捕获对应的 Codex、Claude Code
   或 Cursor resume command。
3. **Save active** 保存当前 pane 布局和可以恢复的 active sessions。
4. 机器重启或 Dashboard 重启后，**Restore saved** 会在后台 tmux 中重新创建
   支持恢复的 session，并把它们放回保存时的 slot。
5. 已结束 sessions 仍然可以搜索，并可从创建 session 的流程中恢复。

<p align="center">
  <img src="docs/assets/resume-session.webp" width="488" alt="搜索已经结束的 coding-agent session，并在后台恢复">
</p>

<p align="center"><sub>可以按 task 名称、agent、workspace、model 或原生 resume ID 搜索，然后在后台或 iTerm 中把 session 恢复回来。</sub></p>

由于不同 agent CLI 暴露的 metadata 不完全一致，恢复能力是 best-effort；但
Dashboard 会明确展示这些状态，而不是让它们消失在 terminal scrollback 里。

点击终端里的本地绝对路径或 `file://` 链接，即可在 SiLing Files 中预览，并自动关联
到该终端所属会话，无需 agent 先执行 `link-file`。Codex 显示的“标签（路径）”也支持
点击标签或被缩进拆成多行的路径。文件须存在于会话所在主机且位于
允许目录内；额外目录通过 `ORCH_LINKED_FOLDER_ROOTS` 配置。

Terminal 和 Codex pane 可直接拖选文本，按住鼠标时滚动滚轮即可跨屏扩展选区。
松开鼠标后按 ⌘C（macOS）或 Ctrl+Shift+C 复制完整选区；输入时回到实时末尾。
Option+拖选保留 xterm 当前屏幕内的选择方式。复制依赖 tmux 的 `copy-pipe-no-clear -CP`
支持。Ctrl+拖选可向终端程序
传递鼠标操作。其他 Agent pane 保留原有鼠标行为，macOS 可用 Option+拖选选择文本。
新建或恢复的 Codex session 使用 inline 模式保留终端滚动历史；已有 alternate-screen
session 需要恢复后才使用新启动参数，未存入终端缓冲区的内容无法通过滚动补回。
Codex pane 在浏览 tmux 历史时，开始打字或粘贴会先返回实时终端，再传递输入；
滚动和文本选择仍保留历史视图，方向键等 Escape 序列仍用于历史导航。
通过滚轮进入历史后，向下滚回最新一屏也会自动退出历史模式；自定义 tmux 滚轮绑定保持不变。

## 每个 task 都有自己的 Linked Items

![Linked Items 展示 task workspace、文件树和 Markdown 状态报告](docs/assets/linked-items.webp)

一个 task 不只是 terminal transcript。它通常还有项目文件夹、计划、测试证据、
结果表格、截图和几个参考网页。Linked Items 会把这些上下文直接绑定到 session。

交付 spec 或报告时，运行 `siling link-file /absolute/path/spec.md --label "Spec"`，
用户即可从 pane 的 **Files** 面板打开，无需复制终端里的路径。
终端 HTTP(S) 链接换行后，悬停时会高亮链接的所有可见分段。
CLI 主动换行的裸 HTTP(S) 链接，在缩进一致且接近 pane 行尾时也会拼接；
点击任一段保留完整查询参数，不跨空行或后续说明文字拼接。

- 绑定整个项目或 task 文件夹，直接在 Dashboard 中浏览目录树。
- 当 task 跨越多个位置时，可以单独绑定文件或 URL。
- 预览 Markdown、源码、图片、CSV 数据和报告。
- 可在 **设置 → 浏览与文件 → Open web links inside SiLing** 中选择将 terminal、Markdown
  和 Linked Items 里的 HTTP(S) 链接打开为内嵌 Projects 标签页。
- 可在 **设置 → 外观 → Panel opacity** 中将弹窗和展开面板的背景透明度调整为
  60%–100%；默认完全不透明。
- 让实现笔记、验证证据和发布产出始终靠近产生它们的 agent。
- 几天后恢复工作时，可以快速找回完整上下文。

Dashboard 不会复制一份新的项目。它记住真正的 workspace，让每个 task 都有一个
稳定的入口，方便你持续 track 它的工作和产出。

### SSH 终端里的文件链接

本机 Terminal pane 内执行 `ssh` 时，在该 pane 的 **More** 菜单填写
**SSH 文件主机**，使用已有 SSH 别名（如 `dev-server`）或 `user@hostname`。
设置按会话保存在当前浏览器；退出 SSH 回到本机 shell 后请清空。
点击终端输出的绝对文件路径，会通过 SSH 拉取文件并在 Files 预览，无需重启
终端或 Claude Code。网页链接仍正常打开。

Dashboard 所在机器需要已有免交互 SSH 访问权限和已验证的主机密钥；自定义端口、
跳板机、密钥文件放在 `~/.ssh/config`。远程机需要 `python3`，无需安装 SiLing。
每次点击会刷新会话目录 `ssh-previews/` 中的只读预览副本（最大 16 MiB），
Files 标签显示来源主机与路径。副本可离线查看，不是实时远程挂载，暂不支持目录。
Remote Nodes pane 继续使用节点原有的文件访问方式。

### 工作台外观与操作入口

顶栏保留新建、搜索、布局等常用入口；布局选择器保留十种布局并显示网格缩略图。
保存／恢复会话、排序和关闭所有面板归入「工作区」。关闭面板不会终止会话。

面板标题显示 Agent 图形与名称徽标，旁边保留标记、文件、放大和「更多」。图形是原创的
界面识别符号，不是官方品牌 Logo；常用工具栏、面板及设置导航使用本地 SVG，不依赖图标 CDN。
重连、终端配色、移动／交换位置、关闭面板与终止会话均在「更多」中。Lead 是协调者角色；P0/P1/P2
是优先级；Blocked/Watching/Done 是人工标记。目前仍共用原有字段，选择新标记会替换旧标记。

「更多 → 重启当前 Agent」会在确认后中断选中的 Claude／Codex／Cursor 进程，并用已保存的
原生对话 ID 启动新的后台会话，适合重新加载 MCP 配置；不会更新或重启独立的 MCP 服务。
没有恢复 ID、工作目录无效或找不到 CLI 时，不会停止 Agent；正常退出超时也不会强杀。
CLI 优先从服务 PATH 查找，再检查 `~/.local/bin`；后台启动使用解析后的绝对可执行路径。新的 SiLing run
只替换对应面板，并带入名称、配色、标记、关联文件和下方输入框草稿。终端内未提交的输入和
正在执行的工作可能丢失，建议在任务间隙使用。若退出后启动失败，可从已保存的原会话执行恢复。
远程节点也需要支持此接口；纯 Terminal 面板不提供此操作。「重连显示」仍不会重启 Agent。

「设置 → 外观」可调整跟随系统／深色／浅色主题、界面密度、字号、减少动画和语言。
新增外观与操作控件支持中英文，旧页面尚未全部翻译。这些偏好只保存在当前浏览器，
不会重启会话或改变终端配色。「终端」中的批量配色需显式应用；「通知」管理优先级提醒；
「连接与更新」提供登录地址复制和已有的验证更新流程。地址显示会遮蔽凭据，复制出的
登录链接仍可授予访问权限，只应分享给可信设备。

本批实现范围、验证证据和剩余工作见[实施报告](docs/uiux-implementation-status.md)。
手机单任务模式与服务端设置编辑尚未包含在本批中。

## 快速开始

需要 macOS 或 Linux、`tmux`、Python 3.10+，以及至少一个支持的 agent CLI
（`codex`、`claude` 或 `agent`）。安装 `ttyd` 后即可使用截图中的完整交互式
terminal 体验。

```bash
git clone https://github.com/Vivo50E/SiLing.git
cd SiLing

PYTHON=python3.11  # 可替换为任意已安装的 Python 3.10+
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x siling
mkdir -p ~/.local/bin
ln -sf "$PWD/siling" ~/.local/bin/siling
siling dashboard
```

打开 [http://127.0.0.1:7860](http://127.0.0.1:7860)，创建 session、设置标签和
优先级，然后选择 **Start in Background**。

如果希望单独设置 New Session 的默认 Working dir，而不改变项目浏览根目录，可在
被忽略的 `dashboard.local.json` 中设置 `new_session_working_dir`，或使用
`ORCH_NEW_SESSION_WORKING_DIR`。未设置时会优先使用已有的 `~/Workflows`，否则
沿用 `projects_root`。点击任意空 pane 即可打开 New Session，并把新建 session
直接放入该 pane。

### 在 macOS 上安装为独立应用

Dashboard 内置 Progressive Web App 支持。启动 Dashboard 后，可在 Safari 中选择
**文件 → 添加到程序坞**，或使用 Chrome/Edge 地址栏中的安装按钮。安装后它会以
独立窗口运行，并出现在程序坞、Launchpad 和 Spotlight 中。由于 session 与 TTY
来自本地后端，使用应用前仍需保持 `siling dashboard` 运行；后端不可用时应用会显示
重连页面，而不会展示缓存的旧 session 状态。

`siling` 启动器会沿符号链接找到当前仓库，并自动使用仓库内的 virtualenv。如果
`~/.local/bin` 不在 `PATH` 中，可以在仓库中运行 `./siling`，或把该目录加入 shell
的 `PATH`。

旧的 `orchestrator.py` 入口、`ORCH_*` 环境变量、状态目录和 `orch-*` tmux 名称继续
兼容已有 sessions。

## 一个实用的日常工作流

1. 创建后台 session，并给它一个人能记住的标签。
2. 设置 `P0`、`P1` 或 `P2`，让它自动进入正确分组。
3. 绑定 task 或项目文件夹，让产出始终容易找到。
4. 观察 busy 和 idle 时长，不再反复打开每一个 pane 检查。
5. 只在需要决策、权限或补充信息时向 agent 发送输入。
6. 重启前保存 active sessions；完成后停止任务，同时保留 resume metadata。

## 从 CLI 启动 sessions

```bash
siling run                              # Cursor Agent
siling run claude                       # Claude Code
siling run codex                        # OpenAI Codex CLI
siling run codex investigate /path/to/project
```

浏览器和 CLI 工作流使用相同的本地 sessions 和 metadata。

### 导入使用 SiLing 之前创建的 sessions

在 **New session → Import existing** 中可以扫描 Codex、Claude Code 和 Cursor
Agent 的原生历史记录。搜索或筛选结果后，一次最多选择 100 个 sessions，导入后
它们会出现在 Resume 列表中。导入只在 `outputs/` 下创建 SiLing metadata
索引；原始 transcript 始终保留在原生目录中，不会被复制、移动、编辑或删除。已经
建立索引的原生 session ID 会自动从导入列表隐藏。

## 让一个 agent 把任务委派给另一个 agent

Agent 不需要在发现额外工作后停下来等人手工开窗口。它可以直接从当前
SiLing session 创建一个有独立名称、agent、model、effort、workspace 和
优先级的子任务：

```bash
siling delegate --agent codex --model gpt-5.6-sol --effort high \
  --label dependency-audit --priority p1 \
  --prompt "检查 dependency update，并报告 targeted test evidence。"
```

子任务会立即出现在 Dashboard 中。默认继承父任务的 workspace 和 Linked Items，
但运行在独立的 tmux session。Agent 还可以通过 `siling session` 列出 sessions、按
指定行数读取 TTY 开头或结尾，以及向目标 session 发送 follow-up。完整流程、幂等
自动化与远端节点行为见 [Agent 委派指南](docs/agent-delegation.md)。

### 批准并应用更新

Dashboard 顶部的 **apply update** 会同时发现两类更新：位于独立 Git worktree、
名称以 `agent/self-improve-` 开头的 Agent 候选分支，以及当前分支 Git upstream
上的新 commits。未配置 tracking branch 时，会依次回退到
`origin/<current-branch>` 和 `origin/main`。Dashboard 会在启动时、每五分钟以及
点击按钮时刷新远端引用。

更新要求工作区干净且能够 fast-forward。第一次点击会针对精确候选运行完整测试；
upstream 代码会在临时 detached worktree 中测试，不会提前改变本地文件。测试通过后
按钮变为 **approve update**，第二次点击才执行已验证 commit 的 fast-forward 并
重启 Dashboard。任一 commit 变化都会使批准令牌失效。该流程不会应用未提交代码、
force merge 或 rebase 用户工作。

验证测试及其 Python CLI 子进程统一使用 Dashboard 的 Python 运行环境，即使临时
checkout 中没有 `.venv` 也不例外。验证不会向系统 Python 安装依赖，也不会修改运行中
服务的 PATH。

## 在 macOS 后台常驻

受管安装器会创建隔离运行环境、安装依赖、生成私有 token，并注册用户级
LaunchAgent：

```bash
./launchd/deploy.sh --install  # 首次安装
./launchd/deploy.sh            # 后续代码更新
./launchd/deploy.sh --dry-run  # 预览更新
```

部署时会保留 outputs、关联 projects、证书、本地配置和私有 task recipes。
LaunchAgent 默认只监听 `127.0.0.1`。

常用覆盖项：

```bash
ORCH_PYTHON=/path/to/python3.12 ./launchd/deploy.sh --install
ORCH_DASHBOARD_PORT=9000 ./launchd/deploy.sh --install
ORCH_DASHBOARD_HOST=0.0.0.0 ./launchd/deploy.sh --install
```

## 远程访问

非 loopback bind 强制要求认证。通过 LAN 或 VPN 访问时，应同时使用 token 和
HTTPS：

```bash
ORCH_DASHBOARD_TOKEN=mysecret siling dashboard --host 0.0.0.0 --https
```

URL helper 会检测正在运行的 Dashboard 协议和 bind 地址：

```bash
siling url            # 打印并复制最佳认证 URL
siling url -q         # 只输出 URL
siling url --json     # 检查所有可访问候选地址
```

## 用一个 Dashboard 管理本地和远端 agents

Remote Nodes 让 agent 进程和 tmux session 留在真正执行工作的机器上，同时把它们
呈现在同一个本地 Dashboard 中。Sidebar 会按地点分组；TTY 输入输出通过轻量的
HTTP/WebSocket 控制面转发；即使浏览器或本地 Dashboard 关闭，远端工作仍会继续。

在远端使用 `siling dashboard --node-only` 启动服务，通过 SSH tunnel 连接，然后在
被 Git 忽略的 `dashboard.local.json` 中登记该节点即可。这个能力不要求复制 projects，
也不要求开启 workspace sync。通用双机配置、安全 token、自动 tunnel 和可选的
自助重连方式见 [Remote Nodes 指南](docs/remote-nodes.md)。

## 实验性 workspace sync（默认关闭）

如果你同时使用本机和远端开发服务器，可选的 **sync status** 视图会让切换状态
保持清晰。它分别显示只在本机修改、只在远端修改、两边相同修改，以及真正的
双端冲突。文件系统事件会快速更新本地变化；低频 reconciliation 则用于捕获遗漏
事件并刷新远端状态。

它和 Remote Nodes 是彼此独立的能力；只有在被忽略的本地配置中显式设置
`sync_status.enabled` 后才会启动。状态监控默认只读。**Sync now** 只传输当前安全
的单端新增和更新；**Sync when
idle** 会等受影响的本机与远端 agent workspace 都空闲后再执行。持续 auto sync
还需要再次显式开启，并且默认关闭。冲突、Git refs、超大文件和删除操作都不会被
自动应用。第一次使用应选择较小的 `paths` 并手动建立 baseline，不要直接指向整个
home 目录。

需要快速切换机器时，每个 session pane 都有独立的 **Sync** 操作。它会根据该
session 的工作目录和文件系统 Linked Items 推导出最小有效范围，先展示将要同步的
project 或 task 产物，再只同步这个范围。只有终端仍在持续输出或有后台 shell 工作，
并且映射到同一个 Git project 或 Linked Item 时，相关路径才算 busy；通用的 Projects
根目录不会阻塞无关工作。普通点击会等待这些路径空闲；按住 Shift 点击则立即同步
当前安全的项目。同步排队或运行期间，同一个按钮会变成 **Cancel**。全 workspace
同步仍保留作为兜底。

如果配置了 `remote_code_root`，session 范围的 project sync 通过完整校验后，还会为
Claude Code 和 Codex 发布一份停止状态的 resume handoff。原生 transcript 与 session
metadata 会复制到远端，任务会出现在可恢复列表中，但不会被自动启动。是否真正切换
机器仍由用户明确决定，也不会在后台悄悄启动第二个 agent。

比较 baseline 保存在 project tree 之外的 SiLing 本地状态目录中。复制
[`examples/dashboard.local.json`](examples/dashboard.local.json)，选择需要跟踪的
workspaces；确认两台机器使用相同 SiLing revision 后，再启用
`sync_status`。

## Local-first 安全模型

SiLing 可以向本地 terminal sessions 发送输入，应当把它视为一个
高权限开发者工具。

- 默认只监听 localhost。
- 非 loopback 访问必须使用 token。
- Token 保存在 tracked source tree 之外，并使用仅当前用户可读的权限。
- Runtime 数据保留在本机，其中可能包含 prompts、transcripts、本地路径和
  resume metadata。
- 绝不要发布 `outputs/`、`projects/`、`.dashboard-certs/`、本地配置或私有
  task recipes。

部署和漏洞报告说明见 [SECURITY.md](SECURITY.md)，开发检查和贡献指南见
[CONTRIBUTING.md](CONTRIBUTING.md)。

## 当前范围

Dashboard-first 是主要支持的体验。由于各 agent CLI 暴露的 session metadata
不同，resume 能力是 best-effort。项目面向可信的本地开发者机器，而不是托管式
多用户部署。旧版 YAML recipe runner 仍为高级用户保留。

SiLing 采用 [MIT License](LICENSE)。
