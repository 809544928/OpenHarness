# OpenHarness PaaS 智能客服插件设计

## 1. 范围与职责边界

[`paas-customer-service`](../../.openharness/plugins/paas-customer-service) 是一个 OpenHarness 项目插件，用于对客服平台传入的 PaaS 服务咨询进行预处理。插件元数据位于 [`plugin.json`](../../.openharness/plugins/paas-customer-service/plugin.json)：插件加载 `skills/` 中的业务规则以及 `tools/` 中的工具实现。

插件当前处理三类场景：

| 场景 | 含义 |
|---|---|
| `access_docs` | 用户咨询服务接入、调用、配置、文档或 demo。 |
| `service_error` | 用户反馈接口报错、超时、状态码、认证问题或服务异常。 |
| `other` | 非 PaaS 处理范围、无关或无法安全处理的问题。 |

Java 上游与插件的职责边界如下：

- Java 向每轮 Agent 提供当前消息、会话标识、历史记录和上一轮状态；保存最终 `newState`，并在下一轮作为 `agentState` 回传。
- 插件完成意图判断、服务识别、追问、Probe、日志查询、POPo/ERP 提交、七鱼消息发送和最终结构化决策。
- 用户可见消息由 `qiyu_send_message` Tool 发送；Java 不根据自然语言补发消息，也不负责解释业务分支。
- Skill 描述路由、流程、知识和话术约束；真实外部调用由 Tool 完成。Skill 不执行 shell、curl 或其他复制自说明文本的命令。

逐轮分支行为见[执行文档](paas-customer-service-execution.md)。

## 2. 插件组成

### 2.1 Tool

| Tool | 当前职责 |
|---|---|
| `paas_resolve_service` | 依据服务注册表和用户消息/候选词解析唯一服务。 |
| `paas_get_manual_url` | 按已注册的 `serviceId` 返回服务展示名和手册 URL。 |
| `paas_probe_service` | 使用注册表控制的 Probe 配置与有道鉴权材料探测服务 demo。 |
| `paas_query_logs` | 按结构化请求上下文查询 o2log，并返回查询上下文、`hits` 和可选 `queryError`。 |
| `paas_send_erp_message` | 将服务配置、用户摘要、可选 Probe 摘要、可选日志结果和平台上下文投递到 POPo/ERP。 |
| `qiyu_send_message` | 向指定七鱼会话发送文本消息；成功后记录当轮 assistant message。 |
| `paas_finish_decision` | 校验并输出 Java 可解析的最终回合决策。 |

插件内部共享模块位于 `tools/_*.py`：

- `_models.py` 定义服务注册表、回合输入输出和状态模型。
- `_service_registry.py` 加载并解析服务注册表。
- `_config.py` 读取环境变量和服务注册表路径。
- `_http.py` 封装安全 JSON/form HTTP 调用及 mock URL 判断。
- `_youdao_auth.py`、`_youdao_probe.py` 生成有道 Probe 请求并归类结果。
- `_turn_messages.py` 暂存和消费当轮成功发送的七鱼 assistant message。
- `_errors.py` 生成统一 JSON 成功/错误 ToolResult。

### 2.2 Skill

| Skill | 当前职责 |
|---|---|
| `paas_customer_service_router` | 总入口：恢复待处理状态、识别场景、调度 Tool，并要求每轮调用最终决策 Tool。 |
| `paas_intent_classifier` | 将消息归类为 `access_docs`、`service_error` 或 `other`。 |
| `paas_service_resolver` | 要求服务身份来自 `paas_resolve_service`，不能凭文本编造服务 ID。 |
| `paas_clarification_policy` | 规定服务与请求上下文的追问条件和状态。 |
| `paas_access_docs_flow` | 处理接入文档咨询。 |
| `paas_service_error_flow` | 处理服务报错、Probe、日志和 POPo/ERP 升级。 |
| `paas_response_composer` | 约束用户可见消息的简洁中文话术与信息脱敏。 |
| `services/ocr`、`services/tts`、`services/asr` | 提供各服务的知识、别名、常见问题和排障上下文。 |

## 3. 服务注册表

