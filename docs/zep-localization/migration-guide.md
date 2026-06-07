# 迁移指南

从 Zep Cloud 迁移到 Graphiti 本地部署的步骤说明。

## 前置条件

- Docker 和 Docker Compose 已安装
- Python 3.11+
- 已配置 LLM API（Graphiti 需要 LLM 进行实体抽取）

## 迁移步骤

### 1. 启动 Neo4j

```bash
# 进入项目根目录
cd /path/to/MiroFish

# 启动 Neo4j 容器
docker-compose -f docker-compose.local.yml up -d

# 检查容器状态
docker-compose -f docker-compose.local.yml ps
```

等待健康检查通过（约 30 秒），状态应显示 `healthy`。

### 2. 验证 Neo4j 连接

访问 Neo4j Browser：http://localhost:7474

- 用户名：`neo4j`
- 密码：`password`

### 3. 安装依赖

```bash
cd backend

# 使用 uv（推荐）
uv sync

# 安装 Graphiti 本地后端依赖（可选）
uv sync --extra graphiti

# 或使用 pip
pip install graphiti-core neo4j
```

> 注意：当前 `oasis`（`camel-oasis`）与 `graphiti` 可能存在 Python Neo4j driver 版本冲突，导致无法在同一 venv 同时安装。
> 如果你的目标是跑通“本地图谱链路”，建议先只启用 `--extra graphiti`；完整链路（含仿真）需要先解决依赖冲突（见 `docs/zep-localization-plan.md` 的「7.5」）。

### 4. 配置环境变量

创建或更新 `.env` 文件：

```env
# 切换到 Graphiti 后端
ZEP_BACKEND=graphiti

# Neo4j 连接配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# LLM 配置（Graphiti 必需）
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=your_chat_model

# Graphiti 模型（推荐显式设置）
GRAPHITI_LLM_MODEL=your_chat_model
GRAPHITI_EMBEDDING_MODEL=your_embedding_model
```

### 5. 启动应用

```bash
cd backend
uv run python run.py
```

> 也可以在项目根目录直接运行：`npm run backend`（仅启动后端）或 `npm run dev`（同时启动前后端）。

## Docker 部署说明

### docker-compose.local.yml 配置

```yaml
version: '3.8'

services:
  neo4j:
    image: neo4j:5.26
    container_name: mirofish-neo4j
    ports:
      - "7474:7474"  # HTTP (Browser)
      - "7687:7687"  # Bolt (Driver)
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_apoc_export_file_enabled: "true"
      NEO4J_apoc_import_file_enabled: "true"
      NEO4J_apoc_import_file_use__neo4j__config: "true"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:7474 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
```

### 常用命令

```bash
# 启动
docker-compose -f docker-compose.local.yml up -d

# 停止
docker-compose -f docker-compose.local.yml down

# 查看日志
docker-compose -f docker-compose.local.yml logs -f neo4j

# 重置数据（危险操作）
docker-compose -f docker-compose.local.yml down -v
```

## 数据迁移

### 从 Zep Cloud 导出数据

目前暂不支持自动数据迁移。如需迁移历史数据：

1. 使用 Zep Cloud API 导出节点和边数据
2. 转换为 Graphiti episode 格式
3. 使用 `add_episode()` 重新导入

### 数据格式参考

```python
# Zep Cloud 导出格式
nodes = zep_client.node.get_by_graph_id(graph_id)
edges = zep_client.edge.get_by_graph_id(graph_id)

# 转换为 episode 文本重新导入
for edge in edges:
    episode_text = f"{edge.source_node.name} {edge.name} {edge.target_node.name}"
    graphiti_client.add_episode(graph_id, episode_text)
```

## 切回 Zep Cloud

如需切回 Zep Cloud 后端：

```bash
# 修改环境变量
export ZEP_BACKEND=cloud
export ZEP_API_KEY=your_api_key

# 重启应用
cd backend && uv run python run.py
```

无需修改任何代码，应用会自动使用 Zep Cloud 后端。

## 常见问题

### 1. Neo4j 连接失败

**症状**：`ServiceUnavailable: Unable to retrieve routing information`

**解决方案**：
```bash
# 检查容器状态
docker-compose -f docker-compose.local.yml ps

# 如果状态不是 healthy，查看日志
docker-compose -f docker-compose.local.yml logs neo4j

# 重启容器
docker-compose -f docker-compose.local.yml restart neo4j
```

### 2. Graphiti 初始化慢

**症状**：首次启动时 `build_indices_and_constraints()` 耗时较长

**说明**：这是正常现象，Graphiti 需要在 Neo4j 中创建索引和约束。后续启动会快很多。

### 3. LLM API 报错

**症状**：`OpenAI API error` 或类似错误

**解决方案**：
1. 检查 `LLM_API_KEY` 是否正确
2. 检查 `LLM_BASE_URL` 是否可访问
3. 确认 API 余额充足

### 4. 搜索结果为空

**症状**：`search()` 返回空结果

**可能原因**：
1. `graph_id`（`group_id`）不匹配
2. Episode 尚未处理完成
3. 查询词与数据不匹配

**调试方法**：
```python
# 直接查询 Neo4j 检查数据
MATCH (n:Entity) WHERE n.group_id = "your_graph_id" RETURN n LIMIT 10
```

### 5. 内存占用高

**症状**：Neo4j 容器内存占用大

**解决方案**：在 docker-compose.local.yml 中限制内存

```yaml
services:
  neo4j:
    # ... 其他配置 ...
    deploy:
      resources:
        limits:
          memory: 2G
    environment:
      NEO4J_dbms_memory_heap_initial__size: 512m
      NEO4J_dbms_memory_heap_max__size: 1G
```

## 功能差异说明

| 功能 | Zep Cloud | Graphiti 本地 |
|------|-----------|---------------|
| Ontology 定义 | 支持 | 暂不支持 |
| 多图谱隔离 | 原生支持 | 通过 group_id 实现 |
| 实体抽取 | 内置 | 需要配置 LLM |
| 搜索重排序 | 支持多种 reranker | 使用默认方式 |
| Episode 异步处理 | 需轮询等待 | 同步处理 |

## 性能优化建议

1. **Neo4j 内存配置**：生产环境建议至少 4GB 堆内存
2. **索引优化**：确保 `group_id` 字段有索引
3. **批量操作**：使用 `add_episode_batch()` 批量添加数据
4. **连接池**：GraphitiClient 内部已管理连接池，避免频繁创建实例
