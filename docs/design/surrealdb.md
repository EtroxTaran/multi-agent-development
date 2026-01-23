# SurrealDB Integration Guide

This guide covers setting up and using SurrealDB with Conductor for persistent workflow state, queryable audit trails, and real-time monitoring.

## Why SurrealDB?

| Current (JSON Files) | With SurrealDB |
|---------------------|----------------|
| Manual file reads | SQL-like queries |
| No concurrent safety | ACID transactions |
| Polling for changes | Live Queries (real-time) |
| Hard to query audit logs | Full query support |
| No cross-project patterns | Vector search for similar errors |

## Quick Start

### 1. Start SurrealDB (Docker)

```bash
cd docker/surrealdb
cp .env.example .env
# Edit .env with your password
docker-compose up -d
```

### 2. Configure Meta-Architect

```bash
# Copy example env
cp orchestrator/db/env.example .env

# Edit .env
SURREAL_URL=ws://localhost:8000/rpc
SURREAL_USER=root
SURREAL_PASS=your-password
```

### 3. Verify Connection

```bash
python scripts/db-cli.py status
```

### 4. Migrate Existing Data

```bash
# Dry run first
python scripts/db-cli.py migrate --project my-project --dry-run

# Actual migration
python scripts/db-cli.py migrate --project my-project
```

## Deployment Options

### Option 1: Local Development

```bash
docker run -d --name surrealdb \
  -p 8000:8000 \
  -v surrealdb_data:/data \
  surrealdb/surrealdb:v2.1 \
  start --log info --user root --pass changeme rocksdb:/data/database.db
```

### Option 2: Remote Server (Dokploy)

1. Create new project in Dokploy
2. Copy `docker/surrealdb/docker-compose.yml`
3. Set environment variables
4. Deploy
5. Configure domain/SSL

Update your `.env`:
```bash
SURREAL_URL=wss://surrealdb.your-domain.com/rpc
```

## Usage Examples

### Query Audit Trail

```bash
# Find all failures for a task
python scripts/db-cli.py query -p my-project \
  "SELECT * FROM audit_entries WHERE task_id = 'T1' AND status = 'failed'"

# Get cost breakdown
python scripts/db-cli.py query -p my-project \
  "SELECT agent, math::sum(cost_usd) as total FROM audit_entries GROUP BY agent"
```

### Python API

```python
from orchestrator.db import (
    is_surrealdb_enabled,
    get_audit_repository,
    get_workflow_repository,
    get_task_repository,
)

# Check if enabled
if is_surrealdb_enabled():
    # Get repositories
    audit = get_audit_repository("my-project")
    workflow = get_workflow_repository("my-project")
    tasks = get_task_repository("my-project")

    # Create audit entry
    entry = await audit.create_entry(
        agent="claude",
        task_id="T1",
        prompt="Implement feature X",
    )

    # Update with result
    await audit.update_result(
        entry.id,
        success=True,
        exit_code=0,
        duration_seconds=45.2,
        cost_usd=0.05,
    )

    # Get statistics
    stats = await audit.get_statistics()
    print(f"Success rate: {stats.success_rate:.1%}")
```

### Real-Time Monitoring

```python
from orchestrator.db import create_workflow_monitor

async with create_workflow_monitor("my-project") as monitor:
    # Subscribe to task changes
    await monitor.on_task_change(
        lambda event: print(f"Task {event.record_id}: {event.data.get('status')}")
    )

    # Subscribe to state changes
    await monitor.on_state_change(
        lambda event: print(f"Phase: {event.data.get('current_phase')}")
    )

    # Keep running
    await asyncio.sleep(3600)
```

## Schema

The database schema includes:

| Table | Purpose |
|-------|---------|
| `workflow_state` | Current workflow state per project |
| `tasks` | Individual implementation tasks |
| `milestones` | Task groupings |
| `audit_entries` | CLI invocation audit trail |
| `error_patterns` | Cross-project error patterns (with embeddings) |
| `checkpoints` | Manual workflow snapshots |
| `sessions` | CLI session continuity |
| `budget_records` | Cost tracking |
| `workflow_events` | Live event stream |

## CLI Reference

```bash
# Show connection status
python scripts/db-cli.py status

# Migrate single project
python scripts/db-cli.py migrate -p project-name -d ./projects/project-name

# Migrate all projects
python scripts/db-cli.py migrate-all --projects-dir ./projects

# Initialize schema
python scripts/db-cli.py init-schema -p project-name

# Execute query
python scripts/db-cli.py query -p project-name "SELECT * FROM tasks"

# Show statistics
python scripts/db-cli.py stats -p project-name
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SURREAL_URL` | `ws://localhost:8000/rpc` | WebSocket URL |
| `SURREAL_NAMESPACE` | `orchestrator` | Namespace for isolation |
| `SURREAL_DATABASE` | `default` | Default database name |
| `SURREAL_USER` | `root` | Authentication user |
| `SURREAL_PASS` | (required) | Authentication password |
| `SURREAL_POOL_SIZE` | `5` | Connection pool size |
| `SURREAL_LIVE_QUERIES` | `true` | Enable Live Queries |

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │           SurrealDB Instance            │
                    │                                         │
                    │  ┌─────────────────────────────────┐   │
                    │  │     Namespace: orchestrator      │   │
                    │  │                                  │   │
                    │  │  ┌──────────┐  ┌──────────┐    │   │
                    │  │  │ project_ │  │ project_ │    │   │
                    │  │  │  alpha   │  │  beta    │    │   │
                    │  │  └──────────┘  └──────────┘    │   │
                    │  │                                  │   │
                    │  │  ┌──────────────────────────┐   │   │
                    │  │  │   shared (patterns DB)   │   │   │
                    │  │  └──────────────────────────┘   │   │
                    │  └─────────────────────────────────┘   │
                    └─────────────────────────────────────────┘
                                        │
                         WebSocket (ws:// or wss://)
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
          ▼                             ▼                             ▼
    ┌───────────┐              ┌───────────────┐              ┌───────────┐
    │  Claude   │              │   Orchestrator │              │  Monitor  │
    │  Worker   │              │    (Python)    │              │   (UI)    │
    └───────────┘              └───────────────┘              └───────────┘
```

## Troubleshooting

### Connection Failed

1. Check SurrealDB is running: `docker ps`
2. Check URL is correct (ws:// for local, wss:// for remote)
3. Check credentials match

### Live Queries Not Working

1. Ensure `SURREAL_LIVE_QUERIES=true`
2. Check WebSocket connection is stable
3. Verify table has been created (run `init-schema` first)

### Migration Failed

1. Run with `--dry-run` first to validate
2. Check source JSON files exist
3. Ensure target database is empty or backup first
