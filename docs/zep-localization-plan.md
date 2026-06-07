# MiroFish Zep 服务本地化方案

> 本文档记录将 MiroFish 项目的 Zep Cloud 依赖改为本地部署的技术方案。

## TL;DR（先 MVP，再完整）

- **MVP 目标**：不依赖 Zep Cloud，也能跑通「建图 → 读实体 → 搜索 → 报告/可视化」的核心链路（允许语义/字段存在差异）。
- **Full parity 目标**：尽量对齐现有 `zep-cloud` 图谱能力与语义（ontology、temporal fields、搜索质量/结构等）。
- **推荐落地方式**：适配器模式 + 双后端（`zep-cloud` 现有云端 + `graphiti` 本地 Neo4j）。

## 1. 背景

### 1.1 当前状态

MiroFish 项目使用 **Zep Cloud** 作为核心知识图谱服务：

```
依赖包：zep-cloud==3.13.0
配置项：ZEP_API_KEY（必需）
```

**涉及文件**（5 个）：
- `backend/app/services/graph_builder.py` - 图谱构建
- `backend/app/services/zep_tools.py` - 搜索工具（1660行）
- `backend/app/services/zep_entity_reader.py` - 实体读取
- `backend/app/services/zep_graph_memory_updater.py` - 记忆更新
- `backend/app/services/oasis_profile_generator.py` - 人设生成

### 1.2 本地化需求

面试官建议"把服务改为本地"，目标是消除对 Zep Cloud API 的依赖，实现完全自托管。

---

## 2. 技术调研

### 2.1 关键发现

| 调研项 | 结论 |
|--------|------|
| Zep 自托管（Community Edition） | **已废弃/不再维护**（官方将其归档为 legacy，但代码仍在仓库 `legacy/` 目录） |
| zep-python SDK | **能连 legacy CE，但无法“直接替换”本项目**：MiroFish 当前依赖的是 `zep-cloud` 的 Graph API（`client.graph.*`），与 legacy CE / `zep-python` 的能力与模型不保证一致 |
| Graphiti | **推荐的 OSS 方向**：Zep 团队开源的时序知识图谱框架，可作为本地化替代的基础，但 **API 不兼容，需要适配层** |

> **Graphiti** 是 Zep 团队开源的图谱内核/框架（Zep 自身也由 Graphiti 驱动）。
> 它提供相近的“图谱构建 + 检索”能力，但 **不是 Zep Cloud 的同款服务**，因此需要适配层。
> - GitHub: https://github.com/getzep/graphiti
> - PyPI: https://pypi.org/project/graphiti-core/

### 2.2 关键结论（对面试官表述）

- “把服务改为本地”在 MiroFish 语境里，最直接就是：**不再依赖 Zep Cloud**，改为 **本地可运行的图谱存储/检索服务**。
- Zep CE 虽然存在，但官方已弃用；更稳的方向是：**Graphiti + 本地图数据库（Neo4j/Kuzu/FalkorDB 等）**。
- Graphiti 是“框架”而不是 Zep Cloud 的同款服务：因此必须通过 **适配器** 做渐进式迁移，先做 MVP 再做语义对齐。

### 2.3 MiroFish 使用的 Zep API 清单（当前 `zep-cloud`）

| API | 用途 | 调用位置 |
|-----|------|----------|
| `client.graph.create()` | 创建知识图谱 | graph_builder.py |
| `client.graph.set_ontology()` | 设置本体（实体/边类型） | graph_builder.py |
| `client.graph.add()` | 添加单条 episode | zep_graph_memory_updater.py |
| `client.graph.add_batch()` | 批量添加 episode | graph_builder.py |
| `client.graph.search()` | 混合搜索（语义+BM25） | zep_tools.py, oasis_profile_generator.py |
| `client.graph.node.get_by_graph_id()` | 获取图谱所有节点 | graph_builder.py, zep_tools.py, zep_entity_reader.py |
| `client.graph.node.get()` | 获取单个节点 | zep_tools.py, zep_entity_reader.py |
| `client.graph.node.get_entity_edges()` | 获取节点关联边 | zep_entity_reader.py |
| `client.graph.edge.get_by_graph_id()` | 获取图谱所有边 | graph_builder.py, zep_tools.py, zep_entity_reader.py |
| `client.graph.episode.get()` | 获取 episode 状态 | graph_builder.py |
| `client.graph.delete()` | 删除图谱 | graph_builder.py |

