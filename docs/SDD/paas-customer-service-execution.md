# PaaS 智能客服插件执行行为

本文档描述 [`paas-customer-service`](../../.openharness/plugins/paas-customer-service) 插件在当前实现中的逐轮行为。插件组成、配置来源和 Java 输入输出契约见[总体设计文档](design.md)。

## 1. 每轮输入、恢复与收口

Router 每轮读取 Java 提供的 `message`、`history`、会话标识和 `agentState`：

1. 如果 `agentState.waitingFor=service`，优先使用本轮消息和历史重新解析服务。
2. 如果 `agentState.waitingFor=request_context`，优先提取 `requestId`、`appKey` 和可选 `time`。
3. 没有待处理状态时，将消息分类为 `access_docs`、`service_error` 或 `other`。
4. 需要识别服务时，调用 `paas_resolve_service`；不从消息文本自行编造服务 ID。
5. 每个分支最终调用 `paas_finish_decision`，由该 Tool 输出 Java 可解析的回合结果。

成功的 `qiyu_send_message` 会将发送内容记录在以 `conversationId` 区分的当轮缓存中。`paas_finish_decision` 默认消费该缓存，并在最终结果的 `assistantMessages` 中返回这些消息；调用流程不应手工重复写入相同内容。

## 2. 场景和状态字段

| 场景 | 触发含义 |
|---|---|
| `access_docs` | 用户询问服务接入、调用、配置、文档或 demo。 |
| `service_error` | 用户反馈错误、失败、异常响应、状态码、超时或认证问题。 |
| `other` | 当前插件不处理的消息。 |

状态保存在每轮最终结果的 `newState` 中：

| 字段 | 当前行为 |
|---|---|
| `serviceId` | 已唯一解析的注册表服务 ID；未解析时为空。 |
| `waitingFor` | `service` 表示等待服务名；`request_context` 表示等待至少一个日志查询键；终态时为空。 |
| `clarificationCount` | 当前状态中已经记录的追问次数。 |
| `probeResult` | 服务明确且执行 Probe 后的脱敏摘要。 |
| `logResult` | 已执行日志查询时的紧凑结果；`hits` 是唯一的匹配日志列表。 |
| `erpSent`、`erpMessageId` | POPo/ERP 提交是否成功及可用消息 ID。 |
| `terminal`、`terminalReason` | 当前分支是否结束及结束/等待原因。 |

非终态必须同时满足 `terminal=false` 且 `waitingFor` 非空。当前状态等待项只有 `service` 与 `request_context`。

## 3. 接入文档流程

### 3.1 服务不明确

当意图为 `access_docs`，但 `paas_resolve_service` 没有返回唯一服务时：

1. 通过 `qiyu_send_message` 询问具体服务。
2. 通过 `paas_finish_decision` 以非终态结束当前轮。

典型状态：

```json
{
  "scenario": "access_docs",
  "serviceId": null,
  "waitingFor": "service",
  "terminal": false,
  "terminalReason": "waiting_for_service"
}
```

追问内容要求用户提供已注册服务名或别名；例如 OCR、TTS、ASR。若 Tool 返回候选展示名，话术使用候选展示名。服务不明确本身不会触发 POPo/ERP。

### 3.2 服务明确

当解析得到唯一注册表服务时：

1. 调用 `paas_get_manual_url(serviceId)` 获取 `displayName` 与 `manualUrl`。
2. 使用 Tool 返回的展示名和 URL 组成接入文档消息。
3. 调用 `qiyu_send_message` 发送该消息。
4. 调用 `paas_finish_decision`，以 `manual_sent` 终止。

典型状态：

```json
{
  "scenario": "access_docs",
  "serviceId": "ocr",
  "waitingFor": null,
  "terminal": true,
  "terminalReason": "manual_sent"
}
```

此流程不执行 Probe、日志查询或 POPo/ERP 提交，且不根据记忆生成手册 URL。

## 4. 服务报错流程

### 4.1 服务不明确

当意图为 `service_error`，但未解析到唯一服务时：

1. 调用 `paas_resolve_service`。
2. 通过 `qiyu_send_message` 追问服务名。
3. 通过 `paas_finish_decision` 返回 `waitingFor=service` 的非终态。

典型状态：

```json
{
  "scenario": "service_error",
  "serviceId": null,
  "waitingFor": "service",
  "terminal": false,
  "terminalReason": "waiting_for_service"
}
```

