# MiroFish Zep Service Localization Plan

> This document records the technical plan for replacing MiroFish's Zep Cloud dependency with a local deployment.

## TL;DR (MVP first, then full parity)

- **MVP Goal**: Run the core pipeline (build graph → read entities → search → report/visualization) without depending on Zep Cloud (allowing semantic/field differences).
- **Full Parity Goal**: Align with existing `zep-cloud` graph capabilities and semantics (ontology, temporal fields, search quality/structure, etc.) as much as possible.
- **Recommended Implementation**: Adapter pattern + dual backend (`zep-cloud` existing cloud + `graphiti` local Neo4j).

## 1. Background

### 1.1 Current State

MiroFish uses **Zep Cloud** as its core knowledge graph service:

```
Dependency: zep-cloud==3.13.0
Config: ZEP_API_KEY (required)
```

**Files involved** (5):
- `backend/app/services/graph_builder.py` - Graph building
- `backend/app/services/zep_tools.py` - Search tools (1660 lines)
- `backend/app/services/zep_entity_reader.py` - Entity reading
- `backend/app/services/zep_graph_memory_updater.py` - Memory updating
- `backend/app/services/oasis_profile_generator.py` - Persona generation

### 1.2 Localization Requirements

The interviewer suggested "making the service local." The goal is to eliminate dependency on the Zep Cloud API and achieve fully self-hosted deployment.

---

## 2. Technical Research

### 2.1 Key Findings

