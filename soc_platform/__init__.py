"""Agentic SOC Analyst Platform.

Phase 1 stores immutable source bytes and projects tenant-scoped records.
Phase 2 exposes those records through a read-only HTTP API.
Phase 3 searches events, alerts, and entities with PostgreSQL full text search.
Phase 4 runs investigation agents that draft cited claims for human approval.
Phase 5 adds the reads the security operations console uses for drafts, entities,
and intake metadata. This package does not serve the console interface.
Phase 6 observes the same processes with metrics, structured logs, traces, and health.
"""

__version__ = "0.6.0"
