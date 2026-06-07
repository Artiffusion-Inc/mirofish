# 架构设计

## 适配器模式

采用适配器模式（Adapter Pattern）统一 Zep Cloud 和 Graphiti 的 API 差异，使业务代码与具体后端解耦。

### 设计原则

1. **抽象接口**：`ZepClientAdapter` 定义统一的操作接口
2. **双实现**：`ZepCloudClient` 和 `GraphitiClient` 分别实现接口
3. **工厂模式**：`create_zep_client()` 根据配置创建对应实例
4. **延迟加载**：仅在需要时导入具体实现，减少启动依赖

### 类图

```
                    ┌─────────────────────┐
                    │  ZepClientAdapter   │
                    │     (Abstract)      │
                    ├─────────────────────┤
                    │ + create_graph()    │
                    │ + add_episode()     │
                    │ + search()          │
                    │ + get_all_nodes()   │
                    │ + get_all_edges()   │
                    │ + ...               │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                                 │
              ▼                                 ▼
┌─────────────────────┐           ┌─────────────────────┐
│   ZepCloudClient    │           │   GraphitiClient    │
├─────────────────────┤           ├─────────────────────┤
│ - client: Zep       │           │ - graphiti: Graphiti│
│ - api_key: str      │           │ - driver: Neo4jDriver│
├─────────────────────┤           ├─────────────────────┤
│ (包装 zep-cloud SDK)│           │ (包装 graphiti-core) │
└─────────────────────┘           └─────────────────────┘
```

## 文件清单

### 新建文件

| 文件路径 | 用途 |
|----------|------|
| `backend/app/services/zep_adapter.py` | 抽象接口和数据结构定义 |
| `backend/app/services/zep_cloud_impl.py` | Zep Cloud 实现 |
| `backend/app/services/zep_graphiti_impl.py` | Graphiti 本地实现 |
| `backend/app/services/graphiti_patch.py` | graphiti-core workaround（Issue #683） |
| `backend/app/services/zep_factory.py` | 工厂函数 |
| `docker-compose.local.yml` | Neo4j Docker 部署配置 |
| `backend/requirements-graphiti.txt` | graphiti 环境最小依赖（可选） |
| `docs/zep-localization/` | 本文档目录 |

### 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `backend/app/config.py` | 新增 `ZEP_BACKEND`, `NEO4J_*` 配置 |
| `backend/app/services/graph_builder.py` | 迁移到适配器接口 |
| `backend/app/services/zep_tools.py` | 迁移到适配器接口 |
| `backend/app/services/zep_entity_reader.py` | 迁移到适配器接口 |
| `backend/app/services/zep_graph_memory_updater.py` | 迁移到适配器接口 |
| `backend/app/services/oasis_profile_generator.py` | 迁移到适配器接口 |
| `backend/app/api/graph.py` | cloud/graphiti 模式兼容（cloud 才要求 `ZEP_API_KEY`） |
| `backend/app/api/simulation.py` | cloud/graphiti 模式兼容（cloud 才要求 `ZEP_API_KEY`） |
| `backend/pyproject.toml` | graphiti/oasis 设为 optional extras |

## 数据结构

### GraphNode

```python
@dataclass
class GraphNode:
    uuid: str              # 节点唯一标识
    name: str              # 节点名称
    labels: List[str]      # 节点标签列表
    summary: str           # 节点摘要描述
    attributes: Dict[str, Any]  # 扩展属性
```

### GraphEdge

```python
@dataclass
class GraphEdge:
    uuid: str              # 边唯一标识
    name: str              # 边名称/关系类型
    fact: str              # 关系描述
    source_node_uuid: str  # 源节点 UUID
    target_node_uuid: str  # 目标节点 UUID
    attributes: Dict[str, Any]  # 扩展属性
    created_at: Optional[str]   # 创建时间
    valid_at: Optional[str]     # 生效时间
```

### SearchResult

```python
@dataclass
class SearchResult:
    nodes: List[GraphNode]  # 匹配的节点
    edges: List[GraphEdge]  # 匹配的边
```

## API 映射表