| Research Item | Conclusion |
|-------------|------------|
| Zep self-hosted (Community Edition) | **Deprecated/no longer maintained** (officially archived as legacy, though code remains in the repo's `legacy/` directory) |
| zep-python SDK | **Can connect to legacy CE, but cannot “directly replace” this project**: MiroFish currently depends on `zep-cloud`'s Graph API (`client.graph.*`), which is not guaranteed to be consistent with legacy CE / `zep-python` capabilities and models |
| Graphiti | **Recommended OSS direction**: An open-source temporal knowledge graph framework from the Zep team that can serve as a foundation for localization, but **the API is not compatible and requires an adapter layer** |

> **Graphiti** is an open-source graph kernel/framework from the Zep team (Zep itself is also powered by Graphiti).
> It provides similar “graph building + retrieval” capabilities, but **it is not the same service as Zep Cloud**, so an adapter layer is required.
> - GitHub: https://github.com/getzep/graphiti
> - PyPI: https://pypi.org/project/graphiti-core/

### 2.2 Key Conclusions (for the interviewer)

- “Making the service local” in the MiroFish context most directly means: **no longer depending on Zep Cloud**, and instead using a **locally runnable graph storage/retrieval service**.
- Zep CE exists but has been officially deprecated; the more stable direction is: **Graphiti + local graph database (Neo4j/Kuzu/FalkorDB, etc.)**.
- Graphiti is a “framework” rather than the same service as Zep Cloud: therefore, progressive migration must be done through an **adapter**, starting with MVP and then aligning semantics.

### 2.3 MiroFish Zep API Usage List (current `zep-cloud`)

| API | Purpose | Call Location |
|-----|---------|---------------|
| `client.graph.create()` | Create knowledge graph | graph_builder.py |
| `client.graph.set_ontology()` | Set ontology (entity/edge types) | graph_builder.py |
| `client.graph.add()` | Add single episode | zep_graph_memory_updater.py |
| `client.graph.add_batch()` | Batch add episodes | graph_builder.py |
| `client.graph.search()` | Hybrid search (semantic+BM25) | zep_tools.py, oasis_profile_generator.py |
| `client.graph.node.get_by_graph_id()` | Get all nodes in a graph | graph_builder.py, zep_tools.py, zep_entity_reader.py |
| `client.graph.node.get()` | Get single node | zep_tools.py, zep_entity_reader.py |
| `client.graph.node.get_entity_edges()` | Get edges associated with a node | zep_entity_reader.py |
| `client.graph.edge.get_by_graph_id()` | Get all edges in a graph | graph_builder.py, zep_tools.py, zep_entity_reader.py |
| `client.graph.episode.get()` | Get episode status | graph_builder.py |
| `client.graph.delete()` | Delete graph | graph_builder.py |

### 2.4 zep-cloud vs Graphiti API Mapping (High-Level)

| zep-cloud API | Graphiti Equivalent | Compatibility | Adaptation Strategy |
|---------------|---------------------|---------------|---------------------|
| `graph.create()` | Auto-create | Different | Handle automatically during initialization |
| `graph.set_ontology()` | (No 1:1 equivalent) | Needs rewrite | MVP: degrade first; Full parity: add constraints/prompt injection/type mapping |
| `graph.add()` / `add_batch()` | `add_episode()` / `add_episode_bulk()` | Similar | Parameter mapping |
| `graph.search()` | `search()` / `retrieve_nodes()` | Similar | Scope parameter mapping |
| `graph.node.get_by_graph_id()` | `retrieve_nodes()` + Neo4j | Needs adaptation | Cypher query |
| `graph.edge.get_by_graph_id()` | `search()` returns edges | Needs adaptation | Result conversion |
| `graph.episode.get()` | Synchronous processing, no polling needed | Simpler | Return directly |

---

## 3. Recommended Approach: Adapter Pattern

### 3.1 Architecture Design

```
┌─────────────────────────────────────┐
│        MiroFish Existing Code       │
│   (graph_builder, zep_tools, ...)   │
└──────────────┬──────────────────────┘
               │ calls
               ▼
┌─────────────────────────────────────┐
│      ZepClientAdapter (new)         │
│   Unified interface, compatible     │
│   with cloud/graphiti               │
└──────────────┬──────────────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌───────────┐    ┌─────────────────┐
│ Zep Cloud │    │ Graphiti Local  │
│ (original)│    │ Neo4j + LLM     │
└───────────┘    └─────────────────┘
```

### 3.2 Core Approach

1. **Abstraction layer**: Define `ZepClientAdapter` unified interface
2. **Dual implementation**: `ZepCloudClient` + `GraphitiClient`
3. **Configuration-driven**: Switch backend via `ZEP_BACKEND` environment variable
4. **Zero intrusion**: Minimal changes to existing code

---

## 4. Implementation Plan (MVP → Full Parity)

### 4.0 MVP Scope Definition

**Capabilities the MVP must cover (enough to run the main pipeline)**

- Graph building: Write text chunks/episodes to the local graph (Graphiti ingestion)
- Graph reading: Fetch nodes/edges by `graph_id` (for frontend visualization, for simulation preparation stage)
- Search: Support basic retrieval used by ReportAgent / persona generation (at least keyword or semantic)
- Single-point queries: get node, get node edges (for entity details/filtering logic)
- Graph deletion: Clean up local graph data (coarse-grained acceptable during development)

**What MVP explicitly does NOT do / allows degradation (avoid getting bogged down by ontology)**

- Strict semantic alignment of `set_ontology()` (Graphiti has no 1:1 equivalent)
- 100% alignment of Zep Cloud search result fields/structure (first ensure “works”, then ensure “equivalent”)
- Complete alignment of temporal fields such as `valid_at/invalid_at/expired_at`
- `zep_graph_memory_updater.py`'s incremental graph memory updates (can be no-op or just record text episodes for now)

**MVP acceptance criteria (recommend recording a demo before the interview)**

- When `ZEP_BACKEND=graphiti`: Frontend can complete Step1 (ontology + build) and see nodes/edges data in GraphPanel
- Step2 can successfully read entities and generate profiles/config (even if types/filtering are coarser than Zep Cloud)
- Step4 ReportAgent can complete one generation (search returns content, report output is non-empty)

### 4.1 Phase 1: Adapter Layer Design (MVP, 0.5-1 day)

**New file**: `backend/app/services/zep_adapter.py`

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
    """Unified Zep client interface"""

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

> Note: The interface can initially stay “as close to zep-cloud as possible” during the MVP stage, but the Graphiti backend implementation may no-op some methods (e.g., `set_ontology()`).

### 4.2 Phase 2: Cloud Implementation (MVP, 0.5 day)

**New file**: `backend/app/services/zep_cloud_impl.py`

Wrap existing zep-cloud API, implementing the `ZepClientAdapter` interface.

### 4.3 Phase 3: Graphiti Implementation (MVP, 2-4 days)

**New file**: `backend/app/services/zep_graphiti_impl.py`

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

    # ... other method implementations
```

**Key Adaptation Points**:

| Challenge | Solution |
|-----------|----------|
| Multi-graph isolation | **MVP required**: Use `group_id` for data isolation (MiroFish `graph_id` maps directly to Graphiti `group_id`) |
| Read all nodes/edges | **MVP required**: Allow direct Cypher queries on Neo4j, convert results to `GraphNode/GraphEdge` |
| Search result structure | **MVP required**: Map Graphiti returns to existing `SearchResult`, first ensure ReportAgent works |
| Ontology mapping | **MVP degrade first**: `set_ontology()` can no-op or be used only for prompt hints; Full parity adds strong constraints |
| Async/sync adaptation | `_run_async()` reuses a persistent event loop (avoiding the cross-loop issue with `asyncio.run()`) |

### 4.4 Phase 4: Factory Pattern + Configuration (MVP, 0.5 day)

**New file**: `backend/app/services/zep_factory.py`

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

**Modify**: `backend/app/config.py`

```python
# New configuration
ZEP_BACKEND = os.environ.get('ZEP_BACKEND', 'cloud')  # 'cloud' | 'graphiti'
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'password')
```

### 4.5 Phase 5: Migrate Existing Code (MVP, 1-2 days)

**Replacement pattern**:

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

**Files to modify**:

| File | Change Volume |
|------|---------------|
| `graph_builder.py` | Medium |
| `zep_tools.py` | Large |
| `zep_entity_reader.py` | Medium |
| `zep_graph_memory_updater.py` | Small |
| `oasis_profile_generator.py` | Small |

### 4.6 Phase 6: Docker Deployment (MVP, 0.5 day)

**New file**: `docker-compose.local.yml`

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

**Update**: `.env.example`

```env
# Zep backend selection: 'cloud' or 'graphiti'
ZEP_BACKEND=graphiti

