# Spec Kit plugin

SiLing includes an optional, disabled-by-default adapter for [GitHub Spec Kit](https://github.com/github/spec-kit). Open **Settings → Plugins → Spec Kit** to enable it. The switch is stored on the Dashboard host and shared by its clients. Disabling it prevents new plugin launches; sessions already created continue normally.

1. Enter an **absolute project directory on the Dashboard host**. SSH pane paths and remote-node projects are not supported by this first adapter.
2. Select Claude, Codex, or Cursor. The corresponding agent must be installed and usable by SiLing. Claude projects need the normal workspace-trust acceptance before delegation.
3. Select **Setup / repair missing files** for a project without Spec Kit. Setup is an agent task, not an automatic installation inside the Dashboard: it checks the official instructions and CLI flags, uses a project-local environment if needed, initializes staging files, and is instructed to copy only missing files. Review its changes and resolve any reported conflicts before continuing. Existing configuration must not be overwritten.
4. Click **Check project and preview prompt**, review the exact prompt, then **Start reviewed stage**. Open the resulting session from Sessions and attach it to an empty pane. This uses your selected agent's account and can modify the project.
5. After setup finishes, check the project again. Select a stage such as Constitution, Specify, Clarify, Plan, Tasks, Analyze, Checklist, or Implement. Supply the feature description or feature path in **Stage request**. Each click starts one stage in a new session; it does not automatically run subsequent stages.

Current agent skill layouts and older `speckit.*` command/prompt layouts are detected. A missing stage blocks launch and points you back to Setup. The preview is invalidated when the project, agent, stage, or request changes. Previewing never runs Specify or writes project files. The CLI indicator reports host-PATH availability, not the success of initialization; installed stage files are checked separately.

The agent is asked to register generated documents in that session's **Files** using `siling link-file --purpose deliverable`. Registration is performed by the agent and may fail; its report should include the actual paths. Files are not fabricated from expected filenames. Review the resulting spec, plan, and tasks before explicitly choosing Implement.

Launch requests have persistent idempotency receipts. Retrying the same request does not create another session. If a launch is interrupted or fails after its receipt is written, check Sessions before preparing a new launch. A created session means the agent was started and its prompt queued, not that the stage has completed successfully.

This release supplies one bundled adapter; it is not an arbitrary third-party plugin loader or a replacement for Spec Kit's own workflow engine. It does not install a Claude marketplace plugin. The Dashboard has no new Python dependency on Spec Kit. Updating the Dashboard provides this adapter's code; each project manages its own Spec Kit installation separately.

## 中文

在 **设置 → 插件 → Spec Kit** 启用。开关保存在 Dashboard 服务端；关闭只阻止新的插件启动，不会终止已有会话。

填写 Dashboard 所在机器上的绝对项目路径，选择 Claude／Codex／Cursor。尚未初始化时选择「初始化／补齐缺失文件」，点击「检查项目并预览提示词」，审阅后点击「启动已审阅阶段」。从会话列表打开新会话，查看初始化结果并处理冲突。初始化由 Agent 执行，可能下载依赖；提示词要求使用项目内独立环境和临时目录，只补齐缺失文件。请审阅实际文件改动。

初始化完成后重新检查，再依次选择项目原则、需求规格、澄清需求、技术方案、任务拆解等阶段。需求框可以填写功能描述和目标 feature 路径。每次只启动所选阶段，不自动进入下一阶段；选择实施前先审阅文档。插件要求 Agent 将生成文档关联到 Files，并报告关联失败及真实路径。

本版仅支持本机项目，不支持直接填写 SSH 远程路径。预览是只读操作；实际执行使用现有 Agent 账号并可能修改项目。启动失败或响应不确定时，先检查会话列表，再重新预览和启动，避免重复工作。插件与项目里的 Spec Kit 分开更新；这不是 Claude 插件市场插件。
