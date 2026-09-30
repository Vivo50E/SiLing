<div align="center">

# 司令 · SiLing

**一个工作台，掌握所有编程 Agent。**

**One workbench for all your coding agents.**

[![CI](https://github.com/Vivo50E/SiLing/actions/workflows/ci.yml/badge.svg)](https://github.com/Vivo50E/SiLing/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![macOS and Linux](https://img.shields.io/badge/macOS%20%7C%20Linux-local--first-24292f)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文](#中文) · [English](#english) · [中文完整指南](README_CN.md) · [Full English guide](README_EN.md)

</div>

![司令 / SiLing — 多 Agent 工作台 / Multi-agent workbench](docs/assets/dashboard-hero.webp)

## 中文

### 司令是什么？

**司令（SiLing）**是本地优先的多 Agent 工作台，将 Claude Code、OpenAI Codex、
Cursor Agent 和普通终端放到同一个 Dashboard。用多面板布局、项目分组、任务状态和
关联文件组织工作，不再靠一堆终端标签记住每项任务。

浏览器只是控制界面：关闭页面不会停止后台 tmux 会话。
应用中文名为「司令」，英文名、仓库名保留 `SiLing`，命令仍为 `siling`。

### 基于什么项目？

本项目 fork 自 [YAMY1234 / Agent Orchestrator](https://github.com/YAMY1234/agent-orchestrator-public)，
在 [Vivo50E/SiLing](https://github.com/Vivo50E/SiLing) 独立维护。感谢原作者和贡献者。

多 Agent 布局、任务优先级与状态、文件／目录／网页关联、会话保存与恢复、Mission Control、
远程节点和实验性工作区同步等基础能力继承自上游，不是司令从零新增。

### 司令新增与改进的功能

- **会话管理**：纯终端会话、导入已有 Agent 对话、可配置的默认工作目录、点击空面板创建会话。
- **单独重启 Agent**：使用保存的原生对话标识恢复支持的会话，可重新加载 MCP 配置；
  “重连显示”不会重启 Agent，重启 Agent 也不会更新独立 MCP 服务。
- **终端交互**：改进多行输入、历史滚动、返回实时输入，以及 Terminal／Codex／Cursor 的跨屏选中复制。
- **链接与文件**：改进长链接和换行链接识别，可在内部打开网页；点击终端路径预览文件，
  支持配置后的 SSH 远程文件只读副本，Markdown 预览跟随主题。
- **项目分组**：自定义颜色、单个／批量归组，筛选不重启终端；同一 Dashboard 的设备共享分组信息。
- **界面与设置**：中英文切换、深浅主题、面板透明度、密度、字号、统一图标和 Agent 身份徽标。
  Agent 输出、用户内容和后端原始错误不翻译。
- **独立应用与受控更新**：支持 PWA 安装和 `siling` CLI；更新先验证指定提交，再明确批准应用。
  推送到 `main` 不等于部署。
- **可核对的运行版本**：在 **设置 → 关于司令** 查看版本号和 Git 提交标识；每次提交更新后
  构建标识自动变化，服务重启后才反映新版本。

### 快速开始

需要 macOS 或 Linux、Python 3.10+、`tmux`；完整交互终端需安装 `ttyd`。
启动编程 Agent 前，请先安装并登录对应 CLI（`claude`、`codex` 或 `agent`）。

```bash
git clone https://github.com/Vivo50E/SiLing.git
cd SiLing
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python orchestrator.py dashboard
```

请确认 `python3` 为 3.10 或更新版本。打开 [http://127.0.0.1:7860](http://127.0.0.1:7860)，
创建会话并在后台启动。语言可在 **设置 → 外观 → 语言** 中调整。
CLI 安装、后台常驻、恢复会话与远程节点配置见[中文完整指南](README_CN.md)。

### 安全与路线图

司令可以向终端发送命令，应视为高权限开发工具。默认仅监听本机；远程访问需认证与
HTTPS，不要直接将未受保护的服务暴露到公网。不要公开令牌、会话记录或 `outputs/`。
会话恢复取决于各 Agent CLI 提供的元数据，并非所有任务都能完整恢复。

[Roadmap #1](https://github.com/Vivo50E/SiLing/issues/1) 记录 Subagent 协作、MCP 管理、
多设备协同、安全公网访问、外部工具集成和移动端体验等后续计划；**计划不代表已经实现**。

[安全说明](SECURITY.md) · [贡献指南](CONTRIBUTING.md) · [UI/UX 规格](docs/uiux-improvement-spec.md) · [MIT 许可证](LICENSE)

### 开发与项目结构

从[文档导航](docs/README.md)和[架构地图](docs/architecture/README.md)开始。
`make map` 输出机器可读的组件目录，`make verify PYTHON=.venv/bin/python`
执行与 CI 相同的结构、语法及完整测试检查。开发工具位于 `tools/`，与 `scripts/`
中的会话运行脚本分离；现有启动入口和数据路径保持兼容。

---

## English

### What is SiLing?

**SiLing (Chinese name: 司令)** is a local-first workbench for Claude Code,
OpenAI Codex, Cursor Agent, and ordinary terminals. Organize work with pane
layouts, project groups, task states, and linked files instead of relying on
terminal tab titles.

The browser is only the control surface: background tmux sessions keep running
when you close the page. The English name and repository remain `SiLing`;
the command remains `siling`.

### Where does it come from?

SiLing is an independently maintained fork of
[YAMY1234 / Agent Orchestrator](https://github.com/YAMY1234/agent-orchestrator-public),
developed in [Vivo50E/SiLing](https://github.com/Vivo50E/SiLing).
Thanks to the original authors and contributors.

Multi-agent layouts, task priorities and states, linked files/folders/URLs,
session save/restore, Mission Control, remote nodes, and experimental workspace
sync come from the upstream foundation, not new work built from scratch here.

### What this fork adds

- **Session management:** Terminal-only sessions, import of native Agent conversations,
  configurable default working directories, and session creation from empty panes.
- **Individual Agent restart:** resume supported sessions with their saved native
  conversation identity to reload MCP configuration. Reconnecting the display does
  not restart the Agent; restarting the Agent does not update independent MCP servers.
- **Terminal interaction:** improved multiline input, scrollback, return to live input,
  and cross-screen selection/copying in Terminal, Codex, and Cursor panes.
- **Links and files:** improved long and wrapped links, optional internal web browsing,
  clickable terminal file paths, configured SSH read-only file snapshots, and themed
  Markdown previews.
- **Project groups:** custom colors, individual/bulk assignment, and filtering without
  restarting terminals. Devices connected to the same Dashboard share group metadata.
- **Interface and settings:** English/Chinese controls, light/dark themes, panel opacity,
  density, text size, consistent icons, and Agent identity badges. Agent output,
  user content, and raw backend errors remain unchanged.
- **Installable app and controlled updates:** PWA installation and the `siling` CLI;
  updates verify a specific commit before explicit approval. Pushing to `main`
  does not deploy it.
- **Visible running version:** **Settings → About SiLing** shows the version and Git
  commit. Each committed update gets a distinct build suffix, reflected after the service restarts.

### Quick start

Requires macOS or Linux, Python 3.10+, and `tmux`. Install `ttyd` for full
interactive terminals. Install and authenticate the corresponding CLI (`claude`,
`codex`, or `agent`) before starting a coding Agent.

```bash
git clone https://github.com/Vivo50E/SiLing.git
cd SiLing
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python orchestrator.py dashboard
```

Ensure `python3` is version 3.10 or newer. Open
[http://127.0.0.1:7860](http://127.0.0.1:7860), create a session, and start it in
the background. Choose a language in **Settings → Appearance → Language**.
See the [full English guide](README_EN.md) for CLI installation, background
services, session recovery, and remote-node configuration.

### Safety and roadmap

SiLing can send commands to terminals: treat it as a privileged developer tool.
It binds to localhost by default; remote access needs authentication and HTTPS.
Do not expose an unprotected service to the public internet or publish tokens,
transcripts, or `outputs/`. Recovery is best-effort and depends on each Agent CLI's
native metadata.

[Roadmap #1](https://github.com/Vivo50E/SiLing/issues/1) tracks Subagent collaboration,
MCP management, multi-device workflows, safe public access, external integrations,
and mobile UX. **Planned features are not claims of current support.**

[Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [UI/UX spec](docs/uiux-improvement-spec.md) · [MIT License](LICENSE)

### Development and repository structure

Start with the [documentation index](docs/README.md) and
[architecture map](docs/architecture/README.md). `make map` prints the validated
component catalog; `make verify PYTHON=.venv/bin/python` runs the same structure,
syntax and full-suite checks as CI. Developer tooling in `tools/` is separate
from session-runtime scripts in `scripts/`; existing entrypoints and data paths remain compatible.