### 4.2 服务明确后先 Probe

服务明确后必须先调用 `paas_probe_service`。Probe 以注册表中的服务配置为准，并返回包含 `available`、HTTP 状态、延迟、错误类型和响应类别的脱敏结果。该 Probe 判断标准 demo 是否可用，不证明用户自身请求必然正确。

### 4.3 Probe 异常

当 Probe 不可用、超时、HTTP 5xx、网络异常、认证异常、响应异常，或无法构造有效 Probe 时：

1. 调用 `paas_send_erp_message`，将用户摘要和必要的脱敏 Probe 摘要交给 POPo/ERP。
2. 不调用 `qiyu_send_message`；这一分支对用户静默。
3. 通过 `paas_finish_decision` 以终态结束。

典型状态：

```json
{
  "scenario": "service_error",
  "serviceId": "ocr",
  "waitingFor": null,
  "probeResult": {"available": false},
  "erpSent": true,
  "terminal": true,
  "terminalReason": "erp_sent_after_probe_failure"
}
```

发送到 POPo/ERP 的 Probe 摘要可以包含 `serviceId`、`available`、`statusCode`、`errorType`、`responseKind`、`apiErrorCode` 和 `latencyMs`。不得包含凭据、签名、请求体、响应样本或音频/base64 内容。

### 4.4 Probe 正常但缺请求上下文

当 Probe 正常、服务已明确，但当前消息和历史中都没有 `requestId` 或 `appKey` 时：

1. 通过 `qiyu_send_message` 请求用户提供 `requestId`、`appKey` 和可选 `time`。
2. 通过 `paas_finish_decision` 返回 `waitingFor=request_context` 的非终态。

典型状态：

```json
{
  "scenario": "service_error",
  "serviceId": "ocr",
  "waitingFor": "request_context",
  "probeResult": {"available": true},
  "terminal": false,
  "terminalReason": "waiting_for_request_context"
}
```

用户提供的时间格式为 `YYYY年M月D日 HH:mm`，例如 `2026年7月2日 10:30`。时间可以省略；`requestId` 或 `appKey` 至少应提供一个。

### 4.5 收到请求上下文

上轮 `waitingFor=request_context` 后，如果本轮或历史中出现 `requestId` 或 `appKey`：

1. 调用 `paas_query_logs`，仅传递 `serviceId`、可用的 `requestId` / `appKey` 和可选 `time`。
2. 调用 `paas_send_erp_message`，将用户摘要、Probe 摘要和完整紧凑 `logResult` 发送给 POPo/ERP。
3. 不调用 `qiyu_send_message`，也不基于日志结果生成面向用户的根因说明。
4. 调用 `paas_finish_decision`，以终态结束。

典型状态：

```json
{
  "scenario": "service_error",
  "serviceId": "ocr",
  "waitingFor": null,
  "probeResult": {"available": true},
  "logResult": {
    "serviceId": "ocr",
    "streamName": "aicloud_ocr",
    "queryInfo": "req-123",
    "queryInfoSource": "requestId",
    "hits": []
  },
  "erpSent": true,
  "terminal": true,
  "terminalReason": "erp_sent_after_log_query"
}
```

### 4.6 无法提供查询键

如果用户明确无法同时提供 `requestId` 与 `appKey`：

1. 不调用 `paas_query_logs`。
2. Probe 正常时，不会仅因为缺少查询键自动发送 POPo/ERP。
3. 流程可再次请求至少一个查询键；若用户明确无法提供，则以 `missing_request_context` 终止。

## 5. o2log 查询行为与结果解释

### 5.1 输入与查询构造

`paas_query_logs` 的输入模型禁止额外字段，只接受：

```json
{
  "serviceId": "ocr",
  "requestId": "req-123",
  "appKey": "app_abcdef",
  "time": "2026年7月2日 10:30"
}
```

`requestId` 和 `appKey` 至少有一个。两者同时存在时，Tool 使用 `requestId` 作为 `queryInfo`；没有 `requestId` 时使用 `appKey`。

日志流从服务注册表的 `log.stream_name` 读取。Tool 生成固定结构的 o2log SQL：按该日志流筛选 `body LIKE '%queryInfo%'`，按 `_timestamp DESC` 排序；查询值中的单引号会被转义。调用方不能传入自由 SQL、DSL、Lucene 查询、`rawQuery` 或 `timeRange`。

### 5.2 时间窗口

`time` 只接受精确格式 `YYYY年M月D日 HH:mm`：

