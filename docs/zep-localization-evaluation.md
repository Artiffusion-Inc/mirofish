# Zep Localization (Graphiti) Implementation Evaluation and Improvement Points

This document evaluates the current “Zep Cloud → Graphiti + Neo4j local backend” implementation quality, usability risks, and provides prioritized improvement suggestions (MVP first, then progressively align to full parity).

> Updated: 2026-01-06 (MVP end-to-end verified locally)

## 1. Current Implementation Overview (Completed)

- ✅ Adapter and Factory
  - `backend/app/services/zep_adapter.py`: Unified data structures and interface
  - `backend/app/services/zep_cloud_impl.py`: Wrapper implementation preserving `zep-cloud` behavior
  - `backend/app/services/zep_graphiti_impl.py`: Graphiti + Neo4j local implementation (MVP)
  - `backend/app/services/zep_factory.py`: Backend selection based on `ZEP_BACKEND`
- ✅ Caller Migration
  - `graph_builder.py`, `zep_tools.py`, `zep_entity_reader.py`, `zep_graph_memory_updater.py`, `oasis_profile_generator.py` have been switched to the adapter
- ✅ Local Dependencies
  - `docker-compose.local.yml`: Provides local Neo4j deployment
  - `backend/pyproject.toml` provides `graphiti`/`oasis` dependencies via optional extras (avoiding forced installation for cloud users)

## 2. Overall Assessment (Current)

- The architecture choice (adapter pattern + dual backend switchable) is correct; the interview selling point holds.
- ✅ Verified: `ZEP_BACKEND=graphiti` can run the core pipeline (graph building / entity reading / search / report / simulation).
- Current remaining risks are more about “long-term maintenance / production readiness” (monkey-patch recoverability, initialization concurrency protection, exit cleanup, ontology semantic alignment).

## 3. Key Risk Points (by severity, updated)

### P0 (May directly cause inability to run / unavailable)

1) **Graphiti dependency upstream regression (Issue #683)**
- Status: Currently bypassed via `backend/app/services/graphiti_patch.py` workaround; however, this is a monkey-patch of a third-party library's internal implementation, and upgrading graphiti-core requires extra caution.

2) **Graphiti initialization concurrency (first request)**
- Status: Currently works locally, but `GraphitiClient._ensure_initialized()` lacks an initialization lock, posing a duplicate initialization risk under concurrent first requests (needs hardening).

3) **Process exit cleanup (driver / loop)**
- Status: Current implementation uses a single background thread for the event loop. Production deployments (multi-process / restarts) require explicit teardown/shutdown to avoid resource leaks or dangling threads.

> Previously resolved P0 risks (kept for record):
> - ✅ `LLM_* → OPENAI_*` mapping implemented in `backend/app/config.py` (only maps when `OPENAI_*` is not explicitly set)
> - ✅ `_run_async()` switched to single background thread + `asyncio.run_coroutine_threadsafe`, avoiding `asyncio.run()`/`nest_asyncio`
> - ✅ Node/edge queries add label fallback, bidirectional edge matching, and log hints, reducing the probability of “silent empty results” due to schema differences
> - ✅ `search()` switched to using public API (`search_()` / `search()` fallback), no longer depends on private `_search`

### P1 (Runnable but quality / consistency issues)

1) **Graphiti backend's `set_ontology()` currently only caches**
- `graph_builder.set_ontology()` passes a list (raw ontology) in graphiti mode, and GraphitiClient only caches it without participating in extraction or constraints.
- Impact: Entity type / relationship type alignment will be noticeably weaker than Zep Cloud; `zep_entity_reader`'s “filter entities by label” may fail (Graphiti may not produce labels consistent with the ontology).

2) **Operational complexity from dependency conflicts**
- `camel-oasis/camel-ai` and `graphiti-core` have conflicting Python neo4j driver version requirements. Currently worked around with a “dual venv + subprocess” approach for running simulations, which raises the usage barrier slightly.

> Previously resolved P1 risks (kept for record):
> - ✅ Edge direction / coverage unified to bidirectional matching with schema fallback
> - ✅ graphiti/oasis dependencies changed to optional extras (`backend/pyproject.toml`)

## 4. Suggested Improvements (by priority, current)

### P0 (Recommended hardening for stability)

1) **Add initialization lock + idempotency to `GraphitiClient._ensure_initialized()`**

2) **Add exit cleanup**
- Flask teardown / `atexit`: `graphiti.close()` + stop loop (at minimum avoid dangling background threads)

3) **Add version/signature guard + toggle to `graphiti_patch`**

### P1 (Experience and engineering quality)

1) **Clarify how Graphiti entities/edges align with MiroFish ontology**
- MVP: Inject ontology text into the episode's source_description/prompt (at least guide extraction).
- Full parity: Then consider type mapping, constraints, or label/attribute normalization on Neo4j.

2) **One-command dual environment setup**
- Turn simulation venv creation / dependency installation / `SIMULATION_PYTHON` configuration into a script or make target to lower the usage barrier.

## 5. Suggested Verification Checklist (Reproducible)

> Goal: Use `ZEP_BACKEND=graphiti` to repeatedly run 1 end-to-end pass, and record screenshots/video.

- Start Neo4j: `docker-compose -f docker-compose.local.yml up -d`
- Start backend (ensure LLM/OPENAI env is available)
- Step1: Upload document → generate ontology → build graph (GraphPanel can show nodes/edges)
- Step2: entities/profiles/config can be generated (allow different counts/types from cloud, but no errors)
- Step4: Report generation can complete (search returns at least some content)

## 6. Full Parity Direction (Future Milestones)

- Ontology mapping: Entity/relationship type and label alignment
- Temporal fields: `valid_at/invalid_at/expired_at` semantic alignment
- Search behavior: scope/limit/reranker alignment, result structure closer to `zep-cloud`
- Graph memory updater: Simulation events written back to the graph and searchable
