FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apk add --no-cache ca-certificates restic tzdata
COPY backup_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backup_agent/agent.py /app/agent.py
COPY backup_agent/runner_client.py /app/runner_client.py
EXPOSE 8090
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]
