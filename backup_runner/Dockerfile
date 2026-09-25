FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apk add --no-cache ca-certificates docker-cli docker-cli-compose
COPY backup_runner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backup_runner/runner.py /app/runner.py
EXPOSE 8091
CMD ["uvicorn", "runner:app", "--host", "0.0.0.0", "--port", "8091", "--workers", "1"]
