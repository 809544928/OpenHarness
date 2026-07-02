# OpenHarness PaaS 智能客服 发送qiyu消息 设计

## 1. 背景与目标

[paas-customer-service](../../.openharness/plugins/paas-customer-service) 分析该插件agent功能, 需要在某些时刻qiyu消息, 向用户提问, 我即将提供调用qiyu的方式, 请帮我完成该部分

## 2. 调用方式

1. **调用endpoint**：http://localhost:8686/http/ai-customer-service/qiyu-sendMsg,
2. **请求方式**：post, 格式为json body, 请求头用来鉴权, Admin-Token = 18298622-9615-4F17-9287-F5EA77CAC96D, 默认为这个串, 从环境变量 {ADMIN_TOKEN} 获取.
3. **请求参数**：

| 请求参数      | 描述                                              |
|-----------|-------------------------------------------------|
| uid       | 访客id, 对应上游传进来的  'platformUserId', 如果为空就设置为空串:"" |
| sessionId | 会话id, 对应上游传进来的 'platformSessionId'              |
| content | 内容                                              |

4. **响应格式**：

| 响应参数   | 描述       |
|--------|----------|
| code   | 200 代表成功 |

