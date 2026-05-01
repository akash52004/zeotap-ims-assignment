# Architecture

```mermaid
flowchart LR
    Producers["Signal Producers<br/>APIs, MCP Hosts, Caches, Queues, DBs"] --> API["FastAPI Ingestion API<br/>JSON over HTTP"]
    API --> RateLimiter["Sliding Window<br/>Rate Limiter"]
    RateLimiter --> Queue["Bounded Async Queue<br/>Backpressure Buffer"]
    Queue --> Workers["Async Workers<br/>Retry DB Writes"]
    Workers --> Raw["JSONL Raw Signal Lake<br/>Audit Log"]
    Workers --> SQLite["SQLite Source of Truth<br/>Work Items + RCA"]
    Workers --> Agg["Timeseries Aggregates"]
    Workers --> Cache["In-Memory Dashboard Cache"]
    Cache --> UI["React Dashboard"]
    SQLite --> UI
    Raw --> UI
```

## Storage Responsibilities

- Raw signal lake: `raw_signals.jsonl`, append-only audit trail for high-volume payloads.
- Source of truth: SQLite tables for work items and RCA records with transactional updates.
- Hot path: in-memory dashboard cache refreshed by async workers.
- Aggregations: per-minute counts stored in `signal_aggregates`.

## Design Patterns

- Strategy pattern: `AlertRouter` maps component classes to alert classification strategies.
- State pattern: `WorkItemStateMachine` validates lifecycle transitions and enforces mandatory RCA before `CLOSED`.
