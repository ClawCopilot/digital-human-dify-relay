一、部署数字人对接服务

第一步、登录到服务器上，需要对外部署一个中转服务。

1. 执行对接脚本
在中转服务器上，执行一下脚本。

- Dify_IP: Dify 服务的 IP 地址。如：https://atwdify.antiwearvalve.com/v1
- API_KEY: Dify 服务的 API 密钥。如：app-PDkSHiHZsZIluoZF7N2OlNZM

```bash
wget -O /tmp/digital-human.sh \
  https://documentation-samples.obs.cn-north-4.myhuaweicloud.com/solution-as-code-publicbucket/solution-as-code-moudle/building-a-dify-llm-application-development-platform/human/digital-human.sh \
  && bash /tmp/digital-human.sh {Dify_IP} {API_KEY}
```

2. 验证中转服务状态是否正常

检查数字人对接中转服务是否正常运行：
```bash
systemctl status digital-human.service
```
当看到 active (running) 时表示服务启动成功

3. 配置防火墙规则

配置防火墙规则，允许外部访问数字人对接服务：
```bash
• 优先级：1
• 协议端口：TCP 8000
• 源地址：0.0.0.0/0
```

4. 验证外部访问
使用 curl 命令测试外部访问：
```bash
curl http://{中转服务器IP}:8000
# 例如：使用IP地址
curl http://192.168.1.100:8000

# 例如：使用域名
curl http://atwdify.antiwearvalve.com:8000
```

二、MetaStudio数字人平台配置

1. 进入智能交互配置
登录华为云MetaStudio控制台 → 我的创作 → 智能交互 → 创建对话

2. 填写配置参数
| 配置项 | 填写内容 |
|------|------|
|  第三方应用 |  选择「第三方大脑(大模型)」 |
|  应用名称 | 自定义，如「智能客服数字人」 |
| APPID | 898675431（默认）|
| API Key | 第三步获取的Dify API密钥，例如： app-PDkSHiHZsZIluoZF7N2OlNZM|
| 第三方语言模型地址 | http://{中转服务器IP}:8000/digital-human， 例如：http://atwdify.antiwearvalve.com:8000/digital-human|
