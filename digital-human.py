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
# 核心转发接口
# ──────────────────────────────────────────────────────────────
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    转发 chat/completions 请求到 Dify。
    支持缓存（可选）：相同请求体会命中 Redis 缓存。
    """
    # 读取请求体
    body = await request.json()

    # 检查 Redis 缓存
    try:
        r = get_redis()
        cache_key = get_cache_key(body)
        cached = r.get(cache_key)
        if cached:
            logger.info(f"缓存命中: {cache_key}")
            return json.loads(cached)
    except RedisConnectionError:
        logger.warning("Redis 不可用，跳过缓存读取")

    # 构建转发请求头
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }

    # 转发到 Dify（Dify 原生端点 /chat-messages）
    # 确保 body 包含 inputs 字段（Dify 应用可能要求此字段）
    if "inputs" not in body:
        body["inputs"] = {}

    dify_endpoint = f"{DIFY_URL.rstrip('/')}/chat-messages"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                dify_endpoint,
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Dify 返回错误状态码 {e.response.status_code}: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Dify 请求失败: {e.response.text}",
        )
    except httpx.RequestError as e:
        logger.error(f"无法连接 Dify 服务: {e}")
        raise HTTPException(status_code=502, detail=f"无法连接 Dify 服务: {e}")

    # 写入 Redis 缓存（TTL = 300 秒）
    try:
        r = get_redis()
        r.setex(cache_key, 300, json.dumps(result))
    except RedisConnectionError:
        pass

    return result


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
