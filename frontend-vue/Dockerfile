# ============================================================
# A3 多智能体学习系统 — 前端 Dockerfile
# 构建上下文为项目根目录（由 docker-compose 传入）
# ============================================================

# ---- Build Stage ----
FROM node:20-alpine AS build

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY frontend-vue/package.json frontend-vue/package-lock.json ./
RUN npm ci

# 复制源码并构建
COPY frontend-vue/ .
RUN npm run build


# ---- Runtime Stage (Nginx) ----
FROM nginx:alpine

# 复制构建产物
COPY --from=build /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY frontend-vue/nginx.conf /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 80

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