### 2.4 zep-cloud vs Graphiti API 映射（高层）

| zep-cloud API | Graphiti 对应 | 兼容性 | 适配策略 |
|---------------|---------------|--------|----------|
| `graph.create()` | 自动创建 | 不同 | 初始化时自动处理 |
| `graph.set_ontology()` | （无 1:1 等价） | 需改写 | MVP 先降级；Full parity 再做约束/提示注入/类型映射 |
| `graph.add()` / `add_batch()` | `add_episode()` / `add_episode_bulk()` | 类似 | 参数映射 |
| `graph.search()` | `search()` / `retrieve_nodes()` | 类似 | scope 参数映射 |
| `graph.node.get_by_graph_id()` | `retrieve_nodes()` + Neo4j | 需适配 | Cypher 查询 |
| `graph.edge.get_by_graph_id()` | `search()` 返回 edges | 需适配 | 结果转换 |
| `graph.episode.get()` | 同步处理，无需轮询 | 更简单 | 直接返回 |

---

## 3. 推荐方案：适配器模式

### 3.1 架构设计

```
┌─────────────────────────────────────┐
│        MiroFish 现有代码            │
│   (graph_builder, zep_tools, ...)   │
└──────────────┬──────────────────────┘
               │ 调用
               ▼
┌─────────────────────────────────────┐
│      ZepClientAdapter (新建)        │
│   统一接口，兼容 cloud/graphiti     │
└──────────────┬──────────────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌───────────┐    ┌─────────────────┐
│ Zep Cloud │    │ Graphiti Local  │
│ (原实现)   │    │ Neo4j + LLM     │
└───────────┘    └─────────────────┘
```

### 3.2 核心思路

1. **抽象层**：定义 `ZepClientAdapter` 统一接口
2. **双实现**：`ZepCloudClient` + `GraphitiClient`
3. **配置驱动**：通过 `ZEP_BACKEND` 环境变量切换后端
4. **零侵入**：现有代码最小改动

---

## 4. 实现计划（MVP → Full parity）

### 4.0 MVP 范围定义

**MVP 要覆盖的能力（足够跑通主链路）**

- 建图：把文本 chunk/episode 写入本地图（Graphiti ingestion）
- 读图：按 `graph_id` 拉取 nodes/edges（供前端可视化、供 simulation 准备阶段读取）
- 搜索：支持 ReportAgent / 人设生成使用的基础检索（至少 keyword/semantic 之一）
- 单点查询：get node、get node edges（供实体详情/过滤逻辑）
- 删除图：清理本地图数据（开发期可接受粗粒度）

**MVP 明确不做/允许降级的点（避免被 ontology 吃掉工期）**

- `set_ontology()` 的严格语义对齐（Graphiti 无 1:1 对应）
- Zep Cloud 搜索结果字段/结构 100% 对齐（先保证“能用”，再保证“等价”）
- `valid_at/invalid_at/expired_at` 等时序字段的完整对齐
- `zep_graph_memory_updater.py` 的图谱记忆增量更新（可先 no-op 或仅记录文本 episode）

**MVP 的验收标准（建议在面试前跑一次录屏）**

- `ZEP_BACKEND=graphiti` 时：前端能完成 Step1（ontology + build）并在 GraphPanel 看到 nodes/edges 数据
- Step2 能成功读取实体并生成 profiles/config（即便类型/过滤比 Zep Cloud 粗糙）
- Step4 ReportAgent 能跑通一次生成（检索能返回内容，报告产出不为空）

