# MiroFish Local Edition Startup Guide

This document explains how to start the MiroFish local edition (using graphiti-core + Neo4j instead of Zep Cloud).

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │────▶│    Neo4j    │
│   (Vue 3)   │     │   (Flask)   │     │  (Docker)   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
              ┌─────▼─────┐ ┌─────▼─────┐
              │  Main Env  │ │  Sim Env  │
              │ graphiti  │ │ camel-ai  │
              │ neo4j 6.x │ │ neo4j 5.x │
              └───────────┘ └───────────┘
```

**Dual-environment isolation**: camel-ai and graphiti-core have conflicting neo4j driver version requirements, resolved through separate virtual environments.

## Prerequisites

| Tool | Version | Description |
|------|---------|-------------|
| Node.js | 18+ | Frontend runtime |
| Python | 3.11 | camel-oasis requires 3.10-3.11 |
| uv | Latest | Python package manager |
| Docker | Latest | Runs Neo4j |

## Quick Start

### 1. Start Neo4j

```bash
docker-compose -f docker-compose.local.yml up -d neo4j
```

Verify: visit http://localhost:7474 and log in with `neo4j/password`

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
# LLM (Alibaba Bailian qwen-plus recommended)
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Embedding (DashScope)
EMBEDDING_API_KEY=your_dashscope_api_key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v3
```

### 3. Install Dependencies

```bash
# One-click install
npm run setup:all

# Or step by step
npm run setup          # Node dependencies
npm run setup:backend  # Python dependencies
```

### 4. Create Simulation Environment

Resolves the neo4j version conflict:

```bash
cd backend
uv venv .venv-simulation --python 3.11
source .venv-simulation/bin/activate
uv pip install camel-oasis openai python-dotenv
deactivate
```

### 5. Start Services

```bash
npm run dev
```

Service URLs:
- Frontend: http://localhost:3000
- Backend: http://localhost:5001
- Neo4j: http://localhost:7474

## Data Cleanup

```bash
cd backend

# Clean Neo4j
.venv/bin/python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
with d.session() as s: s.run('MATCH (n) DETACH DELETE n')
d.close()
"

# Clean simulation data
rm -rf uploads/simulations/* uploads/projects/*
```

## Verify Environment

```bash
cd backend

# Check neo4j version isolation
echo "Main env: $(.venv/bin/python -c 'import neo4j; print(neo4j.__version__)')"
echo "Sim env: $(.venv-simulation/bin/python -c 'import neo4j; print(neo4j.__version__)')"
# Expected: Main env 6.x, Sim env 5.23.0
```

## Troubleshooting

See [docs/zep-localization/troubleshooting.md](docs/zep-localization/troubleshooting.md)

## Development Tools

This project uses [Claude Code](https://claude.ai/claude-code) for development, with the [planning-with-files](https://github.com/OthmanAdi/planning-with-files) skill for managing complex tasks.
