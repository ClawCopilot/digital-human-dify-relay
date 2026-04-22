"""
数字人对接中转服务
-----------------
作为客户端与 Dify LLM 平台之间的中间转发层，处理请求路由、
认证转发及 Redis 缓存，提升响应效率并保护后端 API Key。

环境变量：
    DIFY_URL      - Dify 服务地址，如 https://atwdify.antiwearvalve.com/v1
    DIFY_API_KEY  - Dify API 密钥，如 app-PDkSHiHZsZIluoZF7N2OlNZM
    REDIS_HOST    - Redis 主机地址，默认 localhost
    REDIS_PORT    - Redis 端口，默认 6379
"""

import os
import json
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# ──────────────────────────────────────────────────────────────
# 日志配置
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("digital-human")

# ──────────────────────────────────────────────────────────────
# 应用配置（从环境变量读取）
# ──────────────────────────────────────────────────────────────
DIFY_URL: str = os.getenv("DIFY_URL", "")
DIFY_API_KEY: str = os.getenv("DIFY_API_KEY", "")
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

# 验证必填配置
if not DIFY_URL or not DIFY_API_KEY:
    logger.warning(
        "DIFY_URL 或 DIFY_API_KEY 未配置，"
        "部分功能可能不可用。请通过环境变量设置。"
    )

# ──────────────────────────────────────────────────────────────
# Redis 客户端（懒加载）
# ──────────────────────────────────────────────────────────────
_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """获取 Redis 客户端实例（延迟初始化）。"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5,
        )
    return _redis_client


def get_cache_key(payload: Dict[str, Any]) -> str:
    """根据请求体生成 Redis 缓存键。"""
    raw = json.dumps(payload, sort_keys=True)
    return f"dh:cache:{hashlib.md5(raw.encode()).hexdigest()}"


# ──────────────────────────────────────────────────────────────
# FastAPI 应用生命周期
# ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动 / 关闭钩子。"""
    logger.info("数字人对接服务启动中...")
    logger.info(f"  Dify URL : {DIFY_URL}")
    logger.info(f"  Redis    : {REDIS_HOST}:{REDIS_PORT}")

    # 尝试连接 Redis（仅记录，不阻塞启动）
    try:
        get_redis().ping()
        logger.info("Redis 连接成功")
    except RedisConnectionError as e:
        logger.warning(f"Redis 连接失败（服务将继续运行）: {e}")

    yield

    logger.info("数字人对接服务已关闭")


app = FastAPI(
    title="数字人对接中转服务",
    version="1.0.0",
    description="对接 Dify LLM 平台的数字人应用中转服务",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────────────────────
# 健康检查
# ──────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    """服务健康检查端点。"""
    return {
        "status": "ok",
        "service": "digital-human-relay",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """详细健康检查（包含 Redis 状态）。"""
    redis_ok = False
    try:
        get_redis().ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "dify_configured": bool(DIFY_URL and DIFY_API_KEY),
    }


# ──────────────────────────────────────────────────────────────
# Dify 响应格式转 OpenAI 兼容格式
# ──────────────────────────────────────────────────────────────
def dify_to_openai(dify_resp: Dict[str, Any], model: str = "dify") -> Dict[str, Any]:
    """
    将 Dify /chat-messages 的响应转换为 OpenAI /chat/completions 兼容格式。
    Dify 响应示例: { answer: "...", conversation_id: "...", task_id: "..." }
    OpenAI 目标格式: { id, model, choices: [{ message: { role: "assistant", content: "..." } }] }
    """
    return {
        "id": f"chatcmpl-{dify_resp.get('task_id', 'unknown')}",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": dify_resp.get("answer", ""),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


# ──────────────────────────────────────────────────────────────
# 核心转发接口
# ──────────────────────────────────────────────────────────────
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    接收 OpenAI 兼容格式请求，转换为 Dify /chat-messages 格式后转发。
    OpenAI 格式: { model, messages: [{role, content}], stream }
    Dify 格式:   { query, user, response_mode, inputs }
    """
    body = await request.json()

    # ── 格式转换：OpenAI -> Dify ──────────────────────────────
    # 提取用户最新消息
    user_content = ""
    for msg in reversed(body.get("messages", [])):
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break

    if not user_content:
        raise HTTPException(status_code=400, detail="未找到用户消息")

    # 生成或复用 user 标识（用于 Dify 会话上下文）
    dify_user = body.get("user", "anonymous")
    response_mode = "blocking" if not body.get("stream", False) else "streaming"

    # 构建 Dify 请求体
    dify_payload = {
        "query": user_content,
        "user": dify_user,
        "response_mode": response_mode,
        "inputs": body.get("inputs", {}),
    }

    # 若应用要求 inputs 字段但为空，补上空对象
    if "inputs" not in dify_payload or dify_payload["inputs"] is None:
        dify_payload["inputs"] = {}

    # ── 检查 Redis 缓存（基于 OpenAI 原始请求体）──────────────
    cache_key = get_cache_key(body)
    try:
        cached = get_redis().get(cache_key)
        if cached:
            logger.info(f"缓存命中: {cache_key}")
            return dify_to_openai(json.loads(cached), model=body.get("model", "dify"))
    except RedisConnectionError:
        logger.warning("Redis 不可用，跳过缓存读取")

    # ── 转发到 Dify ─────────────────────────────────────────
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    dify_endpoint = f"{DIFY_URL.rstrip('/')}/chat-messages"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(dify_endpoint, json=dify_payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Dify 返回错误 {e.response.status_code}: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Dify 请求失败: {e.response.text}",
        )
    except httpx.RequestError as e:
        logger.error(f"无法连接 Dify 服务: {e}")
        raise HTTPException(status_code=502, detail=f"无法连接 Dify 服务: {e}")

    # ── 写入缓存（存 Dify 原始格式）───────────────────────────
    try:
        get_redis().setex(cache_key, 300, json.dumps(result))
    except RedisConnectionError:
        pass

    # ── 响应转 OpenAI 兼容格式 ─────────────────────────────────
    return dify_to_openai(result, model=body.get("model", "dify"))


# ──────────────────────────────────────────────────────────────
# 错误处理器
# ──────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": str(exc)},
    )
