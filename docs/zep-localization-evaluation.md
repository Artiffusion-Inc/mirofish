# Zep 本地化（Graphiti）实施评估与改进点

本文档用于评估当前“Zep Cloud → Graphiti + Neo4j 本地后端”的实现质量、可用性风险，并给出按优先级排序的改进建议（MVP 先跑通，再逐步对齐 full parity）。

> 更新时间：2026-01-06（MVP 已在本地跑通端到端）

## 1. 当前实现概览（已完成）

- ✅ 适配器与工厂
  - `backend/app/services/zep_adapter.py`：统一数据结构与接口
  - `backend/app/services/zep_cloud_impl.py`：保持 `zep-cloud` 行为的包装实现
  - `backend/app/services/zep_graphiti_impl.py`：Graphiti + Neo4j 本地实现（MVP）
  - `backend/app/services/zep_factory.py`：基于 `ZEP_BACKEND` 选择后端
- ✅ 调用方迁移
  - `graph_builder.py`、`zep_tools.py`、`zep_entity_reader.py`、`zep_graph_memory_updater.py`、`oasis_profile_generator.py` 已切到适配器
- ✅ 本地依赖
  - `docker-compose.local.yml`：提供 Neo4j 本地部署
  - `backend/pyproject.toml` 通过 optional extras 提供 `graphiti`/`oasis` 依赖（避免 cloud 用户强制安装）

## 2. 总体评价（当前）

- 架构选择（适配器模式 + 双后端可切换）是对的，面试加分点成立。
- ✅ 已验证：`ZEP_BACKEND=graphiti` 可跑通核心链路（建图/实体读取/搜索/报告/仿真）。
- 当前剩余风险更多偏“长期维护/生产化”（monkey-patch 可回收、初始化并发保护、退出清理、ontology 语义对齐）。

## 3. 关键风险点（按严重程度，已更新）

### P0（可能直接导致无法运行/不可用）

1) **Graphiti 依赖 upstream 回归（Issue #683）**
- 状态：当前通过 `backend/app/services/graphiti_patch.py` workaround 绕过；但这是对第三方库内部实现的 monkey-patch，升级 graphiti-core 需要额外小心。

2) **Graphiti 初始化并发（首请求）**
- 状态：当前本地跑通 OK，但 `GraphitiClient._ensure_initialized()` 缺少初始化锁，在并发首请求时存在重复初始化风险（需要 hardening）。

3) **进程退出清理（driver / loop）**
- 状态：当前实现用单后台线程跑 event loop，生产部署（多进程/重启）更需要明确 teardown/shutdown，避免资源泄漏或悬挂线程。

> 以下为已解决的原 P0 风险（保留记录）：  
> - ✅ `LLM_* → OPENAI_*` 映射已在 `backend/app/config.py` 实现（仅在未显式设置 `OPENAI_*` 时映射）  
> - ✅ `_run_async()` 改为单后台线程 + `asyncio.run_coroutine_threadsafe`，避免 `asyncio.run()`/`nest_asyncio`  
> - ✅ 节点/边查询增加 label fallback、边双向匹配与日志提示，降低 schema 差异导致“静默空结果”的概率  
> - ✅ `search()` 改为使用公开 API（`search_()` / `search()` fallback），不再依赖私有 `_search`

### P1（可运行但质量/一致性差）

1) **Graphiti 后端的 `set_ontology()` 目前仅缓存**
- `graph_builder.set_ontology()` 在 graphiti 模式传入的是 list（原始 ontology），GraphitiClient 也仅缓存，不参与抽取或约束。
- 影响：实体类型/关系类型对齐会明显弱于 Zep Cloud；`zep_entity_reader` 的“按 label 过滤实体”可能失效（Graphiti 可能不产出与 ontology 一致的 label）。

2) **依赖冲突带来的运维复杂度**
- `camel-oasis/camel-ai` 与 `graphiti-core` 对 Python neo4j driver 版本要求冲突，当前采用“双 venv + 子进程”运行仿真来绕过，使用门槛稍高。

> 已解决的原 P1 风险（保留记录）：  
> - ✅ 边方向/覆盖范围已统一为双向匹配并做了 schema fallback  
> - ✅ graphiti/oasis 依赖已改为 optional extras（`backend/pyproject.toml`）

## 4. 建议改进（按优先级，当前）

### P0（建议做 hardening，提升稳定性）

1) **给 `GraphitiClient._ensure_initialized()` 加初始化锁 + 幂等**

2) **补齐退出清理**
- Flask teardown / `atexit`：`graphiti.close()` + 停止 loop（至少避免后台线程悬挂）

3) **为 `graphiti_patch` 增加版本/签名 guard + 开关**

### P1（体验与工程质量）

1) **明确 Graphiti 的实体/边如何与 MiroFish ontology 对齐**
- MVP：把 ontology 文本注入到 episode 的 source_description/prompt（至少引导抽取）。
- Full parity：再考虑类型映射、约束、或在 Neo4j 上做标签/属性规范化。

2) **一键化双环境**
- 把 simulation venv 的创建/依赖安装/`SIMULATION_PYTHON` 配置做成脚本或 make target，降低使用门槛。

## 5. 建议的验证清单（可复现）

> 目标：用 `ZEP_BACKEND=graphiti` 可重复跑通 1 次端到端，并记录截图/录屏。

- 启动 Neo4j：`docker-compose -f docker-compose.local.yml up -d`
- 启动后端（确保 LLM/OPENAI env 可用）
- Step1：上传文档 → 生成 ontology → build graph（GraphPanel 能看到 nodes/edges）
- Step2：entities/profiles/config 能生成（允许数量/类型与 cloud 不同，但不能报错）
- Step4：生成报告能走完（search 至少能返回一些内容）

## 6. Full parity 方向（后续里程碑）

- Ontology 映射：实体/关系类型与标签对齐
- Temporal 字段：`valid_at/invalid_at/expired_at` 等语义对齐
- Search 行为：scope/limit/reranker 对齐，结果结构更接近 `zep-cloud`
- Graph memory updater：模拟事件写回图谱并可检索