### 4.1 Phase 1：适配层设计（MVP，0.5-1天）

**新建**：`backend/app/services/zep_adapter.py`

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class GraphNode:
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]

@dataclass
class GraphEdge:
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    attributes: Dict[str, Any]
    created_at: Optional[str] = None
    valid_at: Optional[str] = None

@dataclass
class SearchResult:
    nodes: List[GraphNode]
    edges: List[GraphEdge]

class ZepClientAdapter(ABC):
    """统一的 Zep 客户端接口"""

    @abstractmethod
    def create_graph(self, graph_id: str, name: str, description: str) -> None: ...

    @abstractmethod
    def set_ontology(self, graph_ids: List[str], entities: Dict, edges: Dict) -> None: ...

    @abstractmethod
    def add_episode(self, graph_id: str, data: str) -> str: ...

    @abstractmethod
    def add_episode_batch(self, graph_id: str, episodes: List[Dict]) -> List[str]: ...

    @abstractmethod
    def search(self, graph_id: str, query: str, scope: str, limit: int, reranker: str) -> SearchResult: ...

    @abstractmethod
    def get_all_nodes(self, graph_id: str) -> List[GraphNode]: ...

    @abstractmethod
    def get_all_edges(self, graph_id: str) -> List[GraphEdge]: ...

    @abstractmethod
    def get_node(self, uuid: str) -> GraphNode: ...

    @abstractmethod
    def get_node_edges(self, node_uuid: str) -> List[GraphEdge]: ...

    @abstractmethod
    def delete_graph(self, graph_id: str) -> None: ...

    @abstractmethod
    def wait_for_episode(self, uuid: str, timeout: int) -> bool: ...
```

> 说明：接口可以在 MVP 阶段先保持“尽量贴近 zep-cloud 现状”，但实现上允许 Graphiti backend 对部分方法 no-op（例如 `set_ontology()`）。

### 4.2 Phase 2：Cloud 实现（MVP，0.5天）

**新建**：`backend/app/services/zep_cloud_impl.py`

包装现有 zep-cloud API，实现 `ZepClientAdapter` 接口。

### 4.3 Phase 3：Graphiti 实现（MVP，2-4天）

**新建**：`backend/app/services/zep_graphiti_impl.py`

```python
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

class GraphitiClient(ZepClientAdapter):
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        self.graphiti = Graphiti(neo4j_uri, neo4j_user, neo4j_password)
        _run_async(self.graphiti.build_indices_and_constraints())

    def add_episode(self, graph_id: str, data: str) -> str:
        result = _run_async(self.graphiti.add_episode(
            name=f"episode_{graph_id}",
            episode_body=data,
            source=EpisodeType.text,
            source_description="mirofish_simulation",
            group_id=graph_id,  # MiroFish graph_id -> Graphiti group_id
        ))
        return result.episode.uuid if result and result.episode else ""

    # ... 其他方法实现
```

**关键适配点**：

| 挑战 | 解决方案 |
|------|----------|
| 多图谱隔离 | **MVP 必做**：用 `group_id` 隔离数据（MiroFish `graph_id` 直接映射为 Graphiti `group_id`） |
| 读全量 nodes/edges | **MVP 必做**：允许直接 Cypher 查询 Neo4j，把结果转换成 `GraphNode/GraphEdge` |
| 搜索结果结构 | **MVP 必做**：把 Graphiti 的返回映射成现有 `SearchResult`，先保证 ReportAgent 可用 |
| Ontology 映射 | **MVP 先降级**：`set_ontology()` 可 no-op 或仅用于 prompt 提示；Full parity 再做强约束 |
| 异步/同步适配 | `_run_async()` 复用持久事件循环（避免 `asyncio.run()` 的跨 loop 问题） |

### 4.4 Phase 4：工厂模式 + 配置（MVP，0.5天）

**新建**：`backend/app/services/zep_factory.py`

```python
from app.config import ZEP_BACKEND, ZEP_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

