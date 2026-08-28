# ============================================================
# A3 多智能体学习系统 — 后端 Dockerfile
# 构建上下文为 backend/ 目录（Zeabur 等平台按服务目录部署）
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# 仅复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ============================================================
# Runtime 镜像
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# 安装运行时系统依赖（chromadb / faiss / lxml 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 Python 包
COPY --from=builder /install /usr/local

# 复制后端代码（构建上下文内的全部文件）
COPY . .

# 创建运行时目录
RUN mkdir -p /app/static/mindmap /app/static/uploads /app/data/profiles

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=3)" || exit 1

# 启动服务（关闭 reload，容器环境无需热重载）
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
