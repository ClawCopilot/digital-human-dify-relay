# 数字人对接中转服务

基于 Docker Compose 部署的数字人对接中转服务，连接客户端与 Dify LLM 平台。

## 架构

```
Client  -->  digital-human (8000)  -->  Dify LLM Platform
                    |
                    +-->  Redis (6379)
```

## 快速部署

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 DIFY_URL 和 DIFY_API_KEY
```

### 2. 启动服务

```bash
docker compose up -d
```

### 3. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# 转发测试（chat/completions）
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-model",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

## 端口说明

| 端口 | 服务 | 说明 |
|:---|:---|:---|
| 8000 | digital-human | 中转服务，对外暴露 |
| 6379 | Redis | 仅容器内部使用 |

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `DIFY_URL` | 是 | - | Dify 服务地址，如 `https://xxx.com/v1` |
| `DIFY_API_KEY` | 是 | - | Dify API 密钥 |
| `REDIS_HOST` | 否 | `redis` | Redis 主机（Docker Compose 内部 DNS） |
| `REDIS_PORT` | 否 | `6379` | Redis 端口 |

## 生产部署注意事项

1. **防火墙**：确保服务器 TCP 8000 端口对外部开放
2. **HTTPS**：生产环境建议在 `digital-human` 前加一层 Nginx/Caddy 反向代理， termination TLS
3. **环境变量**：不要将密钥提交到代码仓库，`.env` 已加入 `.gitignore`
4. **Redis**：生产环境可移除内建 Redis，连接外部 Redis 集群

## 目录结构

```
.
├── docker-compose.yml    # 容器编排配置
├── Dockerfile            # 应用镜像构建
├── digital-human.py      # FastAPI 中转服务源码
├── requirements.txt      # Python 依赖
├── .env.example          # 环境变量示例
└── README.md             # 本文件
```
