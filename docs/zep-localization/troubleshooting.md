# Zep Localization Troubleshooting Guide

This document records problems encountered during the Zep localization (graphiti-core + Neo4j) implementation and their solutions.

## 1. Neo4j Version Conflict

### Problem Description
The project has two dependencies with conflicting requirements for the neo4j driver version:
- `camel-ai` (used for simulation) requires `neo4j==5.23.0`
- `graphiti-core` (used for knowledge graph) requires `neo4j>=5.26.0`

### Solution
**Dual virtual environment isolation**:

```
backend/
├── .venv/              # Main environment (Flask + graphiti-core)
│   └── neo4j 6.0.3
└── .venv-simulation/   # Simulation environment (camel-ai/oasis)
    └── neo4j 5.23.0
```

Implementation details:
1. Create a separate simulation environment (requires Python 3.10-3.11; camel-oasis does not support 3.12+):
   ```bash
   cd backend
   uv venv .venv-simulation --python 3.11
   source .venv-simulation/bin/activate
   uv pip install camel-oasis==0.2.5 camel-ai==0.2.78 openai python-dotenv
   ```

2. Modify `simulation_runner.py` to auto-detect and use the separate environment:
   ```python
   def _get_simulation_python() -> str:
       # Priority: environment variable > .venv-simulation > current Python
       env_python = os.environ.get('SIMULATION_PYTHON')
       if env_python and os.path.isfile(env_python):
           return env_python

       backend_dir = os.path.dirname(...)
       sim_venv_python = os.path.join(backend_dir, '.venv-simulation', 'bin', 'python')
       if os.path.isfile(sim_venv_python):
           return sim_venv_python

       return sys.executable
   ```

3. The simulation script already runs via `subprocess.Popen`, providing natural process isolation

---

## 2. DashScope Embedding Batch Size Limit

### Problem Description
The DashScope API has a batch size limit for embedding requests (maximum 10 items), but `graphiti-core`'s `OpenAIEmbedder` sends all input at once, causing a 400 error:
```
Error code: 400 - ... batch size is invalid, it should not be larger than 10
```

### Solution
Create a `DashScopeEmbedderWrapper` that automatically chunks requests:

```python
class DashScopeEmbedderWrapper:
    def __init__(self, embedder, max_batch_size=10):
        self._embedder = embedder
        self.max_batch_size = max_batch_size

    async def create(self, input_data) -> list[float]:
        return await self._embedder.create(input_data)

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        if len(input_data_list) <= self.max_batch_size:
            return await self._embedder.create_batch(input_data_list)

        # Chunk processing
        results = []
        for i in range(0, len(input_data_list), self.max_batch_size):
            batch = input_data_list[i:i + self.max_batch_size]
            batch_result = await self._embedder.create_batch(batch)
            results.extend(batch_result)
        return results
```

Location: `backend/app/services/zep_graphiti_impl.py`

---

## 3. Event Loop Conflict Between Flask Sync Framework and Graphiti Async Library

### Problem Description
`graphiti-core` is a purely async library, but Flask is a synchronous framework. Multiple errors occur when calling async code in Flask requests:

**Error 1**: `RuntimeError: This event loop is already running`
**Error 2**: `RuntimeError: cannot enter context: ... is already entered`
**Error 3**: `RuntimeError: Leaving task <Task-X> does not match the current task <Task-Y>`

### Analysis
Initially attempted approaches and their problems:

1. **Applying `nest_asyncio.apply()` globally** - Modifies event loop internal behavior, conflicts with shared loop across threads
2. **Persistent event loop + multithreading** - Multiple Flask request threads simultaneously driving the same loop, causing context variable conflicts
3. **Calling `asyncio.run()` each time** - Neo4j driver errors about "bound to a different loop"

### Solution
**Single background thread + dedicated event loop (Approach A)**:

```
Flask request thread ────────────────────────────────────┐
                                                    │
Flask request thread ──► asyncio.run_coroutine_threadsafe ──► dedicated background thread
                                                    │   (loop.run_forever)
Flask request thread ────────────────────────────────────┘   ↓
                                                    Graphiti / Neo4j driver
                                                    (always bound to the same loop)
```

Implementation:

```python
_async_loop: Optional[asyncio.AbstractEventLoop] = None
_async_thread: Optional[threading.Thread] = None
_init_lock = threading.Lock()

def _start_async_loop():
    """Start event loop in background thread"""
    global _async_loop
    _async_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_async_loop)
    _async_loop.run_forever()

def _ensure_async_loop():
    """Ensure background event loop is started"""
    global _async_thread
    if _async_thread is None or not _async_thread.is_alive():
        with _init_lock:
            if _async_thread is None or not _async_thread.is_alive():
                _async_thread = threading.Thread(
                    target=_start_async_loop,
                    daemon=True,
                    name="graphiti-async-loop"
                )
                _async_thread.start()
                while _async_loop is None:
                    time.sleep(0.01)

def _run_async(coro):
    """Run async coroutine in sync context"""
    _ensure_async_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _async_loop)
    return future.result(timeout=300)
```

**Key points**:
- Removed `nest_asyncio`
- Single background thread + `run_forever()`
- Flask submits tasks via `run_coroutine_threadsafe`
- Neo4j driver is always bound to the same loop
- Serial execution is sufficient for MVP scenarios; can be extended to a loop pool if concurrency is needed

Location: `backend/app/services/zep_graphiti_impl.py`

---

## 4. Frontend Simulation Status Display Issue

### Problem Description
When simulation fails, the frontend status display is incorrect (shows "running" indefinitely).

### Solution
Add `failed` status detection in `Step3Simulation.vue`'s `fetchRunStatus()`:

```javascript
if (data.runner_status === 'failed') {
  const errorMsg = data.error || 'Simulation run failed'
  addLog(`✗ Simulation failed: ${errorMsg}`)
  phase.value = 2
  stopPolling()
  emit('update-status', 'error')
  return
}
```

---

## Local Development Environment Setup

### Prerequisites
- Python 3.11 (required for simulation environment; camel-oasis does not support 3.12+)
- Neo4j database
- Node.js (frontend)

### Quick Start

```bash
# 1. Start Neo4j
docker-compose -f docker-compose.local.yml up -d neo4j

# 2. Start backend (main environment)
cd backend
source .venv/bin/activate
python run.py

# 3. Start frontend
cd frontend
npm run dev
```

### Data Cleanup

```bash
# Clean up Neo4j
.venv/bin/python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
with d.session() as s:
    s.run('MATCH (n) DETACH DELETE n')
d.close()
"

# Clean up simulation data
rm -rf uploads/simulations/* uploads/projects/*
```

### Verify Environment Isolation

```bash
# Check neo4j version
echo "Main environment: $(.venv/bin/python -c 'import neo4j; print(neo4j.__version__)')"
echo "Simulation environment: $(.venv-simulation/bin/python -c 'import neo4j; print(neo4j.__version__)')"
# Expected: main environment 6.0.3, simulation environment 5.23.0
```

---

## Future Optimization Directions

1. **Decouple Graph Service**: Make Graphiti an independent process/service (FastAPI), completely resolving the event loop and dependency conflict issues
2. **Concurrency Optimization**: If higher throughput is needed, extend to a loop pool (multiple threads, multiple loops, multiple Graphiti instances)
3. **Production Deployment**: Consider using Gunicorn + gevent or switching to FastAPI