# Graphiti local deployment configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# LLM configuration (used by MiroFish uniformly)
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=qwen3-max

# Graphiti reads OPENAI_* by default; the backend will auto-map from LLM_* when not explicitly set
# (you can also explicitly set OPENAI_* to override)
# OPENAI_API_KEY=your_api_key
# OPENAI_BASE_URL=https://api.openai.com/v1

# Graphiti model/embeddings (recommend explicit configuration to avoid incompatible default OpenAI model names)
GRAPHITI_LLM_MODEL=qwen3-max
GRAPHITI_EMBEDDING_MODEL=text-embedding-v4
```

---

## 5. File List (MVP)

### 5.1 New Files

| File Path | Purpose |
|-----------|---------|
| `backend/app/services/zep_adapter.py` | Abstract interface definition |
| `backend/app/services/zep_cloud_impl.py` | Zep Cloud implementation |
| `backend/app/services/zep_graphiti_impl.py` | Graphiti local implementation |
| `backend/app/services/graphiti_patch.py` | graphiti-core workaround (Issue #683) |
| `backend/app/services/zep_factory.py` | Factory function |
| `docker-compose.local.yml` | Neo4j local deployment |
| `backend/requirements-graphiti.txt` | Graphiti environment dependencies (avoiding oasis conflict) |

### 5.2 Modified Files

| File Path | Changes |
|-----------|---------|
| `backend/app/api/graph.py` | cloud/graphiti mode compatibility (no hard dependency on ZEP_API_KEY) |
| `backend/app/api/simulation.py` | cloud/graphiti mode compatibility (no hard dependency on ZEP_API_KEY) |
| `backend/app/services/graph_builder.py` | Replace Zep client |
| `backend/app/services/zep_tools.py` | Replace Zep client |
| `backend/app/services/zep_entity_reader.py` | Replace Zep client |
| `backend/app/services/zep_graph_memory_updater.py` | Replace Zep client |
| `backend/app/services/oasis_profile_generator.py` | Replace Zep client |
| `backend/app/config.py` | Add new configuration items |
| `.env.example` | Add new configuration examples |
| `backend/pyproject.toml` | Set graphiti/oasis as optional extras |

---

## 6. Effort Estimate (MVP vs Full Parity)

### 6.1 MVP (Run the Core Pipeline)

| Phase | Time | Notes |
|-------|------|-------|
| Phase 1: Adapter layer design | 0.5-1 day | Interface definition + data structures |
| Phase 2: Cloud implementation | 0.5 day | Wrap existing API |
| Phase 3: Graphiti implementation | 2-4 days | **Core work (isolation + graph reading + search mapping)** |
| Phase 4: Factory + configuration | 0.5 day | Configuration-driven |
| Phase 5: Code migration | 1-2 days | Replace calls |
| Phase 6: Docker deployment | 0.5 day | Neo4j local deployment |
| Acceptance/demo | 0.5-1 day | Run through acceptance criteria |
| **Total** | **5-9 days** | Depends on Graphiti/Neo4j isolation and query difficulty |

### 6.2 Full Parity (Align Semantics as Much as Possible)

This part is recommended to be split into independent PR milestones:

- Dependency/runtime decoupling: Resolve the `neo4j` Python driver version conflict between `camel-oasis` and `graphiti-core` (see “7.5”)
- Remove temporary patch: Replace/upgrade to a `graphiti-core` version with the fix, or converge to a maintainable fork (see “7.6”)
- Ontology alignment: Pass MiroFish's entity_types/edge_types constraints into Graphiti (or do post-hoc type mapping)
- Temporal field alignment: Add `valid_at/invalid_at/expired_at` etc.
- Search quality alignment: Hybrid retrieval, reranker, pagination/filtering capabilities
- Graph memory updater: Incrementally write simulation events back to the graph and make them searchable

Estimated effort: **1-2+ weeks** (depending on Graphiti's extensibility points and our definition of “equivalent”)

---

## 7. Risks and Challenges

### 7.1 Ontology Mapping (High risk for Full parity; MVP recommended to degrade)

**Problem**: zep-cloud's `set_ontology()` uses dynamic type definitions, while Graphiti uses Pydantic models.

**Solution**:

```python
from pydantic import BaseModel

