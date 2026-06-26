# PaaS 智能客服最小闭环 SDD

## 1. 背景

平台 A 在第一版中明确为七鱼客服平台。用户通过七鱼咨询 PaaS 服务，例如 OCR、TTS、ASR 等。当前目标是在人工客服前增加一层智能客服预处理能力，但 Java 层必须尽可能薄：Java 只接收七鱼 webhook、做七鱼协议校验、最小去重和内存态桥接，然后调用本地 OpenHarness。

客服业务流程、用户可见话术、七鱼主动发消息、ERP、probe、日志查询和后续告警全部沉淀到 OpenHarness Skill/Tool 中。Java 与 OpenHarness 之间只保持稳定、简洁的输入输出协议，避免把客服业务重新写回 Java。

本 SDD 与外部 PRD `/Users/admin/IdeaProjects/reactive_proxy_gateway/sdd/prd/intelligent-customer-service-prd.md` 对齐，描述当前最小闭环的设计边界。OpenHarness Skill/Tool 的具体实现不在 Java 工程内，但本文件定义 Java 与 OpenHarness 的职责分工、协议和验收标准。

## 2. 最小闭环目标

### 2.1 Java 目标

Java 只负责：

1. 暴露七鱼 webhook 接口。
2. 处理七鱼 URL 验证。
3. 校验七鱼事件推送签名和时间戳。
4. 解析七鱼事件 JSON。
5. 只处理有效文本访客消息。
6. 用当前 JVM 内存做最小会话历史和消息去重。
7. 构造最小 OpenHarness 输入 JSON。
8. 调用本地 `oh` 命令。
9. 解析最小 OpenHarness 输出 JSON。
10. 保存 `newState` 和 `terminal`。
11. 返回七鱼 webhook ACK。

### 2.2 Java 明确不负责

Java 第一版不负责：

1. 不识别服务。
2. 不判断业务场景。
3. 不维护服务清单、别名或文档 URL。
4. 不生成用户可见话术。
5. 不调用七鱼发送消息 API。
6. 不调用七鱼会话升级 API。
7. 不发送异常兜底消息。
8. 不发送 ERP 消息。
9. 不解析 `newState` 内部业务字段做流程分支。
10. 不保存平台动作明细对象。
11. 不保存 OpenHarness 调用摘要对象。
12. 不执行 demo probe。
13. 不查询日志系统。
14. 不承载客服排障编排。

### 2.3 OpenHarness 目标

OpenHarness 负责：

1. 判断用户意图、服务和场景。
2. 决定是否追问。
3. 查询接入文档。
4. probe 服务。
5. 查询日志。
6. 发送 ERP 或内部工单消息。
7. 生成用户可见文本。
8. 通过 `qiyu_send_message` Tool 给七鱼用户发消息。
9. 通过 `paas_send_erp_message` Tool 提交客服人员跟进。
10. 返回最小结构化摘要给 Java。

## 3. 最终职责边界

### 3.1 Java 服务职责

Java 层只做基础设施和状态桥接，不做客服业务判断：

- 接收七鱼 URL 验证请求和事件推送请求。
- 校验七鱼 `appkey`、签名、时间戳、nonce 或 checksum。
- 解析七鱼 `CLIENT_MESSAGE` 事件。
- 只接受 `msgtype=TEXT`、`status=1`、`content` 非空且字段完整的访客消息。
- 将七鱼 `session_id` 映射为内部 `conversationId = qiyu:{session_id}`。
- 使用当前 JVM 内存保存最近访客消息 history、OpenHarness 返回的 `agentState` 和 `terminal`。
- 使用 `processedMessageKeys` 对 `platformMessageId` 做最小去重。
- 组装 OpenHarness 最小输入 JSON。
- 通过本地 `oh` 命令调用 OpenHarness。
- 解析 OpenHarness 最小输出 JSON。
- 原样保存 `newState`，保存 `terminal`。
- 返回七鱼 webhook ACK。

Java 不把 OpenHarness 输出转换为用户消息；用户可见消息必须由 OpenHarness 通过七鱼 Tool 主动发送。

### 3.2 OpenHarness 职责

OpenHarness 负责完整客服业务流程：