def create_zep_client() -> ZepClientAdapter:
    if ZEP_BACKEND == 'graphiti':
        from .zep_graphiti_impl import GraphitiClient
        return GraphitiClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    else:
        from .zep_cloud_impl import ZepCloudClient
        return ZepCloudClient(ZEP_API_KEY)
```

**修改**：`backend/app/config.py`

```python
# 新增配置
ZEP_BACKEND = os.environ.get('ZEP_BACKEND', 'cloud')  # 'cloud' | 'graphiti'
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'password')
```

### 4.5 Phase 5：迁移现有代码（MVP，1-2天）

**替换模式**：

```python
# Before
from zep_cloud.client import Zep
self.client = Zep(api_key=self.api_key)
result = self.client.graph.search(...)

# After
from .zep_factory import create_zep_client
self.client = create_zep_client()
result = self.client.search(...)
```

**修改文件列表**：

| 文件 | 修改量 |
|------|--------|
| `graph_builder.py` | 中 |
| `zep_tools.py` | 大 |
| `zep_entity_reader.py` | 中 |
| `zep_graph_memory_updater.py` | 小 |
| `oasis_profile_generator.py` | 小 |

### 4.6 Phase 6：Docker 部署（MVP，0.5天）

**新建**：`docker-compose.local.yml`

```yaml
version: '3.8'
services:
  neo4j:
    image: neo4j:5.26
    ports:
      - "7474:7474"  # HTTP (Browser)
      - "7687:7687"  # Bolt
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
```

**更新**：`.env.example`

```env
# Zep 后端选择: 'cloud' 或 'graphiti'
ZEP_BACKEND=graphiti

# Graphiti 本地部署配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# LLM 配置（MiroFish 统一使用）
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=qwen3-max

# Graphiti 默认读取 OPENAI_*；后端启动时会在未显式设置时自动从 LLM_* 映射
# （也可以显式设置 OPENAI_* 覆盖）
# OPENAI_API_KEY=your_api_key
# OPENAI_BASE_URL=https://api.openai.com/v1