def create_entity_model(name: str, attributes: Dict[str, type]):
    return type(name, (BaseModel,), {
        '__annotations__': attributes
    })

# Usage example
PersonEntity = create_entity_model('Person', {'name': str, 'age': int})
```

> Note: This represents only one approach. A more realistic solution is to use Graphiti's `group_id` for multi-graph isolation (MiroFish's `graph_id` maps directly to `group_id`); if that's not feasible, you may need “one database/one namespace per graph” for isolation.

### 7.2 Multi-Graph Isolation (Medium-high risk for MVP)

**Problem**: MiroFish creates an independent `graph_id` for each project, while Graphiti uses `group_id` for partitioning.

**Solution**: Prioritize `group_id` isolation: map MiroFish's `graph_id` directly to Graphiti's `group_id`, filtering by `group_id` for both writes and queries; use label/database isolation as a fallback if needed.

```cypher
-- Create a node with group_id
CREATE (n:Entity {group_id: $group_id, name: $name})

-- Query nodes for a specific graph
MATCH (n:Entity {group_id: $group_id}) RETURN n
```

### 7.3 Async/Sync Adaptation (Low risk)

**Problem**: Graphiti has an async API, while MiroFish uses synchronous calls.

**Solution**:

- Do not use `asyncio.run()` (it creates/closes a new loop, which can trigger Neo4j driver “cross-loop binding” issues)
- Provide `_run_async()` in the adapter layer: uniformly submit async calls to a dedicated background thread/event loop for execution (avoiding running loop/cross-loop binding issues)
- Reference implementation: `backend/app/services/zep_graphiti_impl.py`'s `_run_async()` (handles the above scenarios)

### 7.4 LLM Configuration Alignment (Medium risk for MVP)

**Problem**: Graphiti reads configuration in the OpenAI way by default (e.g., `OPENAI_API_KEY`), while MiroFish currently uses the custom naming `LLM_API_KEY/LLM_BASE_URL`.

**Solution** (MVP recommended: take the simplest path first):

- Auto-map `LLM_* → OPENAI_*` at backend startup (only when `OPENAI_*` is not explicitly set), see `backend/app/config.py`
- Recommend explicit configuration for Graphiti-side model name/embedding model:
  - `GRAPHITI_LLM_MODEL` (falls back to `LLM_MODEL_NAME` by default)
  - `GRAPHITI_EMBEDDING_MODEL`
- DashScope embeddings batch size limit needs to be handled (see “7.7”)

#### LLM Endpoint Selection (DashScope / OpenAI both work)

MiroFish backend currently uses the `openai` SDK (OpenAI-compatible). So whether you use OpenAI or DashScope, **you need to provide an OpenAI-compatible `base_url` + `api_key`**.

The example you gave is a “native” DashScope Python SDK call:

- `dashscope.base_http_api_url = “https://dashscope.aliyuncs.com/api/v1”` (native DashScope API)
- `model=”qwen3-max”` (chat model)

