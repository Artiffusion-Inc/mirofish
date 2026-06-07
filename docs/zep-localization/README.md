# Zep 本地化实施

将 MiroFish 的知识图谱后端从 Zep Cloud 迁移到本地 Graphiti + Neo4j 方案。

## 背景

MiroFish 原依赖 Zep Cloud 作为知识图谱服务，为支持本地部署需求，实现了双后端架构：

- **Zep Cloud**：原有云服务，适合快速开发
- **Graphiti + Neo4j**：本地部署方案，完全开源

## 架构概览

```
┌─────────────────────────────────────┐
│        MiroFish 业务代码            │
│   (graph_builder, zep_tools, ...)   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│      ZepClientAdapter (适配层)       │
│         统一 API 接口               │
└──────────────┬──────────────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌───────────┐    ┌─────────────────┐
│ Zep Cloud │    │ Graphiti Local  │
│ (云服务)   │    │ Neo4j + LLM     │
└───────────┘    └─────────────────┘
```

## 快速开始

### 使用 Graphiti 本地后端

```bash
# 1. 启动 Neo4j
docker-compose -f docker-compose.local.yml up -d

# 2. 等待服务就绪
docker-compose -f docker-compose.local.yml ps

# 3. 安装后端依赖（graphiti 模式需要）
cd backend
uv sync --extra graphiti

# 4. 设置环境变量（至少需要 LLM_*；OPENAI_* 会自动从 LLM_* 映射）
export ZEP_BACKEND=graphiti
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
export LLM_API_KEY=your_api_key
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL_NAME=your_chat_model
export GRAPHITI_LLM_MODEL=your_chat_model
export GRAPHITI_EMBEDDING_MODEL=your_embedding_model

# 5. 启动后端
uv run python run.py
```

### 使用 Zep Cloud 后端

```bash
# 1. 安装后端依赖（cloud 模式不需要 graphiti extra）
cd backend
uv sync

# 2. 设置环境变量（仍需要 LLM_* 用于 ontology/report 等能力）
export ZEP_BACKEND=cloud  # 或不设置，默认 cloud
export ZEP_API_KEY=your_api_key
export LLM_API_KEY=your_api_key
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL_NAME=your_chat_model

# 3. 启动后端
uv run python run.py
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API Key（后端必填） | - |
| `LLM_BASE_URL` | OpenAI-compatible Base URL | `https://api.openai.com/v1` |
| `LLM_MODEL_NAME` | 默认聊天模型 | `gpt-4o-mini` |
| `ZEP_BACKEND` | 后端选择：`cloud` 或 `graphiti` | `cloud` |
| `ZEP_API_KEY` | Zep Cloud API 密钥（cloud 模式必填） | - |
| `NEO4J_URI` | Neo4j 连接地址 | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j 用户名 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 密码 | `password` |
| `OPENAI_API_KEY` | Graphiti 用的 OpenAI-compatible Key（未设置时自动继承 `LLM_API_KEY`） | - |
| `OPENAI_BASE_URL` | Graphiti 用的 OpenAI-compatible Base URL（未设置时自动继承 `LLM_BASE_URL`） | - |
| `GRAPHITI_LLM_MODEL` | Graphiti 使用的 LLM 模型名（推荐显式设置） | 继承 `LLM_MODEL_NAME` |
| `GRAPHITI_EMBEDDING_MODEL` | Graphiti 使用的 embedding 模型名（DashScope 推荐 `text-embedding-v4`） | Graphiti 默认值 |

## 已知限制

### 1) graphiti-core Issue #683（已通过 workaround 绕过）

在部分 `graphiti-core` 版本中，`add_episode()` 写入 Neo4j 时会尝试保存嵌套 map（Neo4j property 不支持），导致写入失败。
当前在 MiroFish 内部通过 `backend/app/services/graphiti_patch.py` 做了 sanitize（嵌套 dict/list → JSON 字符串）来避免阻塞。

### 2) 依赖冲突（Full parity 的阻塞点）

`camel-oasis` 与 `graphiti-core` 对 Python Neo4j driver 的版本约束可能冲突，导致同一 venv 难以同时安装两者。
如需完整链路（仿真 + 本地图谱）同时启用，建议参考 `docs/zep-localization-plan.md` 的「7.5」采用升级依赖或拆分运行时的方案。

## 文档目录

- [架构设计](./architecture.md) - 适配器模式设计、文件清单、API 映射
- [迁移指南](./migration-guide.md) - 从 Zep Cloud 迁移到 Graphiti 的步骤

## 技术亮点

1. **适配器模式**：业务代码无感知切换后端
2. **配置驱动**：通过环境变量选择后端，无需改代码
3. **Docker 一键部署**：Neo4j 容器化，开箱即用
4. **向后兼容**：保留 Zep Cloud 支持，可随时切回
