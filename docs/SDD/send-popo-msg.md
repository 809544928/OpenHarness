# OpenHarness PaaS 智能客服 发送popo消息 设计

## 1. 背景与目标

[paas-customer-service](../../.openharness/plugins/paas-customer-service) 插件中的智能客服相关skill和tool, 需要在某些时刻发送ERP消息通知客服人员, erp名为popo, 目前该环节属于mock, 我即将提供调用popo的方式, 请帮我完成该部分

## 2. 调用方式

1. **调用endpoint**：https://open.popo.netease.com/open-apis/robots/v1/hook/zZVZJrtOORw3LNEvJWUKjQUNLtBmxUBk9CKT3MLCVVNQ17HdJXTLF5DIA7LzbgFjOO5RYWFMdSSqBEltdVblYsrJPIbiBZOP
2. **请求方式**：post, 格式为json body
3. **请求参数**：message, timestamp()

| 参数       | 描述                                                           |
|----------|--------------------------------------------------------------|
| message    | 消息体正文, 消息体开头必须增加固定前缀: "[aicloud-customer-service]", 然后拼接消息正文 |
| timestamp       | 当前毫秒时间戳                                                      |

4. **响应格式**：

| 参数      | 描述      |
|---------|---------|
| errcode | 0代表成功   |
| errmsg  | 错误信息    |
| data    | 包含msgId |

## 3. 其他补充
1. **message的消息正文内容**：调用 probe_service 工具的结果, 以及调用 query_logs 工具的结果. 如果缺少某部分结果, 不展示即可.