- 理解用户问题。
- 判断问题是否明确。
- 服务不明确时决定追问。
- 判断接入文档、服务报错、其他咨询、ERP 跟进等场景。
- 接入咨询场景：匹配服务并通过七鱼 Tool 发送文档说明。
- 错误反馈场景：按规则调用 demo probe、追问 appKey/requestId、查询日志、发 ERP 或内部工单、通知用户。
- 需要客服人员跟进时，通过 `paas_send_erp_message` Tool 提交 ERP 消息。
- 其他场景：直接结束，不调用 probe、日志、ERP 或转接能力。
- 输出 `action`、`toolResults`、`newState`、`terminal` 等最小 JSON 摘要给 Java。

### 3.3 关键约束

由于本方案不做常驻 bridge，每次 `oh` 调用都是单次执行。Java 必须每次传入：

- `conversationId`
- `platformSessionId`
- `platformUserId`
- `staffId`
- 当前访客文本 `message`
- 最近访客消息 `history`
- 上轮 `agentState`

OpenHarness 不应依赖 Java 进程内业务判断，也不能假设自己拥有跨调用的内存状态。跨轮客服状态必须通过 `newState` 返回 Java，再由 Java 在下一轮作为 `agentState` 原样传回。

## 4. 最小闭环流程

```text
七鱼 CLIENT_MESSAGE
  ↓
Java Controller 校验签名、解析 JSON
  ↓
构造 QiyuCallbackEvent
  ↓
AiCustomerServiceExecutor
  ├─ 过滤事件
  ├─ processedMessageKeys.putIfAbsent 去重
  ├─ conversations.computeIfAbsent 获取上下文
  ├─ 追加 HistoryMessage
  └─ 调用 OpenHarnessClient
       ↓
     OpenHarnessClient
       ├─ 构造最小 input JSON
       ├─ 写临时文件
       ├─ 调用 oh
       └─ 解析最小 output JSON
          ↓
OpenHarness Skill/Tool 编排客服流程
  ├─ 必要时 qiyu_send_message 给用户发消息
  ├─ 必要时通过 paas_send_erp_message 提交客服人员跟进
  ├─ 必要时 paas_probe_service / paas_query_logs / paas_send_erp_message
  └─ 返回最小结构化摘要
          ↓
Java 保存 newState 和 terminal
  ↓
Java 返回七鱼 webhook ACK
```

Java 返回 ACK 只代表七鱼 webhook 已接收，不代表客服消息一定由 Java 发出。客服用户消息是否已发送、是否 ERP 升级，均由 OpenHarness Tool 决定并在 `toolResults` 中返回摘要。

## 5. 七鱼 webhook 需求

### 5.1 URL 验证

七鱼控制台保存回调 URL 时会发送验证请求：

```http
POST https://{服务域名}/ai_customer_service/notify?appkey=APP_KEY&time=13500001234&nonce=123412323&echostr=ENCRYPT_STR&checksum=RTYUQWEXZCVAQFASDFASCYR
```

Java 行为：

1. URL decode `echostr`。
2. 校验 `appkey`、`time`、`nonce`、`echostr`、`checksum`。
3. 解密 `echostr` 得到明文。
4. 在 1 秒内直接返回明文字符串。
5. 返回内容不能加引号，不能带 BOM，不能带换行，不能包裹 `code` 字段。

### 5.2 事件推送

正式事件推送示例：

```http
POST https://{服务域名}/ai_customer_service/notify?appkey=APP_KEY&eventType=CLIENT_MESSAGE&time=162593272&checksum=CHECKSUM&checksumAlgorithm=0
```

`CLIENT_MESSAGE` 示例：

```json
{
  "createtime": 1625932727657,
  "msgidclient": "6383959733#0#36946076bba94a2bb0780bf748606f8c",
  "session_id": 6383959733,
  "content": "OCR 服务一直报 401，帮我看下",
  "from_user": 1,
  "foreign_id": "81275614-ff4c-490e-9517-0934f4fc9325@顺风车乘客",
  "autoreply": 0,
  "user_id": 20627473396,
  "staff_id": 4126122,
  "id": 31050959281,
  "updatetime": 1625932727657,
  "corp_id": 3517575,
  "msgtype": "TEXT",
  "status": 1
}
```

关键字段：

