# PaaS 客服日志查询设计

## 背景

`paas-customer-service` 插件在 PaaS 服务报错场景中已有服务识别、demo probe、日志查询、ERP/POPo 通知和七鱼消息发送能力。当前 `paas_query_logs` 仍是泛化占位实现：可选转发到 `PAAS_LOG_ENDPOINT`，入参包含 `timeRange`，返回的是 mock/摘要式结果。

本设计按 `docs/SDD/query-log.md` 将日志查询改为真实调用有道 o2log，并同步调整客服流程：当用户补充 requestId、appKey、time 等报错信息后，先查日志，再发 ERP/POPo；该分支不再通过七鱼向用户发送“已反馈排查”类确认消息。

## 目标

1. `paas_query_logs` 固定调用 o2log 查询接口。
2. 删除 `timeRange`，用单点时间字段 `time` 替代。
3. `time` 支持客服明确要求的格式：`2026年7月2日 10:30`。
4. 有合法 `time` 时查询 `time - 30 分钟` 到 `time + 30 分钟`。
5. 无 `time` 或 `time` 格式不合法时查询当前时间往前 120 分钟。
6. `paas_query_logs` 返回 o2log 原始 JSON 响应，不脱敏、不摘要化。
7. `paas_send_erp_message` 删除 `logSummary`，新增 `logResult`，用于携带 `paas_query_logs` 返回结果。
8. 报错信息明确后的流程为：查日志 → 发 ERP/POPo → finish，不调用 `qiyu_send_message`。

## 非目标

1. 不实现复杂自然语言时间解析，例如“昨天晚上”“刚刚”“上周五下午”。这类输入由 agent 尽量归一化；归一化失败时工具走默认最近 120 分钟。
2. 不新增独立时间解析工具。
3. 不改 Java 侧 webhook 去重或平台消息发送逻辑。
4. 不在 `paas_query_logs` 中生成面向用户的日志摘要。
5. 不保留 `logSummary` 向后兼容；本次直接替换为 `logResult`。

## 工具契约：`paas_query_logs`

### 入参

```json
{
  "serviceId": "ocr",
  "appKey": "app_xxx",
  "requestId": "req_xxx",
  "time": "2026年7月2日 10:30"
}
```

字段规则：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `serviceId` | 是 | 服务注册表中的服务 ID。 |
| `appKey` | 否 | 用户应用 key；当 `requestId` 不存在时作为日志查询关键字。 |
| `requestId` | 否 | 请求 ID；存在时优先作为日志查询关键字。 |
| `time` | 否 | 单点报错时间，格式必须是 `YYYY年M月D日 HH:mm`，例如 `2026年7月2日 10:30`。 |

校验规则：

- `requestId` 和 `appKey` 至少提供一个，否则工具返回参数错误。
- `timeRange` 删除后由 Pydantic `extra="forbid"` 拒绝。
- `time` 格式错误不导致工具失败，降级到默认最近 120 分钟窗口，并返回 `timeFallback=true`。

### 查询关键字

```text
queryInfo = requestId if requestId else appKey
```

返回中标识来源：

```json
{
  "queryInfo": "req_xxx",
  "queryInfoSource": "requestId"
}
```

或：

```json
{
  "queryInfo": "app_xxx",
  "queryInfoSource": "appKey"
}
```

### 时间窗口

默认时区为 `Asia/Shanghai`。

有合法 `time`：

```text
start = time - 30 分钟
end   = time + 30 分钟
```

无 `time` 或 `time` 不合法：

```text
end   = now
start = now - 120 分钟
```

传给 o2log 时使用：

```text
start_time = start 的毫秒时间戳 * 1000
end_time   = end 的毫秒时间戳 * 1000
```

### o2log 请求

固定调用：

```text
POST https://o2log.corp.youdao.com/api/aicloud/_search
Authorization: Basic <token>
Content-Type: application/json
```

请求体：

```json
{
  "query": {
    "from": 0,
    "size": 100,
    "sql": "SELECT * FROM \"aicloud_ocr\" WHERE body LIKE '\''%req-xxx%\'' ORDER BY _timestamp DESC",
    "start_time": 1782891493000000,
    "end_time": 1782895093000000
  }
}
```

`stream_name` 来自服务配置中的 `log.stream_name`。`stream_name` 不接受外部输入。`queryInfo` 进入 SQL 前需要做单引号转义，避免破坏 SQL 字符串。

### 返回

成功或 o2log 正常返回时：

```json
{
  "serviceId": "ocr",
  "streamName": "aicloud_ocr",
  "queryInfo": "req-xxx",
  "queryInfoSource": "requestId",
  "time": "2026年7月2日 10:30",
  "timeFallback": false,
  "startTime": 1782891493000000,
  "endTime": 1782895093000000,
  "mock": false,
  "response": {
    "...": "o2log 原始 JSON 返回"
  },
  "errorType": null
}
```

HTTP 调用失败时：

```json
{
  "serviceId": "ocr",
  "streamName": "aicloud_ocr",
  "queryInfo": "req-xxx",
  "queryInfoSource": "requestId",
  "time": null,
  "timeFallback": true,
  "startTime": 1782887893000000,
  "endTime": 1782895093000000,
  "mock": false,
  "response": null,
  "errorType": "timeout"
}
```

开发或未配置真实 endpoint 的场景可保留 mock 分支，但 mock 返回结构必须与真实分支一致。

## 工具契约：`paas_send_erp_message`

### 入参变更

删除：

```json
{
  "logSummary": "..."
}
```

新增：