默认注册表是 [`config/paas-services.example.yaml`](../../.openharness/plugins/paas-customer-service/config/paas-services.example.yaml)。当前包含 `ocr`、`tts`、`asr` 三个服务。每项服务均包含以下事实源：

| 配置项 | 用途 |
|---|---|
| `id`、`displayName`、`aliases` | 服务解析与用户展示。 |
| `manualUrl` | `paas_get_manual_url` 返回的接入文档地址。 |
| `probe.type`、`method`、`url`、`timeoutMs`、`requestTemplateRef` | `paas_probe_service` 的受控请求配置。 |
| `log.stream_name` | `paas_query_logs` 构造 o2log SQL 时使用的日志流。 |
| `erp.product`、`erp.message` | `paas_send_erp_message` 组装 POPo/ERP 文本时使用的产品和处理说明。 |

服务解析和手册查询只接受注册表中存在的服务。用户消息不能决定 Probe endpoint、日志流、POPo 产品或处理说明。

## 4. Java 与插件的回合契约

### 4.1 Java 输入

Router 读取每轮 JSON 中的字段：

| 字段 | 必填 | 用途 |
|---|---:|---|
| `conversationId` | 是 | 稳定会话标识；用于最终决策和当轮 Qiyu 消息缓存。 |
| `platformSessionId` | 是 | 客服平台原始会话 ID；Qiyu Tool 发送消息时使用。 |
| `platformUserId` | 否 | 七鱼与 POPo/ERP 上下文中的平台用户 ID。 |
| `staffId` | 否 | 当前客服或机器人坐席标识。 |
| `message` | 是 | 本轮用户消息。 |
| `history` | 否 | 最近对话记录，每项通常含 `role` 与 `content`。 |
| `agentState` | 否 | 上轮 `newState`，用于恢复未完成流程。 |

### 4.2 最终输出

每轮必须以 `paas_finish_decision` 收口。其输出是以下结构：

| 字段 | 含义 |
|---|---|
| `conversationId` | 当前会话 ID。 |
| `action` | 本轮业务动作标识，例如 `manual_sent` 或 `erp_sent`。 |
| `toolResults` | 本轮 Tool 调用摘要列表；每项含 Tool 名、成功状态和摘要。 |
| `assistantMessages` | 成功 `qiyu_send_message` 自动记录的当轮用户可见消息；调用方无需手工重复传入。 |
| `newState` | Java 需要保存并在下一轮回传的状态。 |
| `terminal` | 当前流程是否结束。 |

`newState` 的当前字段如下：

| 字段 | 含义 |
|---|---|
| `scenario` | `access_docs`、`service_error`、`other` 或未设置。 |
| `serviceId` | 注册表中的服务 ID；无法解析时为空。 |
| `waitingFor` | `service`、`request_context` 或为空。 |
| `clarificationCount` | 当前流程已发起的追问次数。 |
| `probeResult` | Probe 执行后的脱敏结果。 |
| `logResult` | 日志 Tool 的紧凑结果；仅 `hits` 表示匹配日志。 |
| `erpSent`、`erpMessageId` | POPo/ERP 是否发送成功及返回的消息标识。 |
| `terminal`、`terminalReason` | 流程终态和稳定原因码。 |

最终出口执行以下校验：

1. `conversationId` 不能为空。
2. 顶层 `terminal` 必须与 `newState.terminal` 相同。
3. `terminal=false` 时必须设置 `waitingFor`。
4. `service_error` 中服务已明确且 `erpSent=true` 时必须包含 `probeResult`。

## 5. Tool 的真实外部调用

### 5.1 服务与手册

`paas_resolve_service` 接收 `message` 和可选 `candidate`，返回注册表解析结果，包括 `serviceId`、置信度、歧义标志和候选服务。`paas_get_manual_url` 仅接收已注册 `serviceId`，返回 `serviceId`、`displayName` 和 `manualUrl`。

### 5.2 Probe

`paas_probe_service` 仅接收 `serviceId`。它从注册表读取 endpoint、HTTP 方法、超时和请求模板引用，使用服务对应的有道鉴权信息构造表单请求；用户输入不能覆盖这些值。返回值至少包含：