# Graphiti 模型/embeddings（建议显式配置，避免默认 OpenAI 模型名不兼容）
GRAPHITI_LLM_MODEL=qwen3-max
GRAPHITI_EMBEDDING_MODEL=text-embedding-v4
```

---

## 5. 文件清单（MVP）

### 5.1 新建文件

| 文件路径 | 用途 |
|----------|------|
| `backend/app/services/zep_adapter.py` | 抽象接口定义 |
| `backend/app/services/zep_cloud_impl.py` | Zep Cloud 实现 |
| `backend/app/services/zep_graphiti_impl.py` | Graphiti 本地实现 |
| `backend/app/services/graphiti_patch.py` | graphiti-core workaround（Issue #683） |
| `backend/app/services/zep_factory.py` | 工厂函数 |
| `docker-compose.local.yml` | Neo4j 本地部署 |
| `backend/requirements-graphiti.txt` | Graphiti 环境依赖（避免 oasis 冲突） |

### 5.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `backend/app/api/graph.py` | cloud/graphiti 模式兼容（不强依赖 ZEP_API_KEY） |
| `backend/app/api/simulation.py` | cloud/graphiti 模式兼容（不强依赖 ZEP_API_KEY） |
| `backend/app/services/graph_builder.py` | 替换 Zep client |
| `backend/app/services/zep_tools.py` | 替换 Zep client |
| `backend/app/services/zep_entity_reader.py` | 替换 Zep client |
| `backend/app/services/zep_graph_memory_updater.py` | 替换 Zep client |
| `backend/app/services/oasis_profile_generator.py` | 替换 Zep client |
| `backend/app/config.py` | 新增配置项 |
| `.env.example` | 新增配置示例 |
| `backend/pyproject.toml` | graphiti/oasis 设为 optional extras |

---

## 6. 工作量估计（MVP vs Full parity）

### 6.1 MVP（跑通核心链路）

| 阶段 | 时间 | 说明 |
|------|------|------|
| Phase 1: 适配层设计 | 0.5-1天 | 接口定义 + 数据结构 |
| Phase 2: Cloud 实现 | 0.5天 | 包装现有 API |
| Phase 3: Graphiti 实现 | 2-4天 | **核心工作（隔离+读图+搜索映射）** |
| Phase 4: 工厂 + 配置 | 0.5天 | 配置驱动 |
| Phase 5: 代码迁移 | 1-2天 | 替换调用 |
| Phase 6: Docker 部署 | 0.5天 | Neo4j 本地部署 |
| 验收/录屏 | 0.5-1天 | 按验收标准跑通 |
| **总计** | **5-9天** | 取决于 Graphiti/Neo4j 隔离与查询难度 |

### 6.2 Full parity（尽量语义对齐）

这部分建议拆成可独立 PR 的里程碑：

- 依赖/运行时解耦：解决 `camel-oasis` 与 `graphiti-core` 的 `neo4j` Python driver 版本冲突（见「7.5」）
- 移除临时 patch：替换/升级到包含修复的 `graphiti-core`，或收敛到可维护的 fork（见「7.6」）
- Ontology 对齐：把 MiroFish 的 entity_types/edge_types 约束传入 Graphiti（或做后置类型映射）
- Temporal 字段对齐：补齐 `valid_at/invalid_at/expired_at` 等
- 搜索质量对齐：混合检索、reranker、分页/过滤等能力补齐
- Graph memory updater：把模拟过程中产生的事件增量写回图谱并可检索

预计工期：**1-2 周+**（取决于 Graphiti 的可扩展点与我们对“等价”的定义）

---

## 7. 风险与挑战

### 7.1 Ontology 映射（Full parity 高风险；MVP 建议降级）

**问题**：zep-cloud 的 `set_ontology()` 使用动态类型定义，Graphiti 用 Pydantic models。

**解决方案**：

```python
from pydantic import BaseModel

def create_entity_model(name: str, attributes: Dict[str, type]):
    return type(name, (BaseModel,), {
        '__annotations__': attributes
    })

# 使用示例
PersonEntity = create_entity_model('Person', {'name': str, 'age': int})
```

> 注：此处仅代表一种思路。更现实的方案是：用 Graphiti 的 `group_id` 做多图谱隔离（MiroFish 的 `graph_id` 直接映射为 `group_id`）；如果做不到，可能需要用“每个 graph 一个数据库/一个 namespace”来隔离。

### 7.2 多图谱隔离（MVP 中高风险）

**问题**：MiroFish 为每个项目创建独立 `graph_id`，Graphiti 用 `group_id` 做 partition。

**解决方案**：优先采用 `group_id` 隔离：把 MiroFish 的 `graph_id` 直接映射为 Graphiti 的 `group_id`，写入/查询都按 `group_id` 过滤；必要时再用 label/数据库隔离。

```cypher
-- 创建带 group_id 的节点
CREATE (n:Entity {group_id: $group_id, name: $name})

