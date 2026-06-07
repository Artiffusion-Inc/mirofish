# Migration Guide

Steps for migrating from Zep Cloud to Graphiti local deployment.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+
- LLM API configured (Graphiti requires an LLM for entity extraction)

## Migration Steps

### 1. Start Neo4j

```bash
# Navigate to the project root directory
cd /path/to/MiroFish

# Start the Neo4j container
docker-compose -f docker-compose.local.yml up -d

# Check container status
docker-compose -f docker-compose.local.yml ps
```

Wait for the health check to pass (about 30 seconds); the status should show `healthy`.

### 2. Verify Neo4j Connection

Visit Neo4j Browser: http://localhost:7474

- Username: `neo4j`
- Password: `password`

### 3. Install Dependencies

```bash
cd backend

# Using uv (recommended)
uv sync

# Install Graphiti local backend dependencies (optional)
uv sync --extra graphiti

# Or using pip
pip install graphiti-core neo4j
```

> Note: There is currently a Python Neo4j driver version conflict between `oasis` (`camel-oasis`) and `graphiti`, preventing them from being installed in the same venv.
> If your goal is to get the "local graph pipeline" working, we recommend enabling only `--extra graphiti` first; the full pipeline (including simulation) requires resolving the dependency conflict first (see `docs/zep-localization-plan.md`, section 7.5).

### 4. Configure Environment Variables

Create or update the `.env` file:

```env
# Switch to Graphiti backend
ZEP_BACKEND=graphiti

# Neo4j connection configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# LLM configuration (required by Graphiti)
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=your_chat_model

# Graphiti models (explicit configuration recommended)
GRAPHITI_LLM_MODEL=your_chat_model
GRAPHITI_EMBEDDING_MODEL=your_embedding_model
```

### 5. Start the Application

```bash
cd backend
uv run python run.py
```

> You can also run from the project root: `npm run backend` (backend only) or `npm run dev` (starts both frontend and backend).

## Docker Deployment Guide

### docker-compose.local.yml Configuration

```yaml
version: '3.8'

services:
  neo4j:
    image: neo4j:5.26
    container_name: mirofish-neo4j
    ports:
      - "7474:7474"  # HTTP (Browser)
      - "7687:7687"  # Bolt (Driver)
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_apoc_export_file_enabled: "true"
      NEO4J_apoc_import_file_enabled: "true"
      NEO4J_apoc_import_file_use__neo4j__config: "true"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:7474 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
```

### Common Commands

```bash
# Start
docker-compose -f docker-compose.local.yml up -d

# Stop
docker-compose -f docker-compose.local.yml down

# View logs
docker-compose -f docker-compose.local.yml logs -f neo4j

# Reset data (destructive operation)
docker-compose -f docker-compose.local.yml down -v
```

## Data Migration

### Exporting Data from Zep Cloud

Automated data migration is not currently supported. If you need to migrate historical data:

1. Use the Zep Cloud API to export node and edge data
2. Convert to Graphiti episode format
3. Re-import using `add_episode()`

### Data Format Reference

```python
# Zep Cloud export format
nodes = zep_client.node.get_by_graph_id(graph_id)
edges = zep_client.edge.get_by_graph_id(graph_id)

# Convert to episode text for re-import
for edge in edges:
    episode_text = f"{edge.source_node.name} {edge.name} {edge.target_node.name}"
    graphiti_client.add_episode(graph_id, episode_text)
```

## Switching Back to Zep Cloud

If you need to switch back to the Zep Cloud backend:

```bash
# Modify environment variables
export ZEP_BACKEND=cloud
export ZEP_API_KEY=your_api_key

# Restart the application
cd backend && uv run python run.py
```

No code changes required; the application will automatically use the Zep Cloud backend.

## Common Issues

### 1. Neo4j Connection Failure

**Symptoms**: `ServiceUnavailable: Unable to retrieve routing information`

**Solution**:
```bash
# Check container status
docker-compose -f docker-compose.local.yml ps

# If status is not healthy, check logs
docker-compose -f docker-compose.local.yml logs neo4j

# Restart container
docker-compose -f docker-compose.local.yml restart neo4j
```

### 2. Slow Graphiti Initialization

**Symptoms**: `build_indices_and_constraints()` takes a long time on first startup

**Explanation**: This is normal behavior; Graphiti needs to create indexes and constraints in Neo4j. Subsequent startups will be much faster.

### 3. LLM API Errors

**Symptoms**: `OpenAI API error` or similar errors

**Solution**:
1. Verify that `LLM_API_KEY` is correct
2. Verify that `LLM_BASE_URL` is accessible
3. Confirm sufficient API balance

### 4. Empty Search Results

**Symptoms**: `search()` returns empty results

**Possible causes**:
1. `graph_id` (`group_id`) mismatch
2. Episode has not finished processing
3. Query terms do not match the data

**Debugging**:
```python
# Query Neo4j directly to check data
MATCH (n:Entity) WHERE n.group_id = "your_graph_id" RETURN n LIMIT 10
```

### 5. High Memory Usage

**Symptoms**: Neo4j container uses a lot of memory

**Solution**: Limit memory in docker-compose.local.yml

```yaml
services:
  neo4j:
    # ... other configuration ...
    deploy:
      resources:
        limits:
          memory: 2G
    environment:
      NEO4J_dbms_memory_heap_initial__size: 512m
      NEO4J_dbms_memory_heap_max__size: 1G
```

## Feature Differences

| Feature | Zep Cloud | Graphiti Local |
|----------|-----------|---------------|
| Ontology definition | Supported | Not currently supported |
| Multi-graph isolation | Natively supported | Via group_id |
| Entity extraction | Built-in | Requires LLM configuration |
| Search re-ranking | Multiple rerankers supported | Uses default method |
| Episode async processing | Requires polling | Synchronous processing |

## Performance Optimization Recommendations

1. **Neo4j memory configuration**: At least 4GB heap memory recommended for production
2. **Index optimization**: Ensure the `group_id` field has an index
3. **Batch operations**: Use `add_episode_batch()` for bulk data insertion
4. **Connection pool**: GraphitiClient internally manages the connection pool; avoid frequent instance creation