# 第二章：多模型与 Provider 工作流

> 本章对应 [项目简介](intro.md) 的“2. 多模型与 Provider 工作流”。重点是让模型选择、认证方式和调用协议可以独立演进。

## 1. 从“填 API Key”到工作流

同一个 Agent 可能需要云端模型、本地模型、企业网关或订阅凭据。若运行时直接绑定某个 SDK 和 API Key，切换模型会侵入业务逻辑。OpenHarness 将这部分拆成 **workflow** 与 **profile**：前者描述接入/认证流程，后者保存某套可选的连接配置；Agent 运行时只消费已解析出的模型客户端。

这种分层适用于在 Claude、OpenAI 兼容接口、Copilot OAuth、本地 Ollama/vLLM 或网关之间切换，也便于让不同项目、不同会话选择不同 profile。

## 2. 组件划分

- `src/openharness/config/`：读取和校验设置、解析配置路径；
- `src/openharness/auth/`：认证流、凭据管理与存储；
- `src/openharness/api/`：Provider 元数据、客户端和用量模型；
- `src/openharness/api/registry.py`：Provider 注册表，是 Provider 识别和默认连接信息的集中来源；
- `src/openharness/api/client.py`、`openai_client.py`、`codex_client.py`、`copilot_client.py`：将不同后端适配到统一的流式消息调用能力。

## 3. 工作流程

1. 使用者选择或配置 profile，提供模型、base URL、认证来源等信息；
2. 配置层加载并解析 profile，认证层按 workflow 获取 API Key、OAuth token 或可复用订阅凭据；
3. Provider 注册表依据模型名、密钥前缀或 base URL 等信号匹配候选 Provider；
4. 运行时按 `backend_type` 创建适配客户端；
5. `QueryEngine` 只面对统一的流式消息接口，持续获取模型文本、工具调用和用量。

## 4. 实现原理

`ProviderSpec` 是不可变的 Provider 描述，包含名称、模型关键字、环境变量名、默认 URL、后端类型及本地/网关/OAuth 等分类标记。注册表的顺序也具有语义：网关和云端特征优先参与匹配，避免泛化的模型关键字抢先命中。

后端差异被压缩在 API 适配层。例如原生 Anthropic 调用、OpenAI 兼容 REST 调用和 Copilot OAuth 的认证与请求格式不同，但都要向上层提供可流式消费的消息能力。这样 Agent Loop 无需为每个厂商复制工具循环、权限处理或 UI 事件逻辑。

认证信息应由认证/存储层管理，不能把 token 写入提示词、会话记录或文档样例。Provider 识别只解决“走哪个适配器”，不保证远端服务可用；网络、配额、模型权限和组织策略仍可能导致调用失败。

## 5. 实践建议

- 用 profile 表达用途，例如“本地低成本测试”“生产云端模型”，避免频繁修改全局配置；
- 对 OpenAI 兼容服务同时确认模型名与 base URL，避免错误路由；
- OAuth 凭据需要考虑刷新和失效，不能等同永久 API Key；
- 本地 Provider 减少数据外发，但仍需评估本机服务、上下文窗口和工具执行权限；
- 切换模型后应重新检查工具调用能力、上下文限制与成本预期。

## 6. 源码入口与关联章节

- `src/openharness/api/registry.py`：ProviderSpec 和匹配信号；
- `src/openharness/api/provider.py`：Provider 解析相关逻辑；
- `src/openharness/auth/flows.py`、`manager.py`、`storage.py`：认证生命周期；
- `src/openharness/config/schema.py`、`settings.py`：设置结构与加载。

统一客户端最终服务于[第一章的执行循环](chapter1.md)；渠道应用中的 profile 复用见[第十章](chapter10.md)。