| 适配器方法 | Zep Cloud API | Graphiti API |
|------------|---------------|--------------|
| `create_graph()` | `graph.create()` | 记录元数据（Graphiti 无显式 create；按 `group_id` 写入即生效） |
| `delete_graph()` | `graph.delete()` | Neo4j Cypher 删除 |
| `add_episode()` | `graph.add()` | `graphiti.add_episode()` |
| `add_episode_batch()` | `graph.add_batch()` | `graphiti.add_episode_bulk()` |
| `search()` | `graph.search()` | 优先 `graphiti.search_()`，fallback `graphiti.search()` |
| `get_all_nodes()` | `node.get_by_graph_id()` | Neo4j Cypher 查询 |
| `get_all_edges()` | `edge.get_by_graph_id()` | Neo4j Cypher 查询 |
| `get_node()` | `node.get()` | Neo4j Cypher 查询 |
| `get_node_edges()` | `node.get_entity_edges()` | Neo4j Cypher 查询 |
| `get_episode_status()` | `episode.get()` | 直接返回 processed=true（同步处理） |
| `wait_for_episode()` | `episode.get()` 轮询 | 直接返回（同步处理） |
| `set_ontology()` | `graph.set_ontology()` | 暂不支持 |

## 关键适配策略

### 1. 多图谱隔离

Zep Cloud 原生支持多 `graph_id`，Graphiti 默认单图谱。

**解决方案**：使用 `group_id` 参数实现数据隔离

```python
# Graphiti 添加 episode 时指定 group_id
await graphiti.add_episode(
    name=f"episode_{graph_id}",
    episode_body=data,
    group_id=graph_id,  # 用于隔离不同项目数据
    ...
)

# Neo4j 查询时过滤 group_id
MATCH (n:Entity) WHERE n.group_id = $graph_id RETURN n
```

### 2. 异步转同步

Graphiti 使用 async API，MiroFish 业务代码使用同步调用。

**解决方案**：`_run_async()` 辅助方法（使用持久事件循环，避免 Neo4j driver 绑定到被关闭的 loop）

```python
def _run_async(coro):
    """在同步上下文中运行异步协程（单后台线程 + run_coroutine_threadsafe）"""
    ...
```

### 3. Episode 等待机制

Zep Cloud 的 `episode.get()` 需要轮询等待处理完成，Graphiti 同步处理。

**解决方案**：Graphiti 实现直接返回成功

```python
# ZepCloudClient
def wait_for_episode(self, uuid: str, timeout: int) -> bool:
    # 轮询 episode.get() 直到状态为 done
    ...

# GraphitiClient
def wait_for_episode(self, uuid: str, timeout: int) -> bool:
    # Graphiti 同步处理，无需等待
    return True
```

### 4. 搜索结果转换

两个后端的搜索结果结构不同，需要转换为统一的 `SearchResult`。

```python
def _convert_edge(self, edge) -> GraphEdge:
    """将 Graphiti EdgeResult 转换为 GraphEdge"""
    return GraphEdge(
        uuid=edge.uuid,
        name=edge.name,
        fact=edge.fact,
        source_node_uuid=edge.source_node_uuid,
        target_node_uuid=edge.target_node_uuid,
        attributes={},
        created_at=str(edge.created_at) if edge.created_at else None,
        valid_at=str(edge.valid_at) if edge.valid_at else None
    )
```

## 配置说明

### config.py 新增配置

```python
# Zep 后端选择: 'cloud' 或 'graphiti'
ZEP_BACKEND = os.environ.get('ZEP_BACKEND', 'cloud')

# Neo4j 配置（graphiti 模式使用）
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'password')
```

### 工厂函数逻辑

```python
def create_zep_client() -> ZepClientAdapter:
    if ZEP_BACKEND == 'graphiti':
        from .zep_graphiti_impl import GraphitiClient
        return GraphitiClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    else:
        from .zep_cloud_impl import ZepCloudClient
        return ZepCloudClient(ZEP_API_KEY)
```

## 已知问题与 workaround

### graphiti-core Issue #683

某些 `graphiti-core` 版本在 `add_episode()` 写入 Neo4j 时会尝试保存嵌套 map，导致写入失败。
当前通过 `backend/app/services/graphiti_patch.py` 在写入前做 sanitize（嵌套 dict/list → JSON 字符串）绕过。
