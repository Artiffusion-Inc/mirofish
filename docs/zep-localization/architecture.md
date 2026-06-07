# Architecture Design

## Adapter Pattern

The Adapter Pattern is used to unify the API differences between Zep Cloud and Graphiti, decoupling business code from the specific backend.

### Design Principles

1. **Abstract interface**: `ZepClientAdapter` defines the unified operation interface
2. **Dual implementation**: `ZepCloudClient` and `GraphitiClient` implement the interface respectively
3. **Factory pattern**: `create_zep_client()` creates the corresponding instance based on configuration
4. **Lazy loading**: Import concrete implementation only when needed, reducing startup dependencies

### Class Diagram

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
│ (wraps zep-cloud SDK)│           │ (wraps graphiti-core) │
└─────────────────────┘           └─────────────────────┘
```

## File List

### New Files

| File Path | Purpose |
|-----------|---------|
| `backend/app/services/zep_adapter.py` | Abstract interface and data structure definitions |
| `backend/app/services/zep_cloud_impl.py` | Zep Cloud implementation |
| `backend/app/services/zep_graphiti_impl.py` | Graphiti local implementation |
| `backend/app/services/graphiti_patch.py` | graphiti-core workaround (Issue #683) |
| `backend/app/services/zep_factory.py` | Factory function |
| `docker-compose.local.yml` | Neo4j Docker deployment configuration |
| `backend/requirements-graphiti.txt` | graphiti environment minimal dependencies (optional) |
| `docs/zep-localization/` | This documentation directory |

### Modified Files

| File Path | Changes |
|-----------|---------|
| `backend/app/config.py` | Added `ZEP_BACKEND`, `NEO4J_*` configuration |
| `backend/app/services/graph_builder.py` | Migrated to adapter interface |
| `backend/app/services/zep_tools.py` | Migrated to adapter interface |
| `backend/app/services/zep_entity_reader.py` | Migrated to adapter interface |
| `backend/app/services/zep_graph_memory_updater.py` | Migrated to adapter interface |
| `backend/app/services/oasis_profile_generator.py` | Migrated to adapter interface |
| `backend/app/api/graph.py` | cloud/graphiti mode compatibility (cloud requires `ZEP_API_KEY`) |
| `backend/app/api/simulation.py` | cloud/graphiti mode compatibility (cloud requires `ZEP_API_KEY`) |
| `backend/pyproject.toml` | graphiti/oasis set as optional extras |

## Data Structures

### GraphNode

```python
@dataclass
class GraphNode:
    uuid: str              # Unique node identifier
    name: str              # Node name
    labels: List[str]      # Node label list
    summary: str           # Node summary description
    attributes: Dict[str, Any]  # Extended attributes
```

### GraphEdge

```python
@dataclass
class GraphEdge:
    uuid: str              # Unique edge identifier
    name: str              # Edge name/relationship type
    fact: str              # Relationship description
    source_node_uuid: str  # Source node UUID
    target_node_uuid: str  # Target node UUID
    attributes: Dict[str, Any]  # Extended attributes
    created_at: Optional[str]   # Creation time
    valid_at: Optional[str]     # Valid time
```

### SearchResult

```python
@dataclass
class SearchResult:
    nodes: List[GraphNode]  # Matched nodes
    edges: List[GraphEdge]  # Matched edges
```

## API Mapping Table

| Adapter Method | Zep Cloud API | Graphiti API |
|----------------|---------------|--------------|
| `create_graph()` | `graph.create()` | Record metadata (Graphiti has no explicit create; writing with `group_id` takes effect) |
| `delete_graph()` | `graph.delete()` | Neo4j Cypher delete |
| `add_episode()` | `graph.add()` | `graphiti.add_episode()` |
| `add_episode_batch()` | `graph.add_batch()` | `graphiti.add_episode_bulk()` |
| `search()` | `graph.search()` | Prefer `graphiti.search_()`, fallback `graphiti.search()` |
| `get_all_nodes()` | `node.get_by_graph_id()` | Neo4j Cypher query |
| `get_all_edges()` | `edge.get_by_graph_id()` | Neo4j Cypher query |
| `get_node()` | `node.get()` | Neo4j Cypher query |
| `get_node_edges()` | `node.get_entity_edges()` | Neo4j Cypher query |
| `get_episode_status()` | `episode.get()` | Return processed=true directly (synchronous processing) |
| `wait_for_episode()` | `episode.get()` polling | Return directly (synchronous processing) |
| `set_ontology()` | `graph.set_ontology()` | Not supported |

## Key Adaptation Strategies

### 1. Multi-Graph Isolation

Zep Cloud natively supports multiple `graph_id`s, while Graphiti defaults to a single graph.

**Solution**: Use the `group_id` parameter for data isolation

```python
# Specify group_id when adding an episode in Graphiti
await graphiti.add_episode(
    name=f"episode_{graph_id}",
    episode_body=data,
    group_id=graph_id,  # Used to isolate different project data
    ...
)

# Filter by group_id when querying Neo4j
MATCH (n:Entity) WHERE n.group_id = $graph_id RETURN n
```

### 2. Async to Sync Conversion

Graphiti uses async API, while MiroFish business code uses synchronous calls.

**Solution**: `_run_async()` helper method (uses a persistent event loop, avoiding Neo4j driver binding to a closed loop)

```python
def _run_async(coro):
    """Run async coroutine in sync context (single background thread + run_coroutine_threadsafe)"""
    ...
```

### 3. Episode Wait Mechanism

Zep Cloud's `episode.get()` requires polling to wait for processing to complete, while Graphiti processes synchronously.

**Solution**: Graphiti implementation returns success directly

```python
# ZepCloudClient
def wait_for_episode(self, uuid: str, timeout: int) -> bool:
    # Poll episode.get() until status is done
    ...

# GraphitiClient
def wait_for_episode(self, uuid: str, timeout: int) -> bool:
    # Graphiti processes synchronously, no waiting needed
    return True
```

### 4. Search Result Conversion

The two backends have different search result structures and need to be converted to a unified `SearchResult`.

```python
def _convert_edge(self, edge) -> GraphEdge:
    """Convert Graphiti EdgeResult to GraphEdge"""
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

## Configuration Details

### config.py New Configuration

```python
# Zep backend selection: 'cloud' or 'graphiti'
ZEP_BACKEND = os.environ.get('ZEP_BACKEND', 'cloud')

# Neo4j configuration (used in graphiti mode)
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'password')
```

### Factory Function Logic

```python
def create_zep_client() -> ZepClientAdapter:
    if ZEP_BACKEND == 'graphiti':
        from .zep_graphiti_impl import GraphitiClient
        return GraphitiClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    else:
        from .zep_cloud_impl import ZepCloudClient
        return ZepCloudClient(ZEP_API_KEY)
```

## Known Issues & Workarounds

### graphiti-core Issue #683

Some `graphiti-core` versions attempt to save nested maps when `add_episode()` writes to Neo4j, causing write failures.
Currently bypassed via `backend/app/services/graphiti_patch.py`, which sanitizes data before writing (nested dict/list → JSON strings).