But for MiroFish / Graphiti, you should use DashScope's **compatible-mode**:

```env
# ✅ DashScope (Bailian) OpenAI-compatible
LLM_API_KEY=your_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen3-max

# Graphiti reads OPENAI_* by default (backend auto-maps from LLM_* at startup; you can also set explicitly to override)
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

If you prefer to use OpenAI, the same applies:

```env
# ✅ OpenAI (OpenAI-compatible)
LLM_API_KEY=your_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=your_chat_model

# Graphiti reads OPENAI_* by default (backend auto-maps from LLM_* at startup; you can also set explicitly to override)
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.openai.com/v1
```

#### Embeddings (DashScope embedding info you provided)

Your embedding example:

- API: `dashscope.TextEmbedding.call(...)`
- Model: `text-embedding-v4`

There are two implementation approaches (MVP recommends trying A first, fall back to B if it doesn't work):

- **A: OpenAI-compatible embeddings** (if DashScope compatible-mode supports `/embeddings`)
  - Have the `openai` SDK use `https://dashscope.aliyuncs.com/compatible-mode/v1`
  - Use `text-embedding-v4` as the embedding model
- **B: DashScope native embeddings** (if compatible-mode doesn't support embeddings)
  - Integrate DashScope embedding separately in the Graphiti backend (using `dashscope.TextEmbedding`)
  - Requires additional `DASHSCOPE_API_KEY` configuration (do not commit to repo, only store in local `.env`)

### 7.5 Dependency Conflict (Full Parity Blocker)

The project currently needs both:

- `camel-oasis` (simulation engine)
- `graphiti-core` (local graph)

However, their version requirements for the **Python Neo4j driver** conflict (verified locally). This makes it difficult to “install both in one venv,” affecting full parity (enabling both simulation + local graph in the complete pipeline).

Current known constraints (based on actual project dependencies):

- `camel-oasis==0.2.5` depends on `neo4j==5.23.0`
- `graphiti-core>=0.25.0,<0.26.0` depends on `neo4j>=5.26.0`

Suggested resolution paths (by priority):

1. **Upgrade/replace oasis dependency**: If upstream `camel-oasis` can be upgraded to be compatible with a newer `neo4j` driver (or relaxes version constraints), this is the cleanest solution.
2. **Split runtime**: Separate Graphiti-related logic into an independent process/service (separate venv / separate container), interacting with the main backend via HTTP/RPC, avoiding Python dependency conflicts.
3. **Choose a compatible graphiti-core version**: Fall back to a `graphiti-core` version compatible with `neo4j==5.23.x`, but need to assess feature/bugfix coverage (including Issue #683).

### 7.6 graphiti-core Issue #683 (MVP bypassed; Full parity needs removal)

Confirmed regression in `graphiti-core`: when writing to Neo4j, it attempts to save nested maps (not supported by Neo4j properties), causing `add_episode()` to fail, blocking end-to-end.

Current MVP workaround: `backend/app/services/graphiti_patch.py` monkey-patches graphiti-core's write path, sanitizing nested dict/list to JSON strings before writing.

Full parity needs to converge this workaround into a maintainable solution:

- Priority: Upgrade to a `graphiti-core` version with the official fix and delete the patch
- Secondary: Maintain the patch short-term, but add version/signature validation and a toggle (avoid silently broken)
- Fallback: Maintain a small fork (pin version + backport fix yourself), ensuring reproducible builds

### 7.7 DashScope Embeddings Batch Limit (P0: Must handle when using DashScope)

Under DashScope's OpenAI-compatible `/embeddings` endpoint, there is a batch size limit per request (currently observed at **<= 10**). Graphiti embeds nodes/edges during writes (e.g., calling `create_batch()` with multiple edge facts at once), and when the number of items to embed exceeds 10, it triggers:

```
Error code: 400 - batch size is invalid, it should not be larger than 10
```

Impact:

- Graph building may reach a state of “some data already written, but embedding stage failure causes the overall task to fail” (requires cleaning the `group_id` and rebuilding to avoid dirty data).

Recommended fix (workaround, usable for MVP):

- Inject a “batch-limited embedder” in the Graphiti adapter: chunk `create_batch(input_data_list)` (each chunk <= 10), call the underlying OpenAI-compatible embeddings API chunk by chunk, then concatenate and return the results.
- Implementation location:
  - Recommended: Wrap a layer around `_build_default_embedder()` in `backend/app/services/zep_graphiti_impl.py`
  - Alternative: Do a monkey-patch like Issue #683 (patch `graphiti_core.embedder.openai.OpenAIEmbedder.create_batch`)

Full parity recommendation:

- Make the batch limit a configurable item (e.g., `GRAPHITI_EMBEDDING_BATCH_SIZE`), and clearly document the default value and applicable range in docs/startup scripts.

---

## 8. Quick Start

### 8.1 Local Deployment

```bash
# 1. Start Neo4j
docker-compose -f docker-compose.local.yml up -d

# 2. Wait for Neo4j to be ready
sleep 30

# 3. Configure environment variables
export ZEP_BACKEND=graphiti
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
# Only need to configure LLM_*, backend will auto-map to OPENAI_*
export LLM_API_KEY=your_key
export LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export LLM_MODEL_NAME=qwen3-max
export GRAPHITI_LLM_MODEL=qwen3-max
export GRAPHITI_EMBEDDING_MODEL=text-embedding-v4

# 4. Install dependencies
# Note: graphiti and oasis currently have neo4j driver conflict; recommend separate venv/container
(cd backend && uv sync --extra graphiti)

# 5. Start services
npm run dev
```

### 8.2 Verification

```bash
# Access Neo4j Browser
open http://localhost:7474

# Test MiroFish
open http://localhost:3000
```

---

## 9. Design Highlights

1. **Adapter pattern**: Supports seamless cloud/local switching, demonstrating engineering capability
2. **Zero-intrusion migration**: Minimal changes to existing code, backward compatible
3. **Configuration-driven**: Switch backend via environment variables, no code changes needed
4. **Docker one-command deployment**: Lowers the usage barrier
5. **End-to-end acceptance checklist**: Reproducible pass-through with demo recording

---

## 10. References

- [Graphiti GitHub](https://github.com/getzep/graphiti)
- [Graphiti Documentation](https://help.getzep.com/graphiti)
- [graphiti-core PyPI](https://pypi.org/project/graphiti-core/)
- [Zep Cloud API Documentation](https://help.getzep.com/)
- [Neo4j Docker Hub](https://hub.docker.com/_/neo4j)
