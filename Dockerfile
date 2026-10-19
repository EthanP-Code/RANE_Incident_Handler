FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY backend ./backend
COPY incident_event_log.csv Incident_response.txt ./

RUN pip install --no-cache-dir ./backend

EXPOSE 8080

CMD ["sh", "-c", "uvicorn rane_api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