-- 查询特定图谱的节点
MATCH (n:Entity {group_id: $group_id}) RETURN n
```

### 7.3 异步/同步适配（低风险）

**问题**：Graphiti 是 async API，MiroFish 用同步调用。

**解决方案**：

- 不使用 `asyncio.run()`（它会创建/关闭新 loop，容易触发 Neo4j driver “跨 loop 绑定”问题）
- 在适配器层提供 `_run_async()`：统一把异步调用丢到专用后台线程/事件循环里执行（避免 running loop/跨 loop 绑定问题）
- 参考实现：`backend/app/services/zep_graphiti_impl.py` 的 `_run_async()`（已处理上述场景）

### 7.4 LLM 配置对齐（MVP 中风险）

**问题**：Graphiti 默认会按 OpenAI 的方式读取配置（例如 `OPENAI_API_KEY`），而 MiroFish 目前使用 `LLM_API_KEY/LLM_BASE_URL` 这套自定义命名。

**解决方案**（MVP 建议先走最简单的）：

- 后端启动时自动做 `LLM_* → OPENAI_*` 映射（仅在未显式设置 `OPENAI_*` 时），见 `backend/app/config.py`
- Graphiti 侧模型名/embedding model 建议显式配置：
  - `GRAPHITI_LLM_MODEL`（默认回退到 `LLM_MODEL_NAME`）
  - `GRAPHITI_EMBEDDING_MODEL`
- DashScope embeddings 的 batch size 上限需要处理（见「7.7」）

#### LLM endpoint 选型（DashScope / OpenAI 都可）

MiroFish 后端目前使用的是 `openai` SDK（OpenAI-compatible）。所以不管你用 OpenAI 还是 DashScope，**都需要提供一个 OpenAI-compatible 的 `base_url` + `api_key`**。

你给的示例是 DashScope Python SDK 的“原生”调用：

- `dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"`（原生 DashScope API）
- `model="qwen3-max"`（聊天模型）

但对 MiroFish / Graphiti 来说，应当走 DashScope 的 **compatible-mode**：

```env
# ✅ DashScope（百炼）OpenAI-compatible
LLM_API_KEY=your_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen3-max

# Graphiti 默认读取 OPENAI_*（后端启动会自动从 LLM_* 映射；也可显式设置覆盖）
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

如果你更想用 OpenAI，也同理：

```env
# ✅ OpenAI（OpenAI-compatible）
LLM_API_KEY=your_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=your_chat_model

# Graphiti 默认读取 OPENAI_*（后端启动会自动从 LLM_* 映射；也可显式设置覆盖）
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.openai.com/v1
```

#### Embeddings（你提供的 DashScope embedding 信息）

你给的 embedding 示例：

- API：`dashscope.TextEmbedding.call(...)`
- Model：`text-embedding-v4`

这里有两种落地方式（MVP 推荐先走 A，跑不通再走 B）：

- **A：OpenAI-compatible embeddings**（如果 DashScope compatible-mode 支持 `/embeddings`）
  - 直接让 `openai` SDK 走 `https://dashscope.aliyuncs.com/compatible-mode/v1`
  - embedding model 用 `text-embedding-v4`
- **B：DashScope 原生 embeddings**（如果 compatible-mode 不支持 embeddings）
  - 在 Graphiti backend 里单独接入 DashScope embedding（用 `dashscope.TextEmbedding`）
  - 需要额外配置 `DASHSCOPE_API_KEY`（不要写入仓库，只放本地 `.env`）

### 7.5 依赖冲突（Full parity 阻塞点）

当前项目同时需要：

- `camel-oasis`（仿真引擎）
- `graphiti-core`（本地图谱）

但两者对 **Python Neo4j driver** 的版本要求存在冲突（已在本地验证）。这会导致 “一套 venv 同时安装两者” 难以成立，从而影响 full parity（完整链路同时启用仿真 + 本地图谱）。

当前已知约束（以项目实际依赖为准）：

- `camel-oasis==0.2.5` 依赖 `neo4j==5.23.0`
- `graphiti-core>=0.25.0,<0.26.0` 依赖 `neo4j>=5.26.0`

建议的解决路径（按优先级）：

1. **升级/替换 oasis 依赖**：如果上游 `camel-oasis` 可以升级到兼容更新版 `neo4j` driver（或放宽版本约束），这是最干净的方案。
2. **拆分运行时**：把 Graphiti 相关逻辑拆成独立进程/服务（单独 venv / 单独容器），与主后端通过 HTTP/RPC 交互，避免 Python 依赖冲突。
3. **选择兼容版本的 graphiti-core**：退回到与 `neo4j==5.23.x` 兼容的 `graphiti-core` 版本，但需要评估功能/bugfix（包括 Issue #683）覆盖情况。

### 7.6 graphiti-core Issue #683（MVP 已绕过；Full parity 需移除）

