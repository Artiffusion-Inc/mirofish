# Zep 本地化完善清单

> 当前状态：MVP 已跑通，以下为后续优化项

## 优先级说明

- **P0**：生产必须
- **P1**：强烈建议
- **P2**：锦上添花

---

## 架构优化

### [ ] P1: 图谱服务独立化
将 Graphiti 从 Flask 进程中剥离，作为独立服务运行。

**收益**：
- 彻底解决 Flask 同步 + Graphiti 异步的冲突
- 解决 neo4j driver 版本冲突（独立 venv）
- 进程隔离，故障不相互影响
- 可独立扩展

**方案**：
```
┌─────────┐      HTTP       ┌──────────────────┐
│  Flask  │ ──────────────▶ │ Graphiti Service │
│ Backend │                  │ (FastAPI/gRPC)   │
└─────────┘                  └──────────────────┘
                                   │
                                   ▼
                             Neo4j + Graphiti
```

**工作量**：2-3 天

---

## 错误处理

### [ ] P0: Graphiti 初始化并发保护
当前 `GraphitiClient._ensure_initialized()` 在并发首请求下可能触发重复初始化（重复建索引/重复创建 driver/重复 patch），需要加锁并保证幂等。

### [ ] P0: 事件循环启动失败处理
```python
# 当前：无处理
# 改进：添加重试 + 降级
def _ensure_async_loop():
    # TODO: 添加启动超时检测
    # TODO: 启动失败时的降级策略
```

### [ ] P0: Neo4j 连接异常处理
```python
# 当前：连接失败直接抛异常
# 改进：
# - 连接池健康检查
# - 自动重连
# - 优雅降级（返回空结果而非崩溃）
```

### [ ] P1: Graphiti 操作超时处理
```python
# 当前：硬编码 300s 超时
# 改进：
# - 可配置超时
# - 超时后清理资源
# - 长操作进度反馈
```

### [ ] P1: 进程退出清理（driver / loop）
本地跑通 OK，但生产/长期跑要有可控的 shutdown：
- Flask teardown / 进程退出时 `graphiti.close()` + `driver.close()`
- 后台 loop 线程的 stop/join（至少避免僵尸线程/资源泄漏）

### [ ] P1: graphiti-core workaround 风险控制（可回收）
当前对 graphiti-core 的 monkey-patch 属于“为了跑通”的临时方案，建议补齐以下护栏：
- 启动时校验 graphiti-core 版本/函数签名，不匹配就 fail fast（避免静默写坏数据）
- 打印明确日志：patch 是否生效、针对的 upstream issue、如何关闭
- 预留开关：`GRAPHITI_DISABLE_PATCH=1`
- 上游修复合入后，移除 patch 并在文档标记可删除的版本范围

---

## 配置管理

### [ ] P0: 硬编码配置外部化

| 当前位置 | 配置项 | 应改为 |
|---------|-------|-------|
| `backend/app/config.py` | `NEO4J_PASSWORD` 默认值 `password` | 生产环境去掉默认值/强校验 |
| `backend/app/services/zep_graphiti_impl.py` | `_run_async()` 超时 300s | 环境变量（例如 `GRAPHITI_ASYNC_CALL_TIMEOUT_S`） |
| `backend/app/services/simulation_runner.py` | `.venv-simulation` fallback 路径 | 环境变量（已支持 `SIMULATION_PYTHON`，可补一键化脚本/校验） |
| `backend/app/services/zep_graphiti_impl.py` | DashScope embedding `batch_size=10` | 环境变量（例如 `GRAPHITI_EMBEDDING_BATCH_SIZE`） |

### [ ] P1: 配置验证完善
当前已有基础校验（`backend/app/config.py` 的 `Config.validate()`），建议补齐：
- graphiti 模式下的 LLM/embedder 相关配置提示（例如未设置 `GRAPHITI_*` 时的建议）
- simulation venv 可用性检查（缺依赖时给出“如何创建 .venv-simulation”的明确指引）

### [ ] P1: 环境变量命名收敛
把分散的“默认值/魔法数字”收敛成明确的 env var（示例）：
- `GRAPHITI_LOOP_STARTUP_TIMEOUT_S`
- `GRAPHITI_ASYNC_CALL_TIMEOUT_S`
- `GRAPHITI_EMBEDDING_BATCH_SIZE`（DashScope <= 10）
- `SIMULATION_PYTHON`（仿真独立 venv）

---

## 可观测性

### [ ] P1: 结构化日志
```python
# 当前：logger.info("消息")
# 改进：
logger.info("graphiti_operation", extra={
    "operation": "add_episode",
    "group_id": group_id,
    "duration_ms": duration,
    "status": "success"
})
```

### [ ] P1: 指标采集
- 事件循环队列深度
- Graphiti 操作延迟分布
- Neo4j 连接池状态
- DashScope API 调用次数/延迟

### [ ] P2: 健康检查端点
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

## 性能优化

### [ ] P2: 并发能力提升
当前：单后台线程串行执行所有 Graphiti 操作

**方案 A**：Loop Pool
```python
# 多个后台线程，每个有独立事件循环
# 请求按 group_id 哈希分配到固定线程
```

**方案 B**：异步队列
```python
# 写操作入队，批量处理
# 读操作直接执行
```

### [ ] P2: 连接池优化
- Neo4j 连接池大小调优
- 连接预热
- 空闲连接回收

---

## 测试

### [ ] P0: 集成测试
```python
# tests/integration/test_graphiti_flow.py
def test_full_flow():
    # 上传 PDF → 构建图谱 → 运行模拟 → 生成报告
    pass
```

### [ ] P1: 事件循环压力测试
```python
def test_concurrent_requests():
    # 模拟多个 Flask 请求同时调用 Graphiti
    # 验证无死锁、无数据竞争
    pass
```

### [ ] P1: 故障注入测试
- Neo4j 断连恢复
- DashScope API 超时
- 磁盘空间不足

---

## 文档

### [ ] P1: API 文档
- Graphiti 本地客户端接口文档
- 与 Zep Cloud 的差异说明

### [ ] P2: 运维手册
- 日常维护命令
- 故障排查流程
- 备份恢复

---

## 依赖管理

### [ ] P1: 锁定依赖版本
```bash
# 当前：requirements.txt 版本范围宽松
# 改进：生成精确版本锁文件
uv pip compile requirements.in -o requirements.txt
```

### [ ] P1: 双环境一键化（graphiti / simulation）
当前 graphiti 与 oasis 的 neo4j driver 版本冲突是客观存在的，建议把“拆 venv / 拆进程”的做法产品化：
- 提供 `make venv-graphiti` / `make venv-simulation`（或脚本）
- 前端/后端提示更明确（缺少依赖时显示“需要 simulation venv”而不是 No module named）

### [ ] P2: 依赖安全扫描
```bash
# CI 中添加
pip-audit
```

---

## 记录

| 日期 | 完成项 | 备注 |
|------|-------|------|
| 2026-01-05 | MVP 跑通 | 双环境隔离 + 单后台线程方案 |