| 字段 | 规则 |
|---|---|
| `session_id` | 生成 `conversationId = qiyu:{session_id}`，并作为 `platformSessionId` 传给 OpenHarness。 |
| `foreign_id` | 作为 `platformUserId` 传给 OpenHarness；不存在或为空时传空字符串 `""`。 |
| `user_id` | 七鱼内部访客 ID，不作为 `platformUserId`，不传给 OpenHarness。 |
| `staff_id` | 转为字符串作为 `staffId`；不存在时为空字符串。 |
| `msgidclient` / `id` | `platformMessageId = msgidclient 非空 ? msgidclient : String.valueOf(id)`，仅 Java 去重使用，不传给 OpenHarness。 |
| `content` | 当前访客文本消息。 |
| `msgtype` | 第一版只处理 `TEXT`。 |
| `status` | 第一版只处理 `1`。 |

## 6. 事件处理规则

| 事件类型 | Java 行为 |
|---|---|
| `CLIENT_MESSAGE` | 仅当 `msgtype=TEXT`、`status=1`、`content` 非空时调用 OpenHarness。 |
| `STAFF_MESSAGE` | 第一版 ACK，不调用 OpenHarness；可选写入 history 或标记 erp_followup，默认不做。 |
| `CLIENT_MARK_READ` | ACK，不调用 OpenHarness。 |
| 其他事件 | ACK，不调用 OpenHarness。 |

忽略类消息包括：

1. 非 `CLIENT_MESSAGE`。
2. `msgtype != TEXT`。
3. `status != 1`。
4. `content` 为空或全空白。
5. 缺少 `session_id`。
6. 缺少消息 ID。
7. 会话已 `terminal` 且配置要求忽略终止会话后续消息。
8. 重复 `platformMessageId`。

忽略类消息只返回 ACK，不调用 OpenHarness，不发送用户消息。

## 7. Java 内存态最小模型

第一版只使用当前 JVM 内存，不接数据库，不接 Redis，不做跨节点共享。服务重启后状态全部丢失。

### 7.1 conversations

```java
ConcurrentHashMap<String, ConversationContext> conversations
```

按 `conversationId` 保存会话。

`ConversationContext` 最小字段：

```java
public class ConversationContext {
    private String conversationId;
    private String platformSessionId;
    private String platformUserId;
    private String staffId;
    private List<HistoryMessage> history;
    private JsonNode agentState;
    private boolean terminal;
    private Instant updatedAt;
    private Instant expiresAt;
}
```

说明：

- `platformUserId` 来自七鱼 `foreign_id`，无值时为空字符串。
- `agentState` 原样保存 OpenHarness 输出的 `newState`。
- Java 只使用 `terminal` 判断是否继续处理，不读取 `agentState.scenario`、`agentState.serviceId`、`agentState.waitingFor`。
- 不保存 assistant 消息正文。
- 不保存 `platformActions`。
- 不保存调用摘要对象。

### 7.2 history

`HistoryMessage` 最小字段：

```java
public class HistoryMessage {
    private String role;
    private String content;
}
```

规则：

1. 默认只保存和传递访客文本消息：`role=user`。
2. 不保存 OpenHarness 已发送给用户的消息正文。
3. 按时间升序。
4. 超过 `maxHistoryMessages` 时保留最近消息。
5. 超过 `maxHistoryChars` 时从最早消息开始裁剪。

### 7.3 processedMessageKeys

```java
ConcurrentHashMap<String, Instant> processedMessageKeys
```

去重规则：

1. `dedupKey = qiyu:{platformMessageId}`。
2. 使用 `putIfAbsent`，只有首次写入成功才调用 OpenHarness。
3. 重复消息直接 ACK。
4. 第一版不记录 `SUCCESS`、`TIMEOUT`、`INVALID_JSON` 等状态对象。
5. 第一版不做失败自动重试。
6. 过期清理时按时间删除旧 key。

## 8. OpenHarness 输入 JSON 最小协议

Java 传给 OpenHarness 的 JSON：

