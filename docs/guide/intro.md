# OpenHarness 项目简介

> 本文只总结 OpenHarness 核心工程能力，不涵盖 `.openharness/` 下的具体插件实现。

## 项目定位

OpenHarness 是一个开源的 **AI Agent Harness（智能体运行底座）**。它将大语言模型接入、Agent 执行循环、工具调用、权限治理、上下文与记忆、多 Agent 协作和终端/消息渠道交互统一封装，主要用于构建类似 Claude Code 的本地编码助手，也可作为通用 Agent 应用的运行时基础。

从分层视角看，OpenHarness 不只是聊天客户端：它负责让模型在可控边界内理解项目上下文、调用工具、执行任务、保存状态、协作分工，并以 CLI、终端 UI、自动化任务或 IM 消息等形式对外提供服务。

## 核心能力

### 1. Agent 执行循环

OpenHarness 提供面向工具调用的 Agent Loop：

- 向模型传递系统提示词、会话上下文和工具定义；
- 接收流式文本与工具调用；
- 执行工具并将结果回灌给模型；
- 反复执行直至任务完成或到达回合上限；
- 支持重试、指数退避、Token 统计和成本追踪。

核心实现位于 `src/openharness/engine/`，其中 `QueryEngine` 负责保存对话历史、协调模型调用、权限检查、Hook 和会话级状态。

### 2. 多模型与 Provider 工作流

项目将模型配置抽象为 **workflow + profile**，而非单一 API Key。使用者可以通过统一配置和切换流程接入不同模型及认证方式。

支持的主要接入方式包括：

- Anthropic 风格 API；
- OpenAI 兼容 API；
- Claude、Codex 等本地订阅凭据复用；
- GitHub Copilot OAuth；
- 云端网关、本地模型服务和自定义兼容接口。

Provider 注册表覆盖 Anthropic、OpenAI、DeepSeek、Gemini、Qwen/DashScope、Kimi、GLM、MiniMax、Groq、Mistral、Bedrock、Vertex、Ollama、vLLM 等代表性后端。相关模块位于 `src/openharness/api/`、`src/openharness/auth/` 和 `src/openharness/config/`。

### 3. 面向代码任务的工具箱

OpenHarness 内置可由 Agent 调用的本地与外部工具，覆盖常见的软件工程工作流：

- 文件读取、写入、精确编辑、Glob 和文本搜索；
- Shell 命令执行；
- Git worktree 管理；
- LSP 代码智能；
- Jupyter Notebook 编辑；
- Web 搜索与网页抓取；
- 图像生成与图像识别；
- 用户澄清问答；
- MCP 工具、资源和认证；
- 任务、日程、Agent 与团队管理。

实现集中在 `src/openharness/tools/`。这使其既可作为本地仓库感知的编码助手，也可以充当其他 Agent 应用的工具执行底座。

### 4. Skills、插件、命令与 MCP 扩展

OpenHarness 提供多种扩展机制：

- **Skills**：Markdown 形式的按需加载能力说明和工作流；
- **Plugins**：可扩展 skills、命令、Agent 与 MCP server；
- **Slash Commands**：内建及插件提供的交互命令；
- **MCP**：支持 MCP server 配置、工具调用、资源读取和认证。

对应实现位于：

- `src/openharness/skills/`
- `src/openharness/plugins/`
- `src/openharness/commands/`
- `src/openharness/mcp/`

其中的插件能力是指 OpenHarness 的通用插件框架，不涉及本仓库 `.openharness/` 下具体插件的业务功能。

### 5. 项目上下文、会话与持久记忆

项目提供从当前会话到长期项目记忆的状态管理能力：

- 自动发现和注入 `CLAUDE.md`；
- 使用 `MEMORY.md` 和 Markdown 文件维护持久记忆；
- 会话保存与恢复；
- 长上下文自动压缩；
- 可选的自动记忆提取与后台记忆整合；
- 基于文件锁和原子写入的记忆文件管理。

主要模块包括 `src/openharness/prompts/`、`src/openharness/memory/`、`src/openharness/services/session_memory/`、`src/openharness/services/memory_extract/` 和 `src/openharness/services/autodream/`。

### 6. 权限治理、Hook 与沙箱

作为 Harness，OpenHarness 特别封装了 Agent 执行过程的约束与治理能力：

- 多级权限模式；
- 工具调用前的交互式确认；
- 路径与命令规则；
- Hook 事件、执行器和热重载；
- Docker 隔离执行环境；
- `oh --dry-run` 静态预检。

