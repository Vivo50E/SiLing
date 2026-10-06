# UI/UX 实现基线与需求追踪

审阅日期：2026-10-05。代码基线：`458765b37091f544a899fec808a1a6466c6d3b34`。
当前需求：[spec.md](spec.md)。本页不把源码存在等同于完整验收。

## 为什么重整

旧规格的“当前实现”仍描述统一身份、分类设置等缺失，但这些已有代码和回归测试；
2026-09-28 报告的 239 项测试只是当时记录。现状、目标与历史证据混用，会让后续 agent
重复开发已存在的能力，或把阶段 A 当成整个 UI/UX 已完成。

新规格将用户需求与技术证据分离，保留既有边界，不为满足模板虚构实现计划。
原文可从[迁移前固定版本](https://github.com/Vivo50E/SiLing/blob/458765b37091f544a899fec808a1a6466c6d3b34/docs/uiux-improvement-spec.md)查看。

## 旧编号 → 当前需求 → 实际缺口

“部分覆盖”仅说明列出的实现/测试覆盖一部分；“计划”不是已交付；“待验收”表示没有本轮端到端证据。

| 原规格 | 新需求 / 故事 | 现有证据 | 剩余工作与状态 |
| --- | --- | --- | --- |
| NAV-01 | FR-001、US1 | [Dashboard](../../static/index.html)、[分组](../../static/pane-groups.js)、[分组测试](../../tests/test_pane_groups.py) | 工作区/搜索/分组已有；统一组合筛选、布局收藏及全部宽度验收仍需补齐。部分覆盖。 |
| PANE-01 | FR-002/003/004/006、US1 | [UI 基础](../../static/ui-foundation.js)、[UI 测试](../../tests/test_ui_foundation.py)、[浏览器脚本](../../tests/ui_browser.mjs) | 窄标题/菜单/空槽创建/响应后落位已有；请求期间预占位、未知结果重试及完整竞争场景需验证/补齐。部分覆盖。 |
| ARCHIVE-01（本地增量） | FR-027/028/029、US1-A8/A9/A10、SC-011 | [归档计划](archive-plan.md)、[共享状态](../../agent_orchestrator/session_archives.py)、[归档界面](../../static/session-archives.js) | 持久化本机会话的逐记录归档、共享状态、草稿保护、已归档输出/Files 和取消归档；与关闭、停止、`organize` 和 legacy 日志分类独立。远端/临时 tmux/legacy 明确拒绝，真机与完整 SC-011 尚待验收。 |
| VISUAL-01 | FR-023/024/026、US6 | [样式](../../static/ui-foundation.css)、[语言目录](../../static/ui-messages.js)、[UI 测试](../../tests/test_ui_foundation.py) | 深浅主题、密度、字体、原生 SVG 图标、语言和偏好已有；跨所有首方页面的语言/对比度/触控尺寸仍待验收。不是重新选图标库。 |
| AGENT-01 | FR-022、US6 | [agentBadge](../../static/ui-foundation.js)、[未知名称/图标测试](../../tests/test_ui_foundation.py)、[历史美化报告](../../docs/uiux-visual-polish.md) | 已有五种形状及安全名称回退；全部展示位置一致性待验收。原文建议 Lucide 不再作为新增依赖要求。 |
| STATE-01 | FR-010/013、US3 | [生命周期投影](../../agent_orchestrator/session_lifecycle.py)、[生命周期测试](../../tests/test_session_lifecycle.py)、[重启测试](../../tests/test_agent_restart.py) | 执行/连接/来源/时间/尝试链路已有；人工角色/优先级/标记仍共享 `panel_state`。展示可分开，持久化仍互斥；不能宣称数据迁移已完成。 |
| STATE-02 | FR-011/012、US3 | [原生活动](../../agent_orchestrator/native_activity.py)、[活动测试](../../tests/test_native_activity.py)、Dashboard 现有提醒 | 原生观察和提醒不等于统一待处理中心或 300 秒心跳契约；统一事件确认、过期检查属于计划。 |
| RESOURCE-01（新增） | FR-030/031/032/033、US3-A6/A7/A8/A9、SC-012/013 | [主机采集](../../agent_orchestrator/resources.py)、[资源界面](../../static/resources.js)、[测试](../../tests/test_resources.py)、[首批计划](resource-plan.md) | 本机 CPU/内存/Swap/产出与项目卷概览、认证缓存及过期提示为首批切片；不修改公开 health。会话排行、远端汇总、原生内存压力、计数/趋势、告警和设置仍待实现，SC-012/013 未整体验收。 |
| MOBILE-01 | FR-007、US2 | [手机控制器](../../static/mobile-reader.js)、[计划](plan.md)、[测试](../../tests/mobile_browser.mjs) | 2026-10-05 增量新增列表 → 单会话只读 → 返回、单个显式终端、时间/来源/截断证据与桌面状态隔离；真机验收仍待完成，不等于整个 US2 完成。 |
| MOBILE-02 | FR-008/009/026、US2 | [终端按键测试](../../tests/test_terminal_keys.py)、[浏览器样本](../../tests/ui_browser.mjs) | 输入基础不代表软键盘、安全区、草稿隔离和未知发送结果全链路通过。计划/待真机验证。 |
| FILE-01 | FR-014/015/016、US4 | [产出契约](../../agent_orchestrator/artifacts.py)、[产出测试](../../tests/test_artifacts.py)、[SSH Files 测试](../../tests/test_ssh_files.py)、[Markdown 对比度记录](../../docs/markdown-preview-contrast.md) | 用途、来源和验证状态已有；手机列表/详情导航和六类资源矩阵待验收。 |
| SETTINGS-01 | FR-017/018/020、US5 | Dashboard 设置分组、[偏好测试](../../tests/test_ui_foundation.py)、[版本测试](../../tests/test_version.py) | 不是“仅链接模式/透明度”；已有多分组、插件/About。搜索、完整作用域/来源呈现、分组重置仍待补齐。 |
| SETTINGS-02 | FR-019/020、US5 | [本地配置](../../agent_orchestrator/local_settings.py)、[安全测试](../../tests/test_dashboard_security.py) | 单项配置已有，不等于通用服务设置编辑器。白名单/原子保存/远端路径验证需独立安全设计。计划。 |
| FEEDBACK-01 | FR-009/013/021、US2/3/5 | [更新测试](../../tests/test_self_update.py)、[重启测试](../../tests/test_agent_restart.py)、[桌面指南](../../docs/desktop-browser.md) | 验证/批准/应用和桌面在线更新已有；所有窄屏错误与未知结果交互待验收，不重新设计更新器。 |
| A11Y-01 | FR-025/026、US6 | UI 按钮名称测试、Dashboard 设置焦点管理 | 局部行为已有；全弹窗焦点/嵌套 Escape/非拖动移动/真机触控不做完成声明。 |
| 前置终端回归 | FR-005、US1 | [交互测试](../../tests/test_pane_interactions.py)、[终端浏览器测试](../../tests/terminal_browser.mjs)、[长链接回归](../../tests/terminal_links.cjs) | 保留 Terminal 复制、Codex 新建/恢复输入/历史、滚到底退出、长标题、完整 URL 与可打开 spec；每次相关 UI 改动重新验收。 |

## 阶段与实施建议

旧 A/B/C 保留为历史分期，不作为完成度百分比。A 的已有视觉/设置/面板基础映射到 US1/5/6；
B 对应 US2/4；C 对应 US3 和 US5 的服务配置部分。

2026-10-05 用户明确要求开始实施，已选择 **US2 的“手机列表 → 单会话只读输出 → 返回”**
切片，并保留显式终端入口。实施前代码基点为 `ba39252`；不捎带新的监控中心或通用服务配置。

用户随后要求插入 Archive 需求：下一候选切片为 **US1-A8/A9/A10 手动会话归档**，桌面优先、手机兼容。
用户随后确认实施；归档增量使用独立 archive-plan/validation。现有 plan/tasks/validation
仍只证明手机阅读切片，不计入归档完成度。已确认“归档不停止 Agent”和同一 Dashboard 共享作用域。

用户又补充 **US3-A6–A9 多会话资源压力监控**：与归档分开排期，先交付主机只读指标/新鲜度，
再验证占用归属和告警。不能用“归档”代替释放进程资源，也不能把 5 分钟任务心跳当作资源采样。
首批采用 5 秒采样、2 秒子进程超时、15 秒过期；见[独立实施计划](resource-plan.md)。
仅在隔离开发环境验证采集，没有更新运行服务或做完整负载压测；告警和开销预算仍待后续验收。

选定切片后才运行 `$speckit-plan` → `$speckit-tasks` → `$speckit-analyze`；
每项任务关联 FR/US/SC 与行为测试。原有契约和数据结构作为研究输入，不把全项目推倒重写。

## 验证证据层级

1. 自动回归：`make verify`，记录解释器、数量、失败/跳过及候选提交。
2. Dashboard 行为：隔离样本的桌面/手机尺寸检查，不等于真实移动浏览器。
3. 真实终端：自建 Terminal、Claude、Codex 新建/恢复会话检查；不得停止用户任务。
4. 移动真机：iOS Safari/PWA、Android Chrome，记录设备/系统/浏览器、软键盘、旋转、离线重连证据。
5. 性能：相同硬件/网络/会话数，记录连接数、内存、输入延迟前后数据；无数据不报提升。

每次变更只把有证据的范围标成完成。最终报告另列已实现但未验收和未实现项，并提供回滚方法。
