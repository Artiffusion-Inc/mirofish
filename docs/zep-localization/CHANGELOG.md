# Zep Localization MVP Change List

## Background

MiroFish originally relied on Zep Cloud for knowledge graph and memory services. The goals of this localization are:

1. **Replace Zep Cloud**: Run the main pipeline without needing a Zep Cloud API Key (LLM API still required)
2. **Reduce costs**: Avoid Zep Cloud call costs, suitable for development and demos
3. **Data sovereignty**: All data stored in local Neo4j, easier to debug and control

## Technical Approach

Use `graphiti-core` + `Neo4j` to replace Zep Cloud, implementing the same interface (`ZepClientAdapter`).

Core challenges:
- graphiti-core is an async library, Flask is a synchronous framework
- camel-ai and graphiti-core have conflicting neo4j driver version requirements
- DashScope Embedding API has batch size limits

---

## Implemented Changes

### 1. Adapter + Dual Backend Switching

**Files**:
- `backend/app/services/zep_adapter.py`
- `backend/app/services/zep_cloud_impl.py`
- `backend/app/services/zep_factory.py`

**What was done**:
- Introduced `ZepClientAdapter`, converging cloud/graphiti differences to the implementation layer
- Switch backend via `ZEP_BACKEND=cloud|graphiti` configuration

---

### 2. Graphiti Local Client

**File**: `backend/app/services/zep_graphiti_impl.py`

**Why**:
- Zep Cloud requires an API Key and network connection
- A local alternative implementing the same interface was needed

**What was done**:
- Implemented `GraphitiClient` class, inheriting the `ZepClientAdapter` interface
- Single background thread + dedicated event loop, resolving Flask sync + Graphiti async conflict
- `DashScopeEmbedderWrapper` wrapper, automatically chunking Embedding requests (batch <= 10)

**What it does**:
- Runs knowledge graph service locally, without Zep Cloud
- Flask request threads safely call async Graphiti API
- Compatible with DashScope Embedding API batch limits

---

### 3. Dual Virtual Environment Isolation (Recommended Approach)

> `.venv/` directories are not committed to the repo (see `.gitignore`). This documents the recommended local development structure.

**Recommended structure**:
- `backend/.venv/` - Main environment (Flask + graphiti-core)
- `backend/.venv-simulation/` - Simulation environment (camel-ai/oasis)

**Why**:
- camel-ai requires `neo4j==5.23.0`
- graphiti-core requires `neo4j>=5.26.0`
- The same environment cannot satisfy both

**What was done**:
- Created independent `.venv-simulation` environment using Python 3.11
- Simulation scripts run via subprocess, providing natural process isolation

**What it does**:
- Both libraries can use their compatible neo4j versions
- No need to fork or modify any dependency library

---

### 4. Simulation Environment Auto-Detection

**File**: `backend/app/services/simulation_runner.py`

**Why**:
- Simulation scripts need to use the isolated environment's Python interpreter
- Auto-detection avoids manual configuration

**What was done**:
- Added `_get_simulation_python()` function
- Priority: environment variable `SIMULATION_PYTHON` > `.venv-simulation/bin/python` > current Python

**What it does**:
- Automatically uses the correct Python environment for running simulations
- Supports override via environment variable for deployment

---

### 5. Frontend State Fix

**File**: `frontend/src/components/Step3Simulation.vue`

**Why**:
- When simulation fails, the frontend state was displayed incorrectly (always showing running)

**What was done**:
- Added `failed` status detection in `fetchRunStatus()`
- Stops polling on failure, displays correct state

**What it does**:
- Users can see whether the simulation failed
- No longer infinitely polls a finished simulation

---

## New Files

| File | Purpose |
|------|---------|
| `LOCAL-STARTUP.md` | Local version startup guide (repo root) |
| `docs/zep-localization/troubleshooting.md` | Troubleshooting guide |
| `docs/zep-localization/TODO.md` | Pending improvements list |
| `docs/zep-localization/CHANGELOG.md` | This document |
| `backend/app/services/zep_adapter.py` | Adapter interface definition |
| `backend/app/services/zep_cloud_impl.py` | Zep Cloud adapter implementation |
| `backend/app/services/zep_graphiti_impl.py` | Graphiti local implementation |
| `backend/app/services/graphiti_patch.py` | graphiti-core workaround (Issue #683) |
| `backend/app/services/zep_factory.py` | Client factory + singleton |
| `docker-compose.local.yml` | Neo4j local deployment |
| `backend/requirements-graphiti.txt` | graphiti environment minimal dependencies (optional) |

---

## Modified Files Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `backend/app/services/zep_graphiti_impl.py` | Refactor | Single background thread + DashScope Wrapper |
| `backend/app/config.py` | Enhancement | `LLM_* → OPENAI_*` mapping + graphiti configuration |
| `backend/pyproject.toml` | Adjustment | graphiti/oasis set as optional extras |
| `backend/app/services/simulation_runner.py` | New function | `_get_simulation_python()` |
| `frontend/src/components/Step3Simulation.vue` | Fix | failed status detection |

---

## Verification Method

```bash
# 1. Check environment isolation
cd backend
echo "Main env: $(.venv/bin/python -c 'import neo4j; print(neo4j.__version__)')"
echo "Simulation env: $(.venv-simulation/bin/python -c 'import neo4j; print(neo4j.__version__)')"
# Expected: main env 6.x, simulation env 5.23.0

# 2. Full pipeline test
# Frontend: Upload PDF → Build graph → Run simulation → Generate report
```

---

## Known Limitations

1. **Serial execution**: All Graphiti operations execute serially in a single background thread, which may become a bottleneck in high-concurrency scenarios
2. **Flask + async**: An architectural compromise; long-term recommendation is to make the graph service independent
3. **Hardcoded configuration**: Some configuration values (timeouts, batch sizes) are hardcoded

See [TODO.md](TODO.md) for future optimization plans.