Docker 沙箱可限制 CPU、内存、挂载和环境变量；当前实现默认关闭容器网络。Dry-run 会解析配置、认证、提示词、Skills、命令、工具及 MCP 配置，输出 `ready`、`warning` 或 `blocked` 结论，但不会调用模型、执行工具、启动 subagent 或连接 MCP server。

主要实现位于 `src/openharness/permissions/`、`src/openharness/hooks/`、`src/openharness/sandbox/` 与 `src/openharness/cli.py`。

### 7. 多 Agent 协作与后台任务

OpenHarness 提供轻量多 Agent 编排原语：

- Subagent 启动；
- in-process 与 subprocess 两类后端；
- Agent 注册表与协调器模式；
- 团队生命周期、成员状态和消息邮箱；
- Git worktree 隔离；
- 权限同步；
- 后台 Shell Task 与 Local Agent Task；
- 任务创建、状态查询、结果读取和停止控制。

相关模块位于 `src/openharness/swarm/`、`src/openharness/tasks/`、`src/openharness/coordinator/` 和 `src/openharness/bridge/`。

### 8. CLI、终端 UI 与自动化输出

项目提供多种交互和集成方式：

- `oh` 命令行入口；
- 交互式终端会话；
- React 终端 UI；
- 单次非交互 Prompt 执行；
- JSON 与 stream-json 输出，便于脚本或 CI 消费；
- 主题、输出风格、键绑定与 Vim 模式；
- 语音输入相关能力。

主要路径为 `src/openharness/cli.py`、`src/openharness/ui/`、`frontend/terminal/`、`src/openharness/keybindings/`、`src/openharness/themes/`、`src/openharness/output_styles/`、`src/openharness/vim/` 和 `src/openharness/voice/`。

### 9. 定时调度与仓库自动化

OpenHarness 还包含面向持续运行场景的自动化能力：

- Cron 任务的创建、启停、查询、执行历史和日志；
- 调度器守护进程；
- 仓库 Autopilot 服务；
- 对应的 Dashboard 前端工程。

相关模块为 `src/openharness/services/cron.py`、`src/openharness/services/cron_scheduler.py`、`src/openharness/autopilot/` 与 `autopilot-dashboard/`。

### 10. `ohmo` 个人 Agent 应用

仓库中的 `ohmo` 是构建在 OpenHarness 核心之上的 personal-agent app，而不是核心的一种简单运行模式。

它提供：

- 独立 workspace 初始化；
- 人格、身份、用户信息和个人记忆文件；
- 基于 provider profile 的 Agent 运行时；
- Gateway 守护服务；
- 多渠道消息接入与会话复用；
- Telegram、Slack、Discord、Feishu 等渠道的配置与运行支持。

对应代码位于 `ohmo/`、`ohmo/gateway/` 和 `src/openharness/channels/`。

## 能力分层

| 层级 | 主要封装能力 |
| --- | --- |
| 模型层 | 多 Provider、多协议、API Key/OAuth/订阅凭据、Profile 切换 |
| Agent 内核 | 流式 Agent Loop、工具调用、上下文控制、成本追踪、重试 |
| 工具层 | 文件、Shell、Git/Worktree、LSP、Web、MCP、图像、Notebook 等 |
| 扩展层 | Skills、Plugins、Slash Commands、MCP Servers |
| 状态层 | `CLAUDE.md`、项目记忆、会话恢复、自动压缩、记忆提取 |
| 治理层 | 权限、审批、Hook、路径规则、Docker Sandbox、Dry-run |
| 协作层 | Subagent、团队、任务、后台进程、协调器、Worktree 隔离 |
| 交互层 | CLI、React TUI、JSON/stream-json、主题、键绑定、Vim、语音 |
| 自动化层 | Cron、Autopilot、后台任务与 Dashboard |
| 应用层 | `ohmo` 多渠道个人 Agent Gateway |

## 结论

OpenHarness 的核心价值是提供一个通用、可扩展、可治理的 Agent 运行底座：模型可以被替换，工具可以被扩展，执行可以受权限和沙箱约束，上下文可以跨会话积累，复杂任务可以拆分给多个 Agent，最终又能通过 CLI、终端 UI、自动化任务或即时消息渠道交付给使用者。

其当前最直接的应用形态是类似 Claude Code 的本地编码 Agent；从模块构成看，它也具备承载个人助理、IM Bot、仓库自动化和多 Agent 工作流的基础能力。
