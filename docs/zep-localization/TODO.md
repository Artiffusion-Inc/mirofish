# Zep Localization Improvement Checklist

> Current status: MVP verified, the following are follow-up optimization items

## Priority Guide

- **P0**: Required for production
- **P1**: Strongly recommended
- **P2**: Nice to have

---

## Architecture Optimization

### [ ] P1: Decouple Graph Service
Separate Graphiti from the Flask process and run it as an independent service.

**Benefits**:
- Completely resolves the Flask sync + Graphiti async conflict
- Resolves neo4j driver version conflict (independent venv)
- Process isolation, failures don't affect each other
- Independently scalable

**Approach**:
```
┌─────────┐      HTTP       ┌──────────────────┐
│  Flask  │ ──────────────▶ │ Graphiti Service │
│ Backend │                  │ (FastAPI/gRPC)   │
└─────────┘                  └──────────────────┘
                                   │
                                   ▼
                             Neo4j + Graphiti
```

**Effort**: 2-3 days

---

## Error Handling

### [ ] P0: Graphiti Initialization Concurrency Protection
Currently `GraphitiClient._ensure_initialized()` may trigger duplicate initialization under concurrent first requests (duplicate index creation / duplicate driver creation / duplicate patching). Need to add locking and ensure idempotency.

### [ ] P0: Event Loop Startup Failure Handling
```python
# Current: No handling
# Improvement: Add retry + degradation
def _ensure_async_loop():
    # TODO: Add startup timeout detection
    # TODO: Degradation strategy when startup fails
```

### [ ] P0: Neo4j Connection Exception Handling
```python
# Current: Connection failure throws exception directly
# Improvement:
# - Connection pool health check
# - Auto-reconnect
# - Graceful degradation (return empty results instead of crashing)
```

### [ ] P1: Graphiti Operation Timeout Handling
```python
# Current: Hardcoded 300s timeout
# Improvement:
# - Configurable timeout
# - Resource cleanup after timeout
# - Progress feedback for long operations
```

### [ ] P1: Process Exit Cleanup (driver / loop)
Works locally, but production / long-running deployments need controlled shutdown:
- Flask teardown / process exit: `graphiti.close()` + `driver.close()`
- Background loop thread stop/join (at minimum avoid zombie threads / resource leaks)

### [ ] P1: graphiti-core Workaround Risk Control (recoverable)
The current monkey-patch of graphiti-core is a temporary “make it work” solution. Recommend adding the following guardrails:
- Validate graphiti-core version/function signature at startup, fail fast on mismatch (avoid silently corrupting data)
- Print explicit logs: whether patch is active, which upstream issue it targets, how to disable
- Reserve toggle: `GRAPHITI_DISABLE_PATCH=1`
- After upstream fix is merged, remove patch and mark the deletable version range in docs

---

## Configuration Management

### [ ] P0: Externalize Hardcoded Configuration

| Current Location | Configuration Item | Should Become |
|-----------------|-------------------|---------------|
| `backend/app/config.py` | `NEO4J_PASSWORD` default value `password` | Remove default/strong validation for production |
| `backend/app/services/zep_graphiti_impl.py` | `_run_async()` timeout 300s | Environment variable (e.g., `GRAPHITI_ASYNC_CALL_TIMEOUT_S`) |
| `backend/app/services/simulation_runner.py` | `.venv-simulation` fallback path | Environment variable (already supports `SIMULATION_PYTHON`, can add one-command script/validation) |
| `backend/app/services/zep_graphiti_impl.py` | DashScope embedding `batch_size=10` | Environment variable (e.g., `GRAPHITI_EMBEDDING_BATCH_SIZE`) |

### [ ] P1: Configuration Validation Enhancement
Currently has basic validation (`backend/app/config.py`'s `Config.validate()`), recommend adding:
- LLM/embedder configuration hints in graphiti mode (e.g., suggestions when `GRAPHITI_*` is not set)
- Simulation venv availability check (show explicit “how to create .venv-simulation” instructions when dependencies are missing)

### [ ] P1: Environment Variable Naming Consolidation
Consolidate scattered “default values / magic numbers” into explicit env vars (examples):
- `GRAPHITI_LOOP_STARTUP_TIMEOUT_S`
- `GRAPHITI_ASYNC_CALL_TIMEOUT_S`
- `GRAPHITI_EMBEDDING_BATCH_SIZE` (DashScope <= 10)
- `SIMULATION_PYTHON` (simulation independent venv)

---

## Observability

### [ ] P1: Structured Logging
```python
# Current: logger.info("message")
# Improvement:
logger.info("graphiti_operation", extra={
    "operation": "add_episode",
    "group_id": group_id,
    "duration_ms": duration,
    "status": "success"
})
```

### [ ] P1: Metrics Collection
- Event loop queue depth
- Graphiti operation latency distribution
- Neo4j connection pool status
- DashScope API call count/latency

### [ ] P2: Health Check Endpoint
```
GET /api/health
{
  "status": "healthy",
  "neo4j": "connected",
  "graphiti_loop": "running",
  "simulation_env": "available"
}
```

---

## Performance Optimization

### [ ] P2: Concurrency Improvement
Current: Single background thread executes all Graphiti operations serially

**Approach A**: Loop Pool
```python
# Multiple background threads, each with an independent event loop
# Requests hashed by group_id to a fixed thread
```

**Approach B**: Async Queue
```python
# Write operations enqueued, processed in batches
# Read operations executed directly
```

### [ ] P2: Connection Pool Optimization
- Neo4j connection pool size tuning
- Connection preheating
- Idle connection recycling

---

## Testing

### [ ] P0: Integration Testing
```python
# tests/integration/test_graphiti_flow.py
def test_full_flow():
    # Upload PDF → Build graph → Run simulation → Generate report
    pass
```

### [ ] P1: Event Loop Stress Testing
```python
def test_concurrent_requests():
    # Simulate multiple Flask requests calling Graphiti simultaneously
    # Verify no deadlocks, no data races
    pass
```

### [ ] P1: Fault Injection Testing
- Neo4j disconnection recovery
- DashScope API timeout
- Insufficient disk space

---

## Documentation

### [ ] P1: API Documentation
- Graphiti local client interface documentation
- Differences from Zep Cloud

### [ ] P2: Operations Manual
- Daily maintenance commands
- Troubleshooting procedures
- Backup and recovery

---

## Dependency Management

### [ ] P1: Lock Dependency Versions
```bash
# Current: requirements.txt has loose version ranges
# Improvement: Generate exact version lock files
uv pip compile requirements.in -o requirements.txt
```

### [ ] P1: One-Command Dual Environment (graphiti / simulation)
The neo4j driver version conflict between graphiti and oasis exists objectively. Recommend productizing the “split venv / split process” approach:
- Provide `make venv-graphiti` / `make venv-simulation` (or scripts)
- More explicit frontend/backend prompts (show “simulation venv required” instead of “No module named” when dependencies are missing)

### [ ] P2: Dependency Security Scanning
```bash
# Add to CI
pip-audit
```

---

## Records

| Date | Completed Items | Notes |
|------|----------------|-------|
| 2026-01-05 | MVP verified | Dual environment isolation + single background thread approach |
