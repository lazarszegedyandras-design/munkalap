FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels
COPY --chown=10001:10001 backend/ .
# Clean a stale, never-valid migration filename that can survive when a release
# is extracted over a much older source tree before the image is rebuilt.
RUN rm -f /app/migrations/versions/0024_contract_details_archives_hr_calendar.py
COPY --chown=10001:10001 VERSION /app/VERSION
COPY --chown=10001:10001 CHANGELOG.md /app/CHANGELOG.md
RUN install -d -o 10001 -g 10001 -m 0750 /app/runtime
EXPOSE 8000
LABEL hu.lunait.munkalap.migrate-hotfix="v0.30.0-hotfix3"
USER 10001:10001
CMD ["sh", "/app/entrypoint.sh"]