```json
{
  "conversationId": "qiyu:6383959733",
  "platformSessionId": "6383959733",
  "platformUserId": "81275614-ff4c-490e-9517-0934f4fc9325@顺风车乘客",
  "staffId": "4126122",
  "message": "OCR 服务一直报 401，帮我看下",
  "history": [
    {
      "role": "user",
      "content": "OCR 服务怎么接入？"
    }
  ],
  "agentState": {
    "terminal": false
  }
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `conversationId` | Java 内部会话 ID，格式 `qiyu:{session_id}`。 |
| `platformSessionId` | 七鱼 `session_id` 字符串，供 OpenHarness 七鱼 Tool 使用。 |
| `platformUserId` | 七鱼 `foreign_id`，无值时为空字符串，不使用 `user_id`。 |
| `staffId` | 七鱼 `staff_id` 字符串，无值时为空字符串。 |
| `message` | 当前访客文本消息。 |
| `history` | 最近访客文本消息列表。 |
| `agentState` | 上轮 OpenHarness 返回的 `newState`；没有时使用 `{ "terminal": false }`。 |

明确不传：

1. `platform`：第一版固定七鱼，OpenHarness 可从调用入口或 `conversationId` 前缀判断。
2. `currentMessage.messageType`：Java 已保证只传文本。
3. `currentMessage.createdAt`：第一版 OpenHarness 不依赖消息时间。
4. `platformMessageId`：仅 Java 内部去重使用。
5. `appKey`、`appSecret`、`checksum`。
6. `rawPayload`。
7. 七鱼内部 `user_id`。
8. 服务注册表、服务别名表或文档 URL：这些属于 OpenHarness 侧 Skill/Tool/配置。

## 9. OpenHarness 输出 JSON 最小协议

OpenHarness 返回给 Java 的 JSON：

```json
{
  "conversationId": "qiyu:6383959733",
  "action": "manual_sent",
  "toolResults": [
    {
      "tool": "qiyu_send_message",
      "success": true,
      "summary": "sent manual message"
    }
  ],
  "newState": {
    "terminal": true
  },
  "terminal": true
}
```

字段说明：

| 字段 | Java 行为 |
|---|---|
| `conversationId` | 必须等于当前调用的 conversationId，否则按非法输出处理。 |
| `action` | 只用于日志，不驱动客服业务流程。 |
| `toolResults` | 可选；只写日志或调试摘要，不解释业务含义。 |
| `newState` | 原样覆盖保存到 `ConversationContext.agentState`。 |
| `terminal` | 保存到 `ConversationContext.terminal`，用于是否忽略后续消息。 |

明确不需要：

1. `scenario`：Java 不使用。
2. `serviceId`：Java 不使用。
3. `platformActions`：与 `toolResults` 重复，第一版删除。
4. `replyToUser`：Java 不发送用户消息；如果 OpenHarness 输出该旧字段，Java 必须忽略。

## 10. OpenHarness Skill/Tool 要求

### 10.1 Skill

| Skill | 职责 |
|---|---|
| `paas_customer_service_router` | 总入口，编排子流程。 |
| `paas_intent_classifier` | 判断用户意图和场景。 |
| `paas_service_resolver` | 识别服务和别名。 |
| `paas_clarification_policy` | 生成追问策略和追问文本。 |
| `paas_access_docs_flow` | 查询并发送接入文档。 |
| `paas_service_error_flow` | probe、查日志、ERP 和用户通知。 |
| `paas_response_composer` | 生成用户可见文本。 |

Skill 可以承载服务知识、接入说明、常见错误码、排障 runbook、用户话术策略和示例模板。Skill 不应承载真实密钥，也不应让模型复制 curl 并通过 Bash 执行真实外部调用。

### 10.2 Tool

| Tool | 职责 |
|---|---|
| `qiyu_send_message` | 向七鱼会话发送用户可见消息。 |
| `paas_get_manual_url` | 查询服务接入文档 URL。 |
| `paas_probe_service` | 执行在线 probe。 |
| `paas_query_logs` | 查询错误日志摘要。 |
| `paas_send_erp_message` | 发送 ERP 或内部工单消息。 |
| `paas_emit_alert` | 发送内部告警。 |

真实外部副作用必须由 Tool 或 MCP 完成，不允许模型通过通用 Bash 执行 Skill 中的 curl 示例。原因：

1. Skill 是给模型看的文本，真实 token、header、内部域名或 curl 容易进入上下文、日志或调试输出。
2. Bash 只能看到一段 shell 字符串，难以按"发送七鱼消息""查日志""发 ERP 消息"做细粒度审计、限流和确认。
3. 日志查询、七鱼发送和 ERP 发送需要结构化参数、服务白名单、超时、重试和幂等控制。
4. Java 需要稳定 JSON 摘要，而不是自然语言和 curl 输出混杂。

所有外部调用工具都应：

- 从环境变量、配置文件或安全配置中心读取凭据，不从用户消息读取。
- 不在 `ToolResult.output` 中输出 token/header。
- 对外部响应做长度限制。
- 对 4xx/5xx/timeout 明确分类。
- 有明确超时和重试策略。
- 对发送类操作提供幂等键或等价的重复保护。

### 10.3 qiyu_send_message Tool 协议

入参：

```json
{
  "conversationId": "qiyu:6383959733",
  "platformSessionId": "6383959733",
  "platformUserId": "81275614-ff4c-490e-9517-0934f4fc9325@顺风车乘客",
  "staffId": "4126122",
  "messageType": "TEXT",
  "content": "请问你反馈的是 OCR、TTS 还是 ASR 服务？",
}
```

出参进入 `toolResults` 即可：

```json
{
  "tool": "qiyu_send_message",
  "success": true,
  "summary": "sent text message to qiyu conversation"
}
```

要求：

1. `platformUserId` 使用七鱼 `foreign_id`，没有值时为空字符串。
2. Tool 自己负责七鱼发送 API 鉴权。
3. Tool 自己负责发送幂等、重试和错误处理。
4. Tool 返回错误摘要时不能包含 token、签名或完整响应体。
5. Tool 结果进入 OpenHarness 输出 `toolResults`。

## 11. OpenHarness 命令调用需求

建议命令形态：

```bash
oh --print --output-format json --prompt-file /tmp/paas-input.json
```

Java 行为：

1. 使用临时文件传入 input JSON，避免命令行长度和 shell 转义问题。
2. 使用配置中的 command、args、workingDirectory。
3. 将 `{inputFile}` 替换为临时文件路径。
4. 设置超时，默认 30 秒。
5. 限制并发进程数。
6. stdout 解析为 OpenHarness 输出 JSON。
7. stderr 只写内部日志。
8. 调用完成后删除临时文件。
9. WebFlux 中阻塞调用必须放到 boundedElastic 或受控调度器中。

如果当前 CLI 的 `--output-format json` 包装为 `{"type":"result","text":"..."}`，则 OpenHarness 侧应保证 `text` 本身是可解析的最小输出 JSON，Java 只做最小解析和校验。后续如有必要，可增强 OpenHarness 输出模式，让最终摘要直接作为顶层 JSON 输出。

## 12. 异常处理

| 场景 | Java 行为 |
|---|---|
| 七鱼鉴权失败 | 返回 HTTP 401，不写会话，不调用 OpenHarness。 |
| 忽略类事件 | 返回 ACK，不调用 OpenHarness。 |
| 重复消息 | 返回 ACK，不调用 OpenHarness。 |
| OpenHarness 超时 | kill 子进程，写日志，返回 ACK，不发送兜底消息。 |
| OpenHarness 非法 JSON | 写内部日志，返回 ACK，不发送兜底消息。 |
| OpenHarness 进程异常 | 写内部日志，返回 ACK，不发送兜底消息。 |
| OpenHarness `conversationId` 不匹配 | 按非法输出处理，写内部日志，返回 ACK，不发送兜底消息。 |
| OpenHarness `terminal=true` | 保存 `newState` 和 `terminal=true`，返回 ACK。 |
| OpenHarness `terminal=false` | 保存 `newState` 和 `terminal=false`，返回 ACK。 |

## 13. 安全要求

1. Java 必须校验七鱼请求签名。
2. Java 必须校验 timestamp，防止重放。
3. Java 不能把七鱼 AppSecret 传给 OpenHarness。
4. Java 不能把七鱼 `checksum` 传给 OpenHarness。
5. Java 不能把七鱼内部 `user_id` 作为 `platformUserId` 传给 OpenHarness。
6. Java 不能把 `rawPayload` 传给 OpenHarness。
7. Java 写临时文件时应限制当前进程可读写。
9. Java 不得把 OpenHarness stdout/stderr 原样返回七鱼或用户。
10. Java 不调用七鱼发送消息 API。
11. Java 不维护用户可见兜底话术。
12. OpenHarness Tool 不得把真实凭据写入模型上下文、工具结果或日志。
13. 日志查询 Tool 不得接受任意原始 DSL；应只接受结构化字段并拼接白名单查询。
14. ERP、七鱼发送等发送类 Tool 必须具备幂等或重复保护。

## 14. 配置需求

```yaml
ai-customer-service:
  platform-a:
    qiyu:
      app-key: "${QIYU_APP_KEY}"
      app-secret: "${QIYU_APP_SECRET}"
      timestamp-tolerance-seconds: 300
  openharness:
    command: "oh"
    working-directory: "/Users/admin/PycharmProjects/OpenHarness"
    timeout-millis: 30000
    max-concurrent-processes: 4
    args:
      - "--print"
      - "--output-format"
      - "json"
      - "--prompt-file"
      - "{inputFile}"
  conversation:
    max-conversations: 10000
    max-history-messages: 20
    max-history-chars: 12000
    expire-after-minutes: 120
    ignore-terminal-conversation-messages: true
