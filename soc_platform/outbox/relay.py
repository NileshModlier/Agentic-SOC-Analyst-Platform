"""Long-running outbox relay. This is not an analyst agent."""

from __future__ import annotations

import logging
import signal
import time

from redis import Redis
from sqlalchemy.orm import Session

from soc_platform.config import get_settings
from soc_platform.db.session import create_db_engine
from soc_platform.observability import (
    configure_observability,
    instrument_redis_client,
    instrument_sqlalchemy,
    service_settings,
    shutdown_tracing,
    start_relay_metrics,
)
from soc_platform.outbox.publisher import publish_pending

logger = logging.getLogger(__name__)


def main() -> None:
    settings = service_settings(get_settings(), "soc-relay")
    configure_observability(settings)
    start_relay_metrics(settings)
    stop = False

    def _stop(signum: int, _frame: object) -> None:
        nonlocal stop
        logger.info("outbox relay stopping signal=%s", signum)
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    engine = create_db_engine(settings.database_url)
    instrument_sqlalchemy(engine)
    client = instrument_redis_client(Redis.from_url(settings.redis_url))
    logger.info("outbox relay started stream=%s", settings.outbox_stream)
    try:
        while not stop:
            with Session(engine) as session:
                with session.begin():
                    handled = publish_pending(
                        session,
                        client,
                        stream=settings.outbox_stream,
                        batch_size=settings.outbox_batch_size,
                        max_attempts=settings.outbox_max_attempts,
                    )
            if handled == 0 and not stop:
                _wait(settings.outbox_poll_interval_seconds, lambda: stop)
    finally:
        client.close()
        engine.dispose()
        shutdown_tracing()


def _wait(seconds: float, should_stop) -> None:
    deadline = time.monotonic() + seconds
    while not should_stop() and time.monotonic() < deadline:
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))


if __name__ == "__main__":
    main()
