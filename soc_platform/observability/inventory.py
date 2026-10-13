"""Platform totals read from PostgreSQL on each API scrape.

The connection uses the table owner, which bypasses row-level security, so the
series are platform-wide. Collector failures keep the last sample and do not
fail the scrape.
"""

from __future__ import annotations

import logging
import time

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import text
from sqlalchemy.engine import Engine

from soc_platform.domain.events import INGEST_REPLAY_FAILED, INGEST_REPLAYED

logger = logging.getLogger(__name__)

_CACHE_SECONDS = 15.0
_QUERY = text(
    """
    SELECT
      (SELECT count(*) FROM alerts) AS alerts_total,
      (SELECT count(*) FROM alerts WHERE severity IN ('high', 'critical')) AS high_severity_alerts_total,
      (SELECT count(*) FROM alerts WHERE status IN ('new', 'in_review')) AS open_alerts_total,
      (SELECT count(*) FROM security_cases WHERE status IN ('open', 'investigating', 'contained')) AS active_cases_total,
      (SELECT count(*) FROM investigations) AS investigations_total,
      (SELECT count(*) FROM dead_letters) AS dead_letters_total,
      (SELECT count(*) FROM canonical_events) AS events_ingested_total,
      (SELECT count(*) FROM outbox_events WHERE event_type IN (:replayed, :replay_failed)) AS events_replayed_total,
      (SELECT count(*) FROM outbox_events) AS outbox_events_total
    """
)

_GAUGES = (
    "alerts_total",
    "high_severity_alerts_total",
    "open_alerts_total",
    "active_cases_total",
    "investigations_total",
)
_COUNTERS = (
    "dead_letters_total",
    "events_ingested_total",
    "events_replayed_total",
    "outbox_events_total",
)
_HELP = {
    "alerts_total": "Alerts stored for every tenant.",
    "high_severity_alerts_total": "Alerts whose severity is high or critical.",
    "open_alerts_total": "Alerts whose status is new or in review.",
    "active_cases_total": "Cases whose status is open, investigating, or contained.",
    "investigations_total": "Investigations stored for every tenant.",
    "dead_letters_total": "Dead-letter rows, including parse, replay, and publish.",
    "events_ingested_total": "Canonical events projected from source records.",
    "events_replayed_total": "Replay attempts recorded in the outbox.",
    "outbox_events_total": "Outbox rows in every publication state.",
}


class InventoryCollector(Collector):
    def __init__(self, engine: Engine, redis_client: object) -> None:
        self._engine = engine
        self._redis = redis_client
        self._cached: dict[str, float] | None = None
        self._cached_at = 0.0
        self._postgres_up = False
        self._redis_up = False
        self._reported_failure = False

    def collect(self):
        sample, postgres_up, redis_up = self._sample()
        dependency = GaugeMetricFamily("dependency_up", "1 when a dependency answered a probe.", labels=["component"])
        dependency.add_metric(["postgres"], 1 if postgres_up else 0)
        dependency.add_metric(["redis"], 1 if redis_up else 0)
        yield dependency
        for name in _GAUGES:
            family = GaugeMetricFamily(name, _HELP[name])
            family.add_metric([], sample[name])
            yield family
        for name in _COUNTERS:
            family = CounterMetricFamily(name, _HELP[name])
            family.add_metric([], sample[name])
            yield family


    def _sample(self) -> tuple[dict[str, float], bool, bool]:
        now = time.monotonic()
        if self._cached is not None and now - self._cached_at < _CACHE_SECONDS:
            return self._cached, self._postgres_up, self._redis_up
        counts, postgres_up = self._query()
        redis_up = self._ping()
        if counts is None:
            counts = self._cached if self._cached is not None else {name: 0.0 for name in (*_GAUGES, *_COUNTERS)}
        else:
            self._reported_failure = False
        self._cached = counts
        self._cached_at = now
        self._postgres_up = postgres_up
        self._redis_up = redis_up
        return counts, postgres_up, redis_up

    def _query(self) -> tuple[dict[str, float] | None, bool]:
        try:
            with self._engine.connect() as connection:
                row = connection.execute(
                    _QUERY,
                    {"replayed": INGEST_REPLAYED, "replay_failed": INGEST_REPLAY_FAILED},
                ).one()
            return {name: float(getattr(row, name)) for name in (*_GAUGES, *_COUNTERS)}, True
        except Exception:
            if not self._reported_failure:
                logger.warning("inventory metrics query failed", exc_info=True)
                self._reported_failure = True
            return None, False

    def _ping(self) -> bool:
        try:
            return bool(self._redis.ping())  # type: ignore[attr-defined]
        except Exception:
            return False


class PoolCollector(Collector):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def collect(self):
        family = GaugeMetricFamily(
            "db_pool_connections",
            "SQLAlchemy connection pool occupancy.",
            labels=["state"],
        )
        pool = self._engine.pool
        family.add_metric(["checked_out"], _pool_value(pool, "checkedout"))
        family.add_metric(["checked_in"], _pool_value(pool, "checkedin"))
        family.add_metric(["overflow"], _pool_value(pool, "overflow"))
        yield family


def _pool_value(pool: object, name: str) -> float:
    method = getattr(pool, name, None)
    if not callable(method):
        return 0.0
    try:
        return float(method())
    except Exception:
        logger.debug("pool stat %s was not read", name, exc_info=True)
        return 0.0
