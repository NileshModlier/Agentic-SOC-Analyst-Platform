FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" --uid 10001 soc

COPY pyproject.toml alembic.ini ./
COPY soc_platform ./soc_platform
COPY alembic ./alembic

RUN pip install --no-cache-dir .

USER soc

CMD ["python", "-m", "soc_platform.outbox.relay"]
