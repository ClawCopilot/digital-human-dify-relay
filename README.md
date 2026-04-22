# 数字人对接中转服务

基于 Docker Compose 部署的数字人对接中转服务，连接客户端与 Dify LLM 平台，支持流式与非流式对话、多轮会话上下文（Redis 缓存）。

## 目录

- [架构](#架构)
- [快速部署](#快速部署)
- [接口说明](#接口说明)
- [环境变量](#环境变量)
- [端口说明](#端口说明)
- [本地测试](#本地测试)
- [常见问题](#常见问题)
- [生产部署](#生产部署)
- [目录结构](#目录结构)

---

## 架构

```
Client  -->  Nginx/Traefik(反向代理)  -->  digital-human(:8000)  -->  Dify LLM Platform
                      |                        |
                      |                        +-->  Redis(:6379, 容器内网)
```

- **digital-human**：FastAPI 中转服务，转发请求至 Dify 并统一响应格式
- **Redis**：存储 session_id 与 dify conversation_id 的映射关系，支持多轮对话
- 两者通过 Docker Compose 内部 DNS (`redis`) 通信，不占用宿主机端口

---

## 快速部署

### 1. 克隆项目

```bash
git clone https://github.com/ClawCopilot/digital-human-dify-relay.git
cd digital-human-dify-relay
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入以下两个必填变量
```

`.env` 必填项：

```env
# Dify 服务地址（末尾不要加 /chat-messages，代码会自动拼接）
DIFY_URL=https://your-dify-domain.com/v1

# Dify API 密钥（纯密钥，不要加 Bearer 前缀）
DIFY_API_KEY=app-PDkSHiHZsZIluoZF7N2OlNZM
```

### 3. 启动服务

```bash
docker compose up -d
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/

# 重启后确认容器状态（healthy 表示正常）
docker ps | grep digital-human
```

---

## 接口说明

### `POST /digital-human`

数字人中转核心接口。

**请求体：**

```json
{
  "messages": [
    { "content": "你好，请用一句话介绍自己。" }
  ],
  "app_id": "app-xxxxxxxx",
  "user": "user-001",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "is_stream": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `messages` | `Array` | ✅ | 消息列表，目前只取第一条 `content` 作为 Dify query |
| `app_id` | `string` | ✅ | Dify 应用 ID |
| `user` | `string` | ✅ | 用户标识，用于 Dify 会话上下文 |
| `session_id` | `string` | ✅ | 会话 ID，用于关联多轮对话上下文，留空自动生成 |
| `is_stream` | `boolean` | ✅ | `true` = SSE 流式响应，`false` = 非流式阻塞返回 |

**响应（非流式 is_stream=false）：**

```json
{
  "id": "131424542124",
  "created": 20230512084843,
  "choices": [
    {
      "index": 0,
      "message": {
        "content": "你好！我是..."
      }
    }
  ]
}
```

**响应（流式 is_stream=true）：**

SSE 格式，每个 chunk：

```
data: {"id":"1231414141541252525","created":20230512084843,"choices":[{"message":{"content":"你"}}]}

data: {"id":"1231414141541252525","created":20230512084843,"choices":[{"message":{"content":"好"}}]}

...

data: [DONE]
```

---

### `GET /`

健康检查端点，用于 Docker healthcheck 和外部监控。

```json
{ "status": "ok" }
```

---

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|:---|:---:|:---|:---|
| `DIFY_URL` | ✅ | — | Dify 服务地址，如 `https://atwdify.antiwearvalve.com/v1` |
| `DIFY_API_KEY` | ✅ | — | Dify API 密钥（纯密钥，不要加 `Bearer ` 前缀） |
| `REDIS_HOST` | 否 | `redis` | Redis 主机，Docker Compose 内部 DNS，始终填 `redis` |
| `REDIS_PORT` | 否 | `6379` | Redis 端口 |
| `DH_PORT` | 否 | `8000` | 宿主机映射端口 |

> **注意**：`DIFY_URL` 末尾不要包含 `/chat-messages`，代码会自动拼接。

---

## 端口说明

| 端口 | 服务 | 说明 |
|:---|:---|:---|
| `${DH_PORT:-8000}` | digital-human | 中转服务，通过反向代理或直连访问 |
| — | Redis | **默认不暴露**，仅在 Docker 容器网络内部互通 |

如需从宿主机直连 Redis，合并 `docker-compose.redis-expose.yml`：

```bash
docker compose -f docker-compose.yml -f docker-compose.redis-expose.yml up -d
```

---

## 本地测试

项目内置两个测试页面：

| 文件 | 用途 | 访问方式 |
|:---|:---|:---|
| `test.html` | 测试中转服务 `/digital-human` 接口 | 浏览器直接打开或部署后访问 |
| `test-dify.html` | 直连 Dify API，跳过中转 | 浏览器直接打开 |

### test.html 使用方法

1. 打开 `test.html`
2. 填写**中转服务地址**，如 `https://chat-agent-demo.aigc-quickapp.com`
3. 填写 Session ID（留空自动生成）
4. 填写 App ID（对应 Dify 应用）
5. 填写 User
6. 填写测试消息
7. 点击**发送请求**

---

## 常见问题

### Q：容器状态为 unhealthy？

执行以下命令查看具体报错：

```bash
docker compose logs digital-human
```

常见原因：
- `.env` 中 `DIFY_URL` 或 `DIFY_API_KEY` 未填写或格式错误
- Redis 连接失败（确保 `REDIS_HOST=redis` 且两个容器在同一网络）

### Q：POST /digital-human 返回 500？

通常是 Dify 请求失败。检查：
- `.env` 中 `DIFY_URL` 是否正确（末尾是否为 `/v1`）
- `DIFY_API_KEY` 是否有效
- 服务器能否访问 Dify 地址：`curl -I $DIFY_URL`

### Q：Redis Connection refused？

确认 `docker-compose.yml` 中 `REDIS_HOST: "redis"` 生效，且 Redis 容器正常运行：

```bash
docker ps | grep redis
docker compose logs redis
```

### Q：外网无法访问服务？

1. 检查容器是否正常：`docker ps` 状态应为 `healthy`
2. 检查防火墙：`sudo ufw allow 8000/tcp`（或对应端口）
3. 通过域名访问时检查反向代理配置是否正确转发到容器端口

---

## 生产部署

1. **反向代理**：在 digital-human 前配置 Nginx/Caddy 进行 TLS termination
2. **HTTPS**：生产环境务必使用 HTTPS
3. **环境变量**：`.env` 不要提交到代码仓库，已在 `.gitignore` 中排除
4. **Redis 高可用**：可替换为外部 Redis 集群，修改 `REDIS_HOST`
5. **域名配置**：将域名 DNS 解析到服务器，通过反向代理转发到容器端口

---

## 目录结构

```
.
├── docker-compose.yml                # 主容器编排（Redis 默认内部模式）
├── docker-compose.redis-expose.yml  # Redis 端口暴露扩展（按需合并）
├── Dockerfile                        # 应用镜像构建
├── digital-human.py                  # FastAPI 中转服务源码
├── requirements.txt                  # Python 依赖
├── .env.example                      # 环境变量模板
├── test.html                         # 中转服务测试页面
├── test-dify.html                    # Dify 直连测试页面
├── downloads/                        # 独立部署包（Systemd + Shell）
└── README.md                         # 本文件
```
