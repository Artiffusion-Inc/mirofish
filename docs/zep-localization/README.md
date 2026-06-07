# Zep Localization Implementation

Migrate MiroFish's knowledge graph backend from Zep Cloud to a local Graphiti + Neo4j solution.

## Background

MiroFish originally relied on Zep Cloud as its knowledge graph service. To support local deployment requirements, a dual backend architecture was implemented:

- **Zep Cloud**: Original cloud service, suitable for rapid development
- **Graphiti + Neo4j**: Local deployment solution, fully open source

## Architecture Overview

```
┌─────────────────────────────────────┐
│        MiroFish Business Code       │
│   (graph_builder, zep_tools, ...)   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│      ZepClientAdapter (Adapter)     │
│         Unified API Interface       │
└──────────────┬──────────────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌───────────┐    ┌─────────────────┐
│ Zep Cloud │    │ Graphiti Local  │
│ (Cloud)   │    │ Neo4j + LLM     │
└───────────┘    └─────────────────┘
```

## Quick Start

### Using the Graphiti Local Backend

```bash
# 1. Start Neo4j
docker-compose -f docker-compose.local.yml up -d

# 2. Wait for the service to be ready
docker-compose -f docker-compose.local.yml ps

# 3. Install backend dependencies (required for graphiti mode)
cd backend
uv sync --extra graphiti

# 4. Set environment variables (at minimum LLM_* is required; OPENAI_* auto-maps from LLM_*)
export ZEP_BACKEND=graphiti
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
export LLM_API_KEY=your_api_key
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL_NAME=your_chat_model
export GRAPHITI_LLM_MODEL=your_chat_model
export GRAPHITI_EMBEDDING_MODEL=your_embedding_model

# 5. Start the backend
uv run python run.py
```

### Using the Zep Cloud Backend

```bash
# 1. Install backend dependencies (cloud mode doesn't need the graphiti extra)
cd backend
uv sync

# 2. Set environment variables (LLM_* still needed for ontology/report capabilities)
export ZEP_BACKEND=cloud  # or leave unset, defaults to cloud
export ZEP_API_KEY=your_api_key
export LLM_API_KEY=your_api_key
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL_NAME=your_chat_model

# 3. Start the backend
uv run python run.py
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_KEY` | LLM API Key (required for backend) | - |
| `LLM_BASE_URL` | OpenAI-compatible Base URL | `https://api.openai.com/v1` |
| `LLM_MODEL_NAME` | Default chat model | `gpt-4o-mini` |
| `ZEP_BACKEND` | Backend selection: `cloud` or `graphiti` | `cloud` |
| `ZEP_API_KEY` | Zep Cloud API key (required for cloud mode) | - |
| `NEO4J_URI` | Neo4j connection address | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `password` |
| `OPENAI_API_KEY` | OpenAI-compatible key for Graphiti (auto-inherits `LLM_API_KEY` if not set) | - |
| `OPENAI_BASE_URL` | OpenAI-compatible Base URL for Graphiti (auto-inherits `LLM_BASE_URL` if not set) | - |
| `GRAPHITI_LLM_MODEL` | LLM model name used by Graphiti (recommend explicit setting) | Inherits `LLM_MODEL_NAME` |
| `GRAPHITI_EMBEDDING_MODEL` | Embedding model name used by Graphiti (DashScope recommends `text-embedding-v4`) | Graphiti default |

## Known Limitations

### 1) graphiti-core Issue #683 (bypassed via workaround)

In some `graphiti-core` versions, `add_episode()` attempts to save nested maps when writing to Neo4j (not supported by Neo4j properties), causing write failures.
Currently bypassed within MiroFish via `backend/app/services/graphiti_patch.py` which sanitizes (nested dict/list → JSON string) to avoid blocking.

### 2) Dependency Conflict (Full parity blocker)

`camel-oasis` and `graphiti-core` have conflicting Python Neo4j driver version constraints, making it difficult to install both in the same venv.
If you need the full pipeline (simulation + local graph) enabled simultaneously, refer to section "7.5" in `docs/zep-localization-plan.md` for upgrading dependencies or splitting runtimes.

## Documentation Directory

- [Architecture Design](./architecture.md) - Adapter pattern design, file list, API mapping
- [Migration Guide](./migration-guide.md) - Steps for migrating from Zep Cloud to Graphiti

## Technical Highlights

1. **Adapter pattern**: Business code switches backends without awareness
2. **Configuration-driven**: Select backend via environment variables, no code changes needed
3. **Docker one-command deployment**: Neo4j containerized, works out of the box
4. **Backward compatible**: Zep Cloud support retained, can switch back at any time
