# OpenHarness PaaS 智能客服 查询日志

## 1. 背景与目标

[paas-customer-service](../../.openharness/plugins/paas-customer-service) 分析该插件agent功能, 需要在某些时刻查询日志, 以下是查日志的具体实现

## 2. 调用方式

1. **调用endpoint**：https://o2log.corp.youdao.com/api/aicloud/_search
2. **请求方式**：post, 格式为json body, 请求头有 Authorization: Basic YWkucHVibGljQHJkLm5ldGVhc2UuY29tOk5XTHZrRnhSb2pQQzh1Tk0=
3. **请求参数**：以下是请求参数示例, 
```
{
  "query": {
    "from": 0,
    "size": 100,
    "sql": "SELECT * FROM \"{stream_name}\" WHERE body LIKE '\''%{queryInfo}%'\'' ORDER BY _timestamp DESC",
    "start_time": 1782891493000000,
    "end_time": 1782892693000000
  }
}
```
其中stream_name来自于[paas-services.example.yaml](../../.openharness/plugins/paas-customer-service/config/paas-services.example.yaml) 的 log.stream_name,
queryInfo优先使用requestId, 如果不存在requestId使用appKey,
start_time和end_time分别是毫秒时间戳追加三个0

## 3. 其他补充: 
参考 [paas-customer-service](../../.openharness/plugins/paas-customer-service), 我希望在 向用户提问 requestId / appKey等信息时候, 也会提问大概的时间点, 因为我的查日志接口需要start_time和end_time两个时间参数, 这怎么智能实现呢