已确认 `graphiti-core` 存在回归：写入 Neo4j 时尝试保存嵌套 map（Neo4j property 不支持），导致 `add_episode()` 失败，阻塞端到端。

当前 MVP 采用 workaround：在 `backend/app/services/graphiti_patch.py` 对 graphiti-core 的写库路径做 monkey-patch，写入前将嵌套 dict/list 转为 JSON 字符串（sanitize）。

Full parity 需要把这个 workaround 收敛为可维护方案：

- 优先：升级到包含官方修复的 `graphiti-core` 版本并删除 patch
- 次选：短期维持 patch，但加上版本/签名校验与开关（避免 silently broken）
- 兜底：维护一个小型 fork（锁定版本 + 自己 backport 修复），确保可复现构建

### 7.7 DashScope embeddings 批量限制（P0：DashScope 下必须处理）

在 DashScope 的 OpenAI-compatible `/embeddings` 接口下，单次请求的 `input` 批量大小存在上限（目前观测为 **<= 10**）。Graphiti 在写入时会对节点/边做 embedding（例如对多条 edge facts 一次性调用 `create_batch()`），当待 embedding 数量超过 10 时会触发：

```
Error code: 400 - batch size is invalid, it should not be larger than 10
```

影响：

- 图谱构建可能出现“部分数据已写入，但 embedding 阶段失败导致整体 task failed”的状态（需要清理 `group_id` 后重建以避免脏数据）。

推荐修复（workaround，MVP 可用）：

- 在 Graphiti adapter 注入一个 “batch-limited embedder”：对 `create_batch(input_data_list)` 做分块（每块 <= 10），逐块调用底层 OpenAI-compatible embeddings API，再拼接结果返回。
- 方案落点：
  - 推荐：在 `backend/app/services/zep_graphiti_impl.py` 的 `_build_default_embedder()` 外包一层 wrapper
  - 备选：像 Issue #683 一样做 monkey-patch（patch `graphiti_core.embedder.openai.OpenAIEmbedder.create_batch`）

Full parity 建议：

- 把批量上限收敛成可配置项（例如 `GRAPHITI_EMBEDDING_BATCH_SIZE`），并在文档/启动脚本中明确写出默认值与适用范围。

---

## 8. 快速启动

### 8.1 本地部署

```bash
# 1. 启动 Neo4j
docker-compose -f docker-compose.local.yml up -d

# 2. 等待 Neo4j 就绪
sleep 30

# 3. 配置环境变量
export ZEP_BACKEND=graphiti
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
# 只需要配置 LLM_*，后端会自动映射到 OPENAI_*
export LLM_API_KEY=your_key
export LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export LLM_MODEL_NAME=qwen3-max
export GRAPHITI_LLM_MODEL=qwen3-max
export GRAPHITI_EMBEDDING_MODEL=text-embedding-v4

# 4. 安装依赖
# 注意：graphiti 与 oasis 目前存在 neo4j driver 冲突，建议分 venv/容器
(cd backend && uv sync --extra graphiti)

# 5. 启动服务
npm run dev
```

### 8.2 验证

```bash
# 访问 Neo4j Browser
open http://localhost:7474

# 测试 MiroFish
open http://localhost:3000
```

---

## 9. 设计亮点

1. **适配器模式**：支持 cloud/local 无缝切换，体现工程化能力
2. **零侵入迁移**：现有代码最小改动，向后兼容
3. **配置驱动**：通过环境变量切换后端，无需改代码
4. **Docker 一键部署**：降低使用门槛
5. **端到端验收清单**：可复现跑通并录屏留档

---

## 10. 参考资料

- [Graphiti GitHub](https://github.com/getzep/graphiti)
- [Graphiti 文档](https://help.getzep.com/graphiti)
- [graphiti-core PyPI](https://pypi.org/project/graphiti-core/)
- [Zep Cloud API 文档](https://help.getzep.com/)
- [Neo4j Docker Hub](https://hub.docker.com/_/neo4j)