- 合法时间：以该时刻为中心，开始时间为前 30 分钟，结束时间为后 30 分钟，`timeFallback=false`。
- 缺失或不合法时间：以 Tool 调用时刻为结束时间，向前回退 120 分钟，`timeFallback=true`。

o2log 的 `startTime` 与 `endTime` 是 Unix 毫秒再乘以 1000。

### 5.3 返回结果和解释规则

Tool 的紧凑输出包含服务和查询上下文、时间窗口、`mock`、`hits`，日志平台请求失败或响应中 `hits` 不是列表时额外包含 `queryError`：

```json
{
  "serviceId": "ocr",
  "streamName": "aicloud_ocr",
  "queryInfo": "req-123",
  "queryInfoSource": "requestId",
  "time": "2026年7月2日 10:30",
  "timeFallback": false,
  "startTime": 1782957600000000,
  "endTime": 1782961200000000,
  "mock": false,
  "hits": [],
  "queryError": {"type": "timeout"}
}
```

解释规则：

1. 仅 `hits` 表示匹配到的用户请求日志。
2. `hits=[]` 仅表示在该查询条件和时间窗口内没有匹配日志；它不是用户请求认证失败、服务故障、无效 appKey 或签名错误的证据。
3. `queryError` 描述 o2log 平台查询本身的问题。例如 `queryError.type=auth_error` 表示日志查询认证失败，而不是 OCR、TTS 或 ASR 用户请求认证失败。
4. 只有具体 `hits` 项中明确出现业务错误时，Agent 才能在内部 POPo/ERP 摘要中提及该错误；当前日志查询分支不向用户发送诊断消息。

## 6. Qiyu 与 POPo/ERP 副作用

### 6.1 Qiyu

`qiyu_send_message` 的正常路径构造 `uid`、`sessionId` 与 `content`，通过本地 Java 七鱼转发 endpoint 发送，并附带 `Admin-Token` 请求头。转发响应中的 `code=200` 才表示发送成功。

当 `QIYU_SEND_MESSAGE_MOCK=true` 时，Tool 不执行 HTTP 请求，直接返回 mock 成功结果，同时仍写入当轮 assistant message。因此最终决策仍会看到对应的 `assistantMessages`。

Qiyu 用户消息用于服务追问、请求上下文追问和文档回复。Probe 异常和日志查询后提交 POPo/ERP 的两个终态分支均不发送 Qiyu 消息。

### 6.2 POPo/ERP

`paas_send_erp_message` 将以下内容组成文本后投递：

1. 固定 PaaS 客服前缀。
2. 服务注册表中的产品和处理说明。
3. 用户摘要。
4. 可选 Probe 摘要。
5. 可选 `logResult`，超长时会截断。
6. 可用的 `conversationId`、`platformSessionId`、`platformUserId`。

POPo/ERP 请求成功且返回 `errcode=0` 时，Tool 输出服务产品、摘要与消息 ID；上游未返回消息 ID 时使用基于服务、用户摘要和会话 ID 的稳定 fallback ID。

## 7. 最终决策输出

每条分支调用 `paas_finish_decision`。Tool 校验：

1. `conversationId` 非空。
2. 顶层 `terminal` 和 `newState.terminal` 一致。
3. 非终态必须有 `waitingFor`。
4. `service_error` 中服务已明确、且状态声明 `erpSent=true` 时，必须提供 `probeResult`。

成功时，Tool 返回 `conversationId`、`action`、`toolResults`、`assistantMessages`、`newState` 和 `terminal`。Java 保存 `newState` 与 `terminal`，并在下一轮继续未终止的对话。

## 8. 当前自动化测试覆盖

插件测试位于 [`tests/test_plugins/test_paas_customer_service`](../../tests/test_plugins/test_paas_customer_service)。当前测试覆盖：

- 服务注册表加载、服务别名解析、手册 URL 查询。
- PaaS Agent 输入模型和插件运行时加载。
- 有道鉴权、请求表单和 OCR/TTS/ASR Probe 结果分类。
- o2log 的请求构造、时间窗口、mock、`hits` 规范化、查询错误和拒绝自由查询字段。
- POPo/ERP 文本构造、HTTP 响应处理和日志结果传递。
- Qiyu 请求、响应处理、内容校验和 mock 下的 assistant message 记录。
- 最终决策的状态校验、assistant message 自动汇总和紧凑日志结果保留。