```json
{
  "serviceId": "ocr",
  "available": true,
  "statusCode": 200,
  "latencyMs": 0,
  "errorType": "ok",
  "responseKind": "json",
  "apiErrorCode": null
}
```

缺少凭据、无法支持的签名或 Probe 模板时，Tool 返回 `available=false` 的结构化结果；它们由服务报错流程作为 Probe 异常处理。

### 5.3 日志

`paas_query_logs` 仅接收 `serviceId`、至少一个 `requestId` / `appKey` 以及可选 `time`。它按服务注册表的 `log.stream_name` 构造查询，返回 `queryInfo`、`queryInfoSource`、时间窗口、`hits` 和可选 `queryError`。精确的查询时间、结果字段和解释规则见[执行文档的日志章节](paas-customer-service-execution.md#5-o2log-查询行为与结果解释)。

### 5.4 POPo/ERP 与七鱼

`paas_send_erp_message` 发送到 POPo webhook：文本含服务的 `erp.product` 和 `erp.message`、用户摘要、可选 Probe 摘要、可选日志结果及可用的平台会话/用户上下文。成功时返回 `erpMessageId`、`product`、`summary` 等字段。

`qiyu_send_message` 将 `platformUserId`、`platformSessionId` 和 `content` 发送到本地 Java 转发 endpoint。成功发送后，Tool 把内容写入当轮 assistant message 缓存；最终出口会自动收集为 `assistantMessages`。

## 6. 配置与外部依赖

| 环境变量 | 当前用途 | 未设置时行为 |
|---|---|---|
| `PAAS_SERVICE_REGISTRY_PATH` | 覆盖默认服务注册表路径。 | 使用插件内 `config/paas-services.example.yaml`。 |
| `PAAS_O2LOG_ENDPOINT` | 覆盖 o2log 搜索 endpoint。 | 使用 Tool 内置的 o2log 默认 endpoint。 |
| `PAAS_O2LOG_AUTHORIZATION` | 提供 o2log 请求 `Authorization` 值。 | 请求不附加该请求头。 |
| `PAAS_POPO_ENDPOINT` | 覆盖 POPo webhook endpoint。 | 使用 Tool 内置的 POPo 默认 endpoint。 |
| `PAAS_ERP_ENDPOINT` | `PAAS_POPO_ENDPOINT` 未设置时的兼容 endpoint 覆盖。 | 使用 Tool 内置的 POPo 默认 endpoint。 |
| `QIYU_SEND_MESSAGE_ENDPOINT` | 覆盖本地 Java 七鱼转发 endpoint。 | 使用 Tool 内置的本地默认 endpoint。 |
| `ADMIN_TOKEN` | 覆盖七鱼转发请求的 `Admin-Token`。 | 使用 Tool 内置默认值；部署环境应通过环境变量覆盖。 |
| `QIYU_SEND_MESSAGE_MOCK` | 设置为不区分大小写的 `true` 时启用 Qiyu mock。 | 发送真实 HTTP 请求。 |

各服务的有道鉴权材料由 `_youdao_auth.py` 从环境变量读取。文档不记录具体凭据、签名或默认 token 值。

## 7. 当前安全边界与限制

- Tool 不接受用户提交的自由 o2log SQL、DSL、Lucene 查询或旧 `timeRange` 字段；日志查询只能由结构化 `serviceId`、`requestId` / `appKey` 和可选 `time` 生成。
- 服务、手册 URL、Probe endpoint 和日志流均以服务注册表为准，Agent 不能从记忆或用户消息编造这些事实。
- Qiyu 用户消息不得展示 token、cookie、签名、完整 appKey、原始日志、内部 endpoint 或 Tool 原始异常。
- Probe 和日志结果可进入 POPo/ERP 的内部消息；Probe 异常和日志查询分支不向用户发送 Qiyu 诊断消息。
- 当前插件未实现统一 Tool 白名单、限流、熔断或跨调用幂等机制；这些能力不是本插件的现有保证。

## 8. 与执行文档的关系

本文档记录插件的组成与运行契约。[`paas-customer-service-execution.md`](paas-customer-service-execution.md) 记录 Router 每轮如何恢复状态、选择场景、调用 Tool，并解释日志和外部副作用。
