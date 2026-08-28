# 个性化学习助手（Personalized Learning Assistant）

基于多智能体（Multi-Agent）架构的 AI 个性化学习平台。通过多个分工明确的智能体（Agent）协作，覆盖**学生画像构建 → 学习路径规划 → 智能辅导 → 技能差距分析 → 真实练习 → 知识库问答**的完整学习闭环。

后端采用 FastAPI + LangGraph，前端为 Vue 3，支持 SSE / WebSocket 流式交互。LLM 默认接入讯飞星火，可无缝切换智谱 GLM、通义千问。

---

## ✨ 功能特性

- **对话式画像构建** — 通过分步对话自动采集学生信息，生成 ≥6 维度的动态学生画像，雷达图可视化
- **个性化学习路径规划**
  - 一次性生成：基于画像 + 时间约束，输出分阶段、带每日任务的学习路径
  - 交互式联网规划：三阶段对话，联网搜索市场需求与练习资源，支持中途确认、修改、补充资源
  - 标准模板：内置数据分析 / 统计学等成熟路径模板，命中关键词直接秒出稳定结构
- **智能辅导** — 多模态解答学生疑问，支持联网搜索获取最新信息
- **技能差距分析** — 对比「学生画像技能」与「目标岗位 JD 需求」，输出雷达图双系列差距数据
- **真实练习卡搜索** — 按知识点从牛客、LeetCode、洛谷、AcWing、PTA 等 OJ 平台搜索真实题目
- **资源生成** — 按资源类型（视频 / 文档 / 思维导图等）使用专用模型生成学习资源
- **知识库问答（RAG）** — 上传文档（PDF / Word 等）建立向量库，结合讯飞知识库进行检索增强问答
- **练习与错题管理** — 每日练习、打卡、错题收集与重做、AI 批改
- **流式体验** — SSE 流式生成、WebSocket 实时交互、思维导图（markmap）可视化

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 · FastAPI · Uvicorn · LangGraph · SQLAlchemy |
| 前端 | Vue 3 · Vite · Pinia · Element Plus · ECharts · markmap · mermaid |
| 大模型 | 讯飞星火 Spark（默认）· 智谱 GLM · 通义千问 Dashscope（OpenAI 兼容） |
| 存储 | MySQL（可选，可降级文件存储）· Redis（可选，可降级内存缓存）· ChromaDB / FAISS 向量检索 |
| 部署 | Docker（后端 / 前端 Nginx 各一个镜像） |

## 📁 项目结构

```
A3_agent/
├── backend/                  # FastAPI 后端
│   ├── api/                  # 路由层（onboarding / online / 主路由）
│   ├── core/
│   │   ├── capabilities/     # 智能体实现（画像 / 路径 / 辅导 / 技能差距 / 练习搜索等）
│   │   ├── config.py         # 模型与全局配置（从 .env 读取）
│   │   ├── graph.py          # LangGraph 编排
│   │   └── models/           # 数据模型（SQLAlchemy / Pydantic schema）
│   ├── services/             # 缓存 / 数据库 / LLM / RAG 等服务层
│   ├── data/                 # 文件存储（路径 / 练习记录 / 画像等）
│   ├── mcp_server.py         # MCP 服务
│   ├── Dockerfile
│   └── requirements.txt
├── frontend-vue/             # Vue 3 前端
│   ├── src/
│   │   ├── api/              # axios 封装（SSE / WebSocket 流式）
│   │   ├── stores/           # Pinia 状态
│   │   ├── views/            # 页面（画像 / 路径 / 辅导 / 练习 / 报告 / 技能差距…）
│   │   └── components/       # 组件（思维导图 / 路径向导 / 视频搜索等）
│   ├── nginx.conf            # Nginx 配置（静态资源 + API 反代 + WebSocket）
│   ├── Dockerfile
│   └── vite.config.js        # 开发端口 3002，代理 /api → :8000
└── .gitignore
```

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- 讯飞星火 API 密钥（必填）；GLM / 通义为可选

### 1. 启动后端（端口 8000）

```bash
cd backend

# 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env             # Windows: copy .env.example .env
# 编辑 .env，填入 XUNFEI_APP_ID / XUNFEI_API_KEY / XUNFEI_API_SECRET

# 启动服务
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

启动后：
- 健康检查：`http://localhost:8000/health`
- 接口文档（Swagger）：`http://localhost:8000/docs`

### 2. 启动前端（端口 3002）

```bash
cd frontend-vue
npm install
npm run dev
```

浏览器打开 **http://localhost:3002**。

> 开发时前端通过 Vite 代理将 `/api`、`/static` 转发到 `localhost:8000`，无需额外配置。

## 🔑 环境变量说明

复制 `backend/.env.example` 为 `backend/.env` 后填写：

| 变量 | 必填 | 说明 |
|---|---|---|
| `XUNFEI_APP_ID` | ✅ | 讯飞星火 AppID |
| `XUNFEI_API_KEY` | ✅ | 讯飞星火 API Key |
| `XUNFEI_API_SECRET` | ✅ | 讯飞星火 API Secret |
| `GLM_API_KEY` | 可选 | 智谱 GLM 密钥（OpenAI 兼容） |
| `DASHSCOPE_API_KEY` | 可选 | 通义千问密钥（OpenAI 兼容） |
| `KB_API_URL` | 可选 | 讯飞知识库接口，默认 `https://chatdoc.xfyun.cn/openapi/v1` |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | 可选 | MySQL 连接；不配置则自动降级为文件存储 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | 可选 | Redis 连接；不配置则自动降级为内存缓存 |

## 🐳 Docker 部署

两个独立镜像，构建上下文分别为对应目录：

```bash
# 后端
docker build -t a3-backend ./backend
docker run -p 8000:8000 --env-file ./backend/.env a3-backend

# 前端（Nginx 反代 API 到 backend:8000）
docker build -t a3-frontend ./frontend-vue
docker run -p 80:80 --add-host backend:host-gateway a3-frontend
```

> 前端 Nginx 通过 `backend:8000` 访问后端，容器内需确保 `backend` 主机名可解析（Docker Compose 网络或 `--add-host`）。

## 📄 许可证

本项目为个人学习项目，未指定开源许可证，保留所有权利。如需开源请与作者联系。