```json
{
  "logResult": {
    "serviceId": "ocr",
    "streamName": "aicloud_ocr",
    "queryInfo": "req-xxx",
    "queryInfoSource": "requestId",
    "time": "2026年7月2日 10:30",
    "timeFallback": false,
    "startTime": 1782891493000000,
    "endTime": 1782895093000000,
    "mock": false,
    "response": {
      "...": "o2log 原始 JSON 返回"
    },
    "errorType": null
  }
}
```

最终输入示例：

```json
{
  "serviceId": "ocr",
  "userSummary": "用户反馈 OCR 调用报错，已提供 requestId/appKey/time。",
  "probeSummary": "probe available: serviceId=ocr, latencyMs=98",
  "logResult": {
    "...": "paas_query_logs 返回结果"
  },
  "platformContext": {
    "conversationId": "qiyu:6383959733",
    "platformSessionId": "6383959733",
    "platformUserId": "user-1"
  }
}
```

POPo 消息中包含 `logResult` 的 JSON 文本。如果消息过长，可以按固定最大长度截断，截断是传输保护，不是脱敏或摘要替换。

## 报错场景流程

### 服务不明确

1. 调用 `paas_resolve_service`。
2. 调用 `qiyu_send_message` 询问服务。
3. 调用 `paas_finish_decision`，`terminal=false`，等待用户补充。

### 服务明确，probe 失败

1. 调用 `paas_probe_service`。
2. 调用 `paas_send_erp_message`。
3. 不调用 `qiyu_send_message`。
4. 调用 `paas_finish_decision`，`terminal=true`。

终态 reason：`erp_sent_after_probe_failure`。

### 服务明确，probe 正常，但缺 requestId/appKey

1. 调用 `paas_probe_service`。
2. 调用 `qiyu_send_message` 询问请求上下文。
3. 调用 `paas_finish_decision`，`terminal=false`。

用户话术：

```text
线上 demo 检测暂未发现服务整体异常。请提供 requestId、appKey、time 等信息，方便客服进一步排查。time 给一个大约模糊有误差的时间即可，但必须是 2026年7月2日 10:30 这种格式；如果暂时没有时间也可以先提供 requestId 或 appKey。
```

### 用户补充 requestId/appKey/time

1. 读取 `agentState.waitingFor=request_context` 和已有 `serviceId`。
2. 从当前消息和历史中提取 `requestId`、`appKey`、`time`。
3. 只要 `requestId` 或 `appKey` 至少有一个，调用 `paas_query_logs`。
4. 调用 `paas_send_erp_message`，传入 `logResult`。
5. 不调用 `qiyu_send_message`。
6. 调用 `paas_finish_decision`，`terminal=true`。

终态：

```json
{
  "scenario": "service_error",
  "serviceId": "ocr",
  "waitingFor": null,
  "probeResult": {
    "available": true
  },
  "logResult": {
    "...": "paas_query_logs 返回结果"
  },
  "erpSent": true,
  "terminal": true,
  "terminalReason": "erp_sent_after_log_query"
}
```

最终 decision 的 `assistantMessages` 应为空，因为该分支不通过七鱼发送确认消息。

### 用户明确无法提供 requestId/appKey

不查询日志。保持现有澄清或结束策略即可，但不得在没有 requestId/appKey 的情况下构造日志查询。是否发送 ERP 仍按服务是否 probe 失败区分：probe 正常且缺上下文时不发送日志结果。

## 需要修改的文件

- `.openharness/plugins/paas-customer-service/tools/paas_query_logs_tool.py`
- `.openharness/plugins/paas-customer-service/tools/paas_send_erp_message_tool.py`
- `.openharness/plugins/paas-customer-service/tools/_models.py`
- `.openharness/plugins/paas-customer-service/skills/paas_service_error_flow/SKILL.md`
- `.openharness/plugins/paas-customer-service/skills/paas_clarification_policy/SKILL.md`
- `.openharness/plugins/paas-customer-service/skills/paas_customer_service_router/SKILL.md`
- `tests/test_plugins/test_paas_customer_service/test_paas_query_logs_tool.py`
- `tests/test_plugins/test_paas_customer_service/test_paas_send_erp_message_tool.py`

## 测试计划

1. `paas_query_logs` schema 拒绝 `timeRange`。
2. `paas_query_logs` 要求 `requestId` 和 `appKey` 至少一个。
3. `requestId` 优先于 `appKey` 构造 SQL。
4. 只有 `appKey` 时可以查询。
5. `time="2026年7月2日 10:30"` 时查询窗口是 10:00 到 11:00。
6. 无 `time` 时查询窗口是当前时间往前 120 分钟。
7. `time` 格式错误时降级最近 120 分钟，并返回 `timeFallback=true`。
8. o2log endpoint、Authorization header、body 结构正确。
9. `paas_query_logs` 返回 `response` 原始 JSON，不返回 `summary/highlights`。
10. `paas_send_erp_message` 接收 `logResult`。
11. `paas_send_erp_message` schema 拒绝旧 `logSummary`。
12. skill 文档不再出现 `timeRange` / `logSummary`，补充上下文后的报错流程为“查日志 → 发 ERP/POPo → 不发 qiyu 消息”。

## 风险与边界

1. o2log Basic token 是外部凭据，不能出现在测试断言失败、错误信息或文档示例的真实值中。
2. `paas_query_logs` 返回原始日志详情，调用链下游必须避免把原始日志通过 `qiyu_send_message` 发给终端用户。
3. POPo 消息长度可能有限；`logResult` JSON 文本需要固定上限截断，避免发送失败。
4. 时间解析只支持指定格式，模糊自然语言需要 agent 在调用工具前归一化。
