
有道短语音识别API接口提供有道的短语音识别服务，包含了中文和英文的识别功能。您只需要通过调用有道语音识别API，传入待识别的音频文件，并指定要识别的源语言种类，以POST方式请求就可以得到相应的识别结果。

有道语音识别asr 接口HTTPS地址：

`https://openapi.youdao.com/asrapi`

**语音支持：**

格式支持：wav（不压缩，pcm编码，采样率：推荐16k ，编码：16bit位深的单声道），aac，mp3

| 格式    | 代码    |
|-------|-------|
| wav   | wav   |
| aac   | aac   |
| mp3   | mp3   |

>
> 注：上传的文件时长不能超过60s，文件大小不能超过10M。

## 接口调用参数
调用API需要向接口发送以下字段来访问服务。

|字段名 |类型| 含义                                        |必填  | 备注                                           |
|------|-----|----------------------------------------|-----|----------------------------------------------|
|q   |text  | 要翻译的音频文件的Base64编码字符串                    |True | 必须是Base64编码                                  |
|langType   |text   | 源语言                                      |True    | [支持语言](#section-8)                           |
|appKey |text   | 应用 ID                                  |True  | 可在 [应用管理](https://ai.youdao.com/appmgr.s) 查看 |
|salt   |text   | UUID                                    |True| uuid，唯一通用识别码                                 |
| curtime       |text   | 时间戳（秒）                                 | true  | 秒数                                           |
|sign   |text   | 签名，通过sha256(应用ID+q+salt+curtime+密钥)生成  |True| sha256(应用ID+input+salt+curtime+密钥)           |
|signType   |text   | 签名版本                                    |True|    v3                                          |
| format       |text    | 语音文件的格式，wav                            | true  | wav                                          |
| rate       |text  | 采样率， 推荐 16000 采用率                      | true  | 16000                                        |
| channel       |text   | 声道数， 仅支持单声道，请填写固定值1                    | true  | 1                                            |
| type       |text  | 上传类型， 仅支持base64上传，请填写固定值1              | true  | 1                                            |

>签名`sign`生成方法如下：
>1、将请求参数中的 `应用ID "appKey" ` , `Base64编码字符串 "q"` ,`UUID "salt"` , `时间戳 "curTime"`和 `应用密钥` 按照 `应用ID+q+salt+curTime+应用密钥` 的顺序拼接得到字符串 `str` 。
>
>其中，q的计算方式为：`q`=`q前10个字符` + `q长度` + `q后10个字符`（当q长度大于20）或 `input`=`q字符串`（当q长度小于等于20）；

*注意:*

1. 请先将需要翻译的音频文件转换为 Base64 编码
2. 在发送 HTTP 请求之前需要对各字段做 URL encode。
3. 在生成签名拼接 `应用ID+q+salt+curTime+密钥` 字符串时，`q` 不需要做 URL encode，在生成签名之后，发送 HTTP 请求之前才需要对要发送的待翻译文本字段 `q` 做 URL encode。

## 输出结果

响应结果是以json形式输出，包含字段如下表所示：

| 字段    | 含义    |
|-------|-------|
| errorCode | 识别结果错误码，一定存在。<br>详细信息参加 [错误代码列表](#section-9)  |
| result    | 识别结果，识别成功一定存在 |


## 示例

```
{
    "result": [
        "今天天气不错" //识别结果
    ],
    "errorCode": "0",   //错误码。一定存在
}
```

## 支持语言

|英文名    |中文名    |代码 |
|-------|-----|-----|
|   Arabic  |   阿拉伯语    |   ar|
|   Bahasa (Indonesia)  |   巴哈萨语（印度尼西亚） |   in|
|   Cantonese   |   粤语  |   yue|
|   Catalan |   加泰隆语    |   ca|
|   Czech   |   捷克语 |   cs|
|   Danish  |   丹麦语 |   da|
|   Dutch   |   荷兰语 |   nl|
|   Dutch (Belgium) |   荷兰语（比利时）    |   nl-BEL|
|   English (Australia)     |   英语（澳大利亚）    |   en-AUS|
|   English (GB)    |   英语（英国）  |   en-GBR|
|   English (India)     |   英语（印度）  |   en-IND|
|   English (Ireland)   |   英语（爱尔兰） |   en-IRL|
|   English (Scotland)  |   英语（苏格兰） |   en-SCT|
|   English (South Africa)  |   英语（南非）  |   en-ZAF|
|   English (US)    |   英语（美国）  |   en|
|   Finnish |   芬兰语 |   fi|
|   French  |   法语  |   fr|
|   French (Canada) |   法语（加拿大） |   fr-CAN|
|   German  |   德语  |   de|
|   Greek   |   希腊语 |   el|
|   Hebrew  |   希伯来语    |   he|
|   Hindi   |   印地语 |   hi|
|   Hungarian   |   匈牙利语    |   hu|
|   Italian |   意大利语    |   it|
|   Japanese    |   日语  |   ja|
|   Korean  |   韩语  |   ko|
|   Mandarin (China)    |   普通话（中国） |   zh-CHS|
|   Mandarin (Taiwan)   |   普通话（中国台湾）   |   zh-TWN|
|   Norwegian   |   挪威语 |   no|
|   Polish  |   波兰语 |   pl|
|   Portuguese (Brazil)     |   葡萄牙语（巴西）    |   pt-BRA|
|   Portuguese (Portugal)   |   葡萄牙语（葡萄牙）   |   pt|
|   Romanian    |   罗马尼亚语   |   ro|
|   Russian |   俄语  |   ru|
|   Slovak  |   斯洛伐克语   |   sk|
|   Spanish (Castilian) |   西班牙语（卡斯蒂利亚） |   es-ESP|
|   Spanish (Columbia)  |   西班牙语（哥伦比亚）  |   es-COL|
|   Spanish (Mexico)    |   西班牙语（墨西哥）   |   es-MEX|
|   Spanish (Mexico)    |   西班牙语    |   es|
|   Swedish |   瑞典语 |   sv|
|   Thai    |   泰语  |   th|
|   Turkish |   土耳其语    |   tr|


## 错误代码列表

|错误码    |含义|
|-------|----|
|101    |缺少必填的参数，首先确保必填参数齐全，然后，确认参数书写是否正确。|
|102    |不支持的语言类型|
|103    |翻译文本过长|
|104    |不支持的API类型|
|105    |不支持的签名类型|
|106    |不支持的响应类型|
|107    |不支持的传输加密类型|
|108    |应用ID无效，注册账号，登录后台创建应用并完成绑定，可获得应用ID和应用密钥等信息|
|109    |batchLog格式不正确|
|110    |无相关服务的有效应用，应用没有绑定服务，可以新建服务。注：某些服务的结果发音需要tts服务，需要在控制台创建语音合成实例绑定应用后方能使用。|
|111    |开发者账号无效|
|112    |请求服务无效 |
|113    |q不能为空|
|114    |不支持的图片传输方式|
|201    |解密失败，可能为DES,BASE64,URLDecode的错误|
|202    |签名检验失败，如果确认应用ID和应用密钥的正确性，仍返回202，一般是编码问题。请确保翻译文本 `q` 为UTF-8编码.|
|203    |访问IP地址不在可访问IP列表|
|205    |请求的接口与应用的平台类型不一致，确保接入方式（Android SDK、IOS SDK、API）与创建的应用平台类型一致。如有疑问请参考[入门指南](https://ai.youdao.com/doc.s#guide)|
|206    |因为时间戳无效导致签名校验失败|
|207    |重放请求|
|301    |辞典查询失败|
|302    |翻译查询失败|
|303    |服务端的其它异常|
|304    |会话闲置太久超时|
|401    |账户已经欠费停|
|402    |offlinesdk不可用|
|411    |访问频率受限,请稍后访问   |
|412    |长请求过于频繁，请稍后访问  |
|1001   |无效的OCR类型|
|1002   |不支持的OCR image类型|
|1003   |不支持的OCR Language类型|
|1004   |识别图片过大|
|1201   |图片base64解密失败|
|1301   |OCR段落识别失败|
|1411   |访问频率受限|
|1412   |超过最大识别字节数|
|2003   | 不支持的语言识别Language类型|
|2004   | 合成字符过长 |
|2005   | 不支持的音频文件类型    |
|2006   | 不支持的发音类型  |
|2201   | 解密失败  |
|2301   | 服务的异常 |
|2411   | 访问频率受限,请稍后访问|
|2412   | 超过最大请求字符数|
|3001   | 不支持的语音格式  |
|3002   | 不支持的语音采样率 |
|3003   | 不支持的语音声道|
|3004   | 不支持的语音上传类型    |
|3005   | 不支持的语言类型  |
|3006   | 不支持的识别类型  |
|3007   | 识别音频文件过大  |
|3008   | 识别音频时长过长  |
|3009   | 不支持的音频文件类型|
|3010   | 不支持的发音类型|
|3201   | 解密失败|
|3301   | 语音识别失败|
|3302   | 语音翻译失败    |
|3303   | 服务的异常 |
|3411   | 访问频率受限,请稍后访问|
|3412   | 超过最大请求字符数|
|4001   | 不支持的语音识别格式    |
|4002   | 不支持的语音识别采样率   |
|4003   | 不支持的语音识别声道    |
|4004   | 不支持的语音上传类型    |
|4005   | 不支持的语言类型  |
|4006   | 识别音频文件过大  |
|4007   | 识别音频时长过长  |
|4201   | 解密失败  |
|4301   | 语音识别失败    |
|4303   | 服务的异常 |
|4304   | 识别结果为空    |
|4411   | 访问频率受限,请稍后访问  |
|4412   | 超过最大请求时长  |
| 4416    | 包含不合时宜词汇    |
|4414        | 音频格式转换失败   |
|5001   | 无效的OCR类型|
|5002   | 不支持的OCR image类型|
|5003   | 不支持的语言类型  |
|5004  | 识别图片过大|
|5005  | 不支持的图片类型|
|5006  | 文件为空|
|5201  | 解密错误，图片base64解密失败  |
|5301  | OCR段落识别失败|
|5411  | 访问频率受限|
|5412  | 超过最大识别流量   |
|9001  |   不支持的语音格式    |
|9002  |   不支持的语音采样率  |
|9003  |   不支持的语音声道    |
|9004  |   不支持的语音上传类型    |
|9005  |   不支持的语音识别 Language类型   |
|9301  |   ASR识别失败 |
|9303  | 服务器内部错误    |
|9411  |   访问频率受限（超过最大调用次数）    |
|9412  |   超过最大处理语音长度 |
|10001  |无效的OCR类型|
|10002  |不支持的OCR image类型|
|10004  |识别图片过大|
|10201  |图片base64解密失败|
|10301  |OCR段落识别失败|
|10411  |访问频率受限|
|10412  |超过最大识别流量|
|11001  | 不支持的语音识别格式    |
|11002  | 不支持的语音识别采样率   |
|11003  | 不支持的语音识别声道    |
|11004  | 不支持的语音上传类型    |
|11005  | 不支持的语言类型  |
|11006  | 识别音频文件过大  |
|11007  | 识别音频时长过长，最大支持30s  |
|11201  | 解密失败  |
|11301  | 语音识别失败    |
|11303  | 服务的异常 |
|11411  | 访问频率受限,请稍后访问  |
|11412  | 超过最大请求时长  |
|12001  | 图片尺寸过大    |
|12002  | 图片base64解密失败  |
|12003  | 引擎服务器返回错误     |
|12004  | 图片为空  |
|12005  | 不支持的识别图片类型    |
|12006  |图片无匹配结果|
|13001  | 不支持的角度类型  |
|13002  | 不支持的文件类型  |
|13003  | 表格识别图片过大  |
|13004 |文件为空|
|13301  | 表格识别失败    |
|15001|需要图片|
|15002|图片过大（1M）|
|15003|服务调用失败|
|17001  |需要图片|
|17002  |图片过大（1M）|
|17003  |识别类型未找到|
|17004  |不支持的识别类型|
|17005  |服务调用失败|


## 常用语言 Demo
### Python3 示例
```python
# -*- coding: utf-8 -*-
import sys
import uuid
import requests
import wave
import base64
import hashlib

from imp import reload

import time

reload(sys)

YOUDAO_URL = 'https://openapi.youdao.com/asrapi'
APP_KEY = '您的应用ID'
APP_SECRET = '您的应用密钥'

def truncate(q):
    if q is None:
        return None
    size = len(q)
    return q if size <= 20 else q[0:10] + str(size) + q[size-10:size]

def encrypt(signStr):
    hash_algorithm = hashlib.sha256()
    hash_algorithm.update(signStr.encode('utf-8'))
    return hash_algorithm.hexdigest()

def do_request(data):
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    return requests.post(YOUDAO_URL, data=data, headers=headers)

def connect():
    audio_file_path = '音频的路径'
    lang_type = '合成文本的语言类型'
    extension = audio_file_path[audio_file_path.rindex('.')+1:]
    if extension != 'wav':
        print('不支持的音频类型')
        sys.exit(1)
    wav_info = wave.open(audio_file_path, 'rb')
    sample_rate = wav_info.getframerate()
    nchannels = wav_info.getnchannels()
    wav_info.close()
    with open(audio_file_path, 'rb') as file_wav:
        q = base64.b64encode(file_wav.read()).decode('utf-8')

    data = {}
    curtime = str(int(time.time()))
    data['curtime'] = curtime
    salt = str(uuid.uuid1())
    signStr = APP_KEY + truncate(q) + salt + curtime + APP_SECRET
    sign = encrypt(signStr)
    data['appKey'] = APP_KEY
    data['q'] = q
    data['salt'] = salt
    data['sign'] = sign
    data['signType'] = "v2"
    data['langType'] = lang_type
    data['rate'] = sample_rate
    data['format'] = 'wav'
    data['channel'] = nchannels
    data['type'] = 1

    response = do_request(data)
    print(response.content)

if __name__ == '__main__':
    connect()

```