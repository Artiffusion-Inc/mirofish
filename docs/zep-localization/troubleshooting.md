# Zep 本地化问题排查指南

本文档记录 Zep 本地化（graphiti-core + Neo4j）实施过程中遇到的问题及解决方案。

## 1. Neo4j 版本冲突

### 问题描述
项目中存在两个依赖对 neo4j driver 版本有冲突要求：
- `camel-ai` (用于模拟) 需要 `neo4j==5.23.0`
- `graphiti-core` (用于知识图谱) 需要 `neo4j>=5.26.0`

### 解决方案
**双虚拟环境隔离**：

```
backend/
├── .venv/              # 主环境 (Flask + graphiti-core)
│   └── neo4j 6.0.3
└── .venv-simulation/   # 模拟环境 (camel-ai/oasis)
    └── neo4j 5.23.0
```

实现细节：
1. 创建独立的模拟环境（需要 Python 3.10-3.11，camel-oasis 不支持 3.12+）：
   ```bash
   cd backend
   uv venv .venv-simulation --python 3.11
   source .venv-simulation/bin/activate
   uv pip install camel-oasis==0.2.5 camel-ai==0.2.78 openai python-dotenv
   ```

2. 修改 `simulation_runner.py`，自动检测并使用独立环境：
   ```python
   def _get_simulation_python() -> str:
       # 优先级：环境变量 > .venv-simulation > 当前 Python
       env_python = os.environ.get('SIMULATION_PYTHON')
       if env_python and os.path.isfile(env_python):
           return env_python

       backend_dir = os.path.dirname(...)
       sim_venv_python = os.path.join(backend_dir, '.venv-simulation', 'bin', 'python')
       if os.path.isfile(sim_venv_python):
           return sim_venv_python

       return sys.executable
   ```

3. 模拟脚本已通过 `subprocess.Popen` 运行，天然进程隔离

---

## 2. DashScope Embedding 批次大小限制

### 问题描述
DashScope API 对 embedding 请求有批次大小限制（最大 10 条），但 `graphiti-core` 的 `OpenAIEmbedder` 会将所有输入一次性发送，导致 400 错误：
```
Error code: 400 - ... batch size is invalid, it should not be larger than 10
```

### 解决方案
创建 `DashScopeEmbedderWrapper` 包装器，自动分块处理：

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

        # 分块处理
        results = []
        for i in range(0, len(input_data_list), self.max_batch_size):
            batch = input_data_list[i:i + self.max_batch_size]
            batch_result = await self._embedder.create_batch(batch)
            results.extend(batch_result)
        return results
```

位置：`backend/app/services/zep_graphiti_impl.py`

---

## 3. Flask 同步框架 + Graphiti 异步库的事件循环冲突

### 问题描述
`graphiti-core` 是纯异步库，但 Flask 是同步框架。在 Flask 请求中调用异步代码时出现多种错误：

**错误 1**：`RuntimeError: This event loop is already running`
**错误 2**：`RuntimeError: cannot enter context: ... is already entered`
**错误 3**：`RuntimeError: Leaving task <Task-X> does not match the current task <Task-Y>`

### 问题分析
最初尝试的方案及其问题：

1. **`nest_asyncio.apply()` 全局应用** - 修改事件循环内部行为，与多线程共享循环冲突
2. **持久事件循环 + 多线程** - 多个 Flask 请求线程同时驱动同一个循环，导致 context variable 冲突
3. **每次调用 `asyncio.run()`** - Neo4j driver 报错"绑定到不同循环"

### 解决方案
**单后台线程 + 专用事件循环（方案 A）**：

```
Flask 请求线程 ─────────────────────────────────────┐
                                                    │
Flask 请求线程 ──► asyncio.run_coroutine_threadsafe ──► 专用后台线程
                                                    │   (loop.run_forever)
Flask 请求线程 ─────────────────────────────────────┘   ↓
                                                    Graphiti / Neo4j driver
                                                    (始终绑定同一循环)
```

实现代码：

```python
_async_loop: Optional[asyncio.AbstractEventLoop] = None
_async_thread: Optional[threading.Thread] = None
_init_lock = threading.Lock()

def _start_async_loop():
    """在后台线程中启动事件循环"""
    global _async_loop
    _async_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_async_loop)
    _async_loop.run_forever()

def _ensure_async_loop():
    """确保后台事件循环已启动"""
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
    """在同步上下文中运行异步协程"""
    _ensure_async_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _async_loop)
    return future.result(timeout=300)
```

**关键点**：
- 移除 `nest_asyncio`
- 单后台线程 + `run_forever()`
- Flask 通过 `run_coroutine_threadsafe` 提交任务
- Neo4j driver 始终绑定同一循环
- 串行执行对 MVP 场景足够，如需并发可扩展为 loop pool

位置：`backend/app/services/zep_graphiti_impl.py`

---

## 4. 前端模拟状态显示问题

### 问题描述
模拟失败时，前端状态显示不正确（一直显示运行中）。

### 解决方案
在 `Step3Simulation.vue` 的 `fetchRunStatus()` 中添加 `failed` 状态检测：

```javascript
if (data.runner_status === 'failed') {
  const errorMsg = data.error || '模拟运行失败'
  addLog(`✗ 模拟失败: ${errorMsg}`)
  phase.value = 2
  stopPolling()
  emit('update-status', 'error')
  return
}
```

---

## 本地开发环境设置

### 前置要求
- Python 3.11（模拟环境需要，camel-oasis 不支持 3.12+）
- Neo4j 数据库
- Node.js（前端）

### 快速启动

```bash
# 1. 启动 Neo4j
docker-compose -f docker-compose.local.yml up -d neo4j

# 2. 启动后端（主环境）
cd backend
source .venv/bin/activate
python run.py

# 3. 启动前端
cd frontend
npm run dev
```

### 数据清理

```bash
# 清理 Neo4j
.venv/bin/python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
with d.session() as s:
    s.run('MATCH (n) DETACH DELETE n')
d.close()
"

# 清理模拟数据
rm -rf uploads/simulations/* uploads/projects/*
```

### 验证环境隔离

```bash
# 检查 neo4j 版本
echo "主环境: $(.venv/bin/python -c 'import neo4j; print(neo4j.__version__)')"
echo "模拟环境: $(.venv-simulation/bin/python -c 'import neo4j; print(neo4j.__version__)')"
# 预期：主环境 6.0.3，模拟环境 5.23.0
```

---

## 未来优化方向

1. **图谱服务独立化**：将 Graphiti 做成独立进程/服务（FastAPI），彻底解决事件循环和依赖冲突
2. **并发优化**：如需更高吞吐，可扩展为 loop pool（多线程多循环多 Graphiti 实例）
3. **生产部署**：考虑使用 Gunicorn + gevent 或切换到 FastAPI