```

## 15. 验收标准

### 15.1 基础链路

1. 七鱼发送有效文本 `CLIENT_MESSAGE`。
2. Java 完成鉴权和解析。
3. Java 生成最小 OpenHarness 输入 JSON。
4. Java 调用 `oh`。
5. OpenHarness 通过 `qiyu_send_message` Tool 给用户发消息。
6. Java 解析最小输出 JSON。
7. Java 保存 `newState` 和 `terminal`。
8. Java 返回 ACK。
9. Java 不调用七鱼发送消息 API。

### 15.2 多轮状态

1. 第一轮 OpenHarness 返回 `terminal=false` 和 `newState`。
2. Java 保存 `newState`。
3. 第二轮 Java 把上一轮 `agentState` 和访客 history 传给 OpenHarness。
4. Java 不解析 `agentState` 内部业务字段。

### 15.3 最小协议

1. OpenHarness 输入不包含 `platform`、`currentMessage.messageType`、`currentMessage.createdAt`、`platformMessageId`、`user_id`、`appKey`、`appSecret`、`checksum`、`rawPayload`。
2. OpenHarness 输出不要求 `scenario`、`serviceId`、`platformActions`。
3. 如果 OpenHarness 输出 `replyToUser`，Java 忽略。
4. `platformUserId` 必须来自七鱼 `foreign_id`，没有值时为空字符串。

### 15.4 忽略和异常

1. 非文本消息 ACK，不调用 OpenHarness。
2. 已撤回消息 ACK，不调用 OpenHarness。
3. 空内容消息 ACK，不调用 OpenHarness。
4. 重复消息 ACK，不重复调用 OpenHarness。
5. OpenHarness 超时、非法 JSON、进程异常时 ACK，不发送兜底消息。

## 16. 后续演进

第一版不做以下能力：

1. 数据库持久化。
2. Redis 去重或会话共享。
3. 多节点会话一致性。
4. 平台动作明细模型。
5. OpenHarness 调用摘要对象。
6. Java 侧七鱼发送消息。
7. Java 侧 ERP 发送。
8. Java 侧服务识别。
9. Java 侧客服流程编排。
10. 常驻 bridge/daemon 模式。

如后续需要生产级审计、重试、跨节点部署或多平台支持，再引入持久化存储、独立去重记录、调用摘要、平台动作模型、平台适配层或 OpenHarness bridge/daemon。只有当本地 `oh` 单次执行的冷启动延迟和并发成本无法满足生产要求时，才评估常驻模式。

## 17. Java 设计文档生成提示

根据本 SDD 生成 Java 设计文档时，Java 第一版只需要以下核心类：

1. `AiCustomerServiceController`
2. `AiCustomerServiceExecutor`
3. `OpenHarnessClient`
4. `AiCustomerServiceProperties`
5. `QiyuCallbackEvent`
6. `HistoryMessage`
7. `ConversationContext`
8. `OpenHarnessOutput`
9. `OpenHarnessToolResult`

不得生成以下 Java 类：

1. `MessageDedupService`
2. `MessageHistoryService`
3. `AgentStateService`
4. `ConversationStore`
5. `InMemoryConversationStore`
6. `OpenHarnessGateway`
7. `OpenHarnessInputBuilder`
8. `OpenHarnessProcessExecutor`
9. `OpenHarnessResponseParser`
10. `QiyuSignatureVerifier`
11. `QiyuMessageParser`
12. `OpenHarnessPlatformAction`
13. `OpenHarnessInvocationSummary`
14. `AgentStateSnapshot`
15. `ConversationMessage`
16. `ProcessedMessageRecord`
17. `ConversationStatus`
18. `MessageRole`
19. `ProcessedMessageStatus`
20. `QiyuReplyService`
21. `FallbackReplyService`
22. 任何负责用户话术生成、用户消息发送、ERP 业务发送、服务识别或排障流程编排的 Java 类。
