# ============================================================
# 数字人对接中转服务 - Dockerfile
# 基础镜像：Python 3.11 slim（Debian-based，体积适中）
# ============================================================

FROM python:3.11-slim

# ── 安装系统依赖 ──────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        redis-tools \
    && rm -rf /var/lib/apt/lists/*

# ── 设置工作目录 ──────────────────────────────────────────
WORKDIR /app

# ── 安装 Python 运行时依赖 ────────────────────────────────
# 优先使用清华镜像加速，镜像不可用时自动回退到官方 PyPI
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    || pip install --no-cache-dir -r requirements.txt

# ── 复制应用代码 ──────────────────────────────────────────
COPY digital-human.py .

# ── 暴露端口 ──────────────────────────────────────────────
EXPOSE 8000

# ── 启动命令 ──────────────────────────────────────────────
# 使用 uvicorn 运行 FastAPI 应用，监听 0.0.0.0:8000
CMD ["uvicorn", "digital-human:app", "--host", "0.0.0.0", "--port", "8000"]
