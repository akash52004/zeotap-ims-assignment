# Prompts And Plan

## Assignment Prompt

Build a resilient Incident Management System for a distributed stack. It must ingest high-volume signals, debounce repeated component failures, persist raw and structured records separately, expose a dashboard, require RCA before closure, calculate MTTR, provide health and throughput observability, include rate limiting, tests, sample data, Docker Compose setup, and documentation.

## Implementation Plan Used

1. Build an async FastAPI backend with a bounded queue so ingestion can accept bursts without blocking on persistence.
2. Store raw payloads in JSONL, structured work items and RCA records in SQLite, and active dashboard state in memory.
3. Implement alert routing with the Strategy pattern and incident lifecycle validation with a state machine.
4. Create a React dashboard with live feed, detail view, raw signal inspection, status transitions, and RCA closure form.
5. Add sample data that simulates an RDBMS outage followed by MCP and cache degradation.
6. Document setup, architecture, backpressure, resilience, security, and test commands